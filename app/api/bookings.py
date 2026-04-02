import logging
from datetime import timedelta, datetime
from types import SimpleNamespace

from flask import request, make_response, jsonify
from sqlalchemy import or_, and_

from . import api
from app.api.models import Booking, RoomOnline, BookingRate, BookingStatus
from .. import db
from app.auth.utils import get_current_user
from app.api.decorators import require_permission
# --- ADDED IMPORT ---
from app.api.channel_manager.models import ChannelReservationLink
from app.api.channel_manager.services.pms_sync import (
    queue_booking_ari_sync,
    queue_booking_transition_ari_sync,
)


@api.route('/properties/<int:property_id>/bookings', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_bookings')
def new_booking(property_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        user_id = get_current_user()  # Still getting this just to mark the creator
        booking_data = request.get_json()

        try:
            booking = Booking.from_json(booking_data)
        except ValueError as ve:
            print(str(ve))
            return make_response(jsonify({'status': 'fail', 'message': str(ve)})), 400

        # Force the property_id from the secured URL to prevent payload tampering
        booking.property_id = property_id
        booking.creator_id = user_id

        assign_nightly_rates(booking)
        db.session.add(booking)
        db.session.commit()

        queue_booking_ari_sync(booking, 'booking_created')

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking submitted successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in new_booking: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to submit booking. Please try again.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_bookings')
def edit_booking(property_id, booking_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking_data = request.get_json()

        # Removed creator_id check. Any staff with 'manage_bookings' can edit now.
        booking = db.session.query(Booking).filter_by(id=booking_id, property_id=property_id).first()
        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found in this property.'
            })), 404

        old_property_id = booking.property_id
        old_room_id = booking.room_id
        old_check_in = booking.check_in
        old_check_out = booking.check_out

        # Update fields dynamically
        updateable_fields = [
            'first_name', 'last_name', 'email', 'phone', 'number_of_adults',
            'number_of_children', 'payment_status_id', 'status_id', 'note',
            'special_request', 'check_in', 'check_out', 'check_in_day',
            'check_in_month', 'check_in_year', 'check_out_day', 'check_out_month',
            'check_out_year', 'number_of_days', 'rate', 'room_id'
        ]

        for field in updateable_fields:
            if field in booking_data:
                setattr(booking, field, booking_data[field])

        BookingRate.query.filter_by(booking_id=booking.id).delete()
        assign_nightly_rates(booking)

        db.session.commit()

        queue_booking_transition_ari_sync(
            old_property_id=old_property_id,
            old_room_id=old_room_id,
            old_check_in=old_check_in,
            old_check_out=old_check_out,
            booking=booking,
            reason='booking_updated',
        )

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking updated successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error in edit_booking: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update booking. Please try again.'
        })), 500


@api.route('/properties/<int:property_id>/bookings', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_bookings')
def all_bookings(property_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        check_in_year = request.args.get('check_in_year', type=int)
        check_in_month = request.args.get('check_in_month', type=int)

        bookings = db.session.query(Booking).filter(
            and_(
                Booking.property_id == property_id,
                or_(Booking.check_in_year == check_in_year,
                    Booking.check_out_year == check_in_year),
                or_(
                    and_(Booking.check_in_month == check_in_month,
                         Booking.check_out_month == check_in_month),
                    and_(Booking.check_in_month != check_in_month,
                         Booking.check_out_month == check_in_month),
                    and_(Booking.check_in_month == check_in_month,
                         Booking.check_out_month != check_in_month)
                )
            )
        ).order_by(Booking.check_in_year, Booking.check_in_month, Booking.check_in_day).all()

        response_data = [booking.to_json() for booking in bookings]

        return make_response(jsonify({
            'status': 'success',
            'data': response_data
        })), 200
    except Exception as e:
        logging.exception("Error in all_bookings: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch bookings.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_bookings')
def delete_booking(property_id, booking_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking = db.session.query(Booking).filter_by(id=booking_id, property_id=property_id).first()

        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found or permission denied.'
            })), 404

        old_property_id = booking.property_id
        old_room_id = booking.room_id
        old_check_in = booking.check_in
        old_check_out = booking.check_out

        # --- ADDED THIS LINE TO PREVENT FOREIGN KEY ERROR ---
        ChannelReservationLink.query.filter_by(internal_booking_id=booking_id).delete(synchronize_session=False)

        db.session.delete(booking)
        db.session.commit()

        deleted_snapshot = SimpleNamespace(
            property_id=old_property_id,
            room_id=old_room_id,
            check_in=old_check_in,
            check_out=old_check_out,
        )

        queue_booking_ari_sync(deleted_snapshot, 'booking_deleted')

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking deleted successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error in delete_booking: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete booking. Please try again.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/check_in', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_bookings')
def check_in_booking(property_id, booking_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking = db.session.query(Booking).filter_by(id=booking_id, property_id=property_id).first()

        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found.'
            })), 404

        checked_in_status = db.session.query(BookingStatus).filter_by(code='CHECKED IN').first()
        if not checked_in_status:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Checked In status not configured in the system.'
            })), 500

        booking.change_status(checked_in_status.id)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking status updated to CHECKED IN.'
        })), 200

    except Exception as e:
        logging.exception("Error in check_in_booking: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update booking status.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/by_state', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_bookings')
def bookings_by_date_and_state(property_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        date_str = request.args.get('date')
        booking_type = request.args.get('booking_state', type=str)

        if not date_str or not booking_type:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Missing date or booking_state parameter.'
            })), 400

        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Invalid date format. Expected YYYY-MM-DD.'
            })), 400

        booking_type = booking_type.strip().lower()

        filters = {
            'arrivals': Booking.check_in == target_date,
            'departures': Booking.check_out == target_date,
            'inhouse': and_(
                Booking.check_in <= target_date,
                Booking.check_out > target_date
            ),
        }

        selected_filter = filters.get(booking_type)
        if selected_filter is None:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Invalid booking_state. Use InHouse, Arrivals, or Departures.'
            })), 400

        bookings = (
            db.session.query(Booking)
            .filter(
                Booking.property_id == property_id,
                selected_filter
            )
            .order_by(Booking.check_in)
            .all()
        )

        return make_response(jsonify({
            'status': 'success',
            'data': [booking.to_json() for booking in bookings]
        })), 200

    except Exception as e:
        logging.exception("Error in bookings_by_date: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch bookings.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_bookings')
def get_booking_by_id(property_id, booking_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking = db.session.query(Booking).filter_by(id=booking_id, property_id=property_id).first()

        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found.'
            })), 404

        return make_response(jsonify({
            'status': 'success',
            'data': booking.to_json()
        })), 200

    except Exception as e:
        logging.exception("Error in get_booking_by_id: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch booking.'
        })), 500


# --- HELPER FUNCTION ---
def assign_nightly_rates(booking):
    # Ensure check_in and check_out are datetime.date objects
    if isinstance(booking.check_in, str):
        booking.check_in = datetime.strptime(booking.check_in, "%Y-%m-%dT%H:%M:%S.%f").date()
    if isinstance(booking.check_out, str):
        booking.check_out = datetime.strptime(booking.check_out, "%Y-%m-%dT%H:%M:%S.%f").date()

    current_date = booking.check_in
    total = 0.0

    while current_date < booking.check_out:
        room_online = RoomOnline.query.filter_by(
            room_id=booking.room_id,
            date=current_date
        ).first()

        nightly_rate = room_online.price if room_online else 0.0

        booking.booking_rates.append(
            BookingRate(
                booking_id=booking.id,
                rate_date=current_date,
                nightly_rate=nightly_rate,
            )
        )

        total += nightly_rate
        current_date += timedelta(days=1)

    booking.rate = total