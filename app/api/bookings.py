import logging
from datetime import timedelta, datetime
from types import SimpleNamespace
from flask import request, make_response, jsonify
from sqlalchemy import or_, and_

from . import api
from app.api.models import Booking, RoomOnline, BookingRate, BookingStatus, GuestMessage, Room
from .. import db
from app.auth.utils import get_current_user
from app.api.decorators import require_permission
from app.api.constants import Constants

# --- CHANNEL MANAGER IMPORTS ---
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

        # ---> Prevent Overbooking / Double Bookings <---
        is_available = check_room_availability(
            room_id=booking.room_id,
            check_in=booking.check_in,
            check_out=booking.check_out
        )

        if not is_available:
            return make_response(jsonify({
                "status": "error",
                "message": "The selected room is already booked for these dates. Please choose different dates or another room."
            })), 409

        # Force the property_id from the secured URL to prevent payload tampering
        booking.property_id = property_id
        booking.creator_id = user_id

        assign_nightly_rates(booking)
        db.session.add(booking)

        # Apply the housekeeping rule for same-day check-ins
        handle_same_day_checkin_housekeeping(booking)

        db.session.commit()

        if booking.email:
            from app.api.utils.guest_communication_task import send_booking_email_task
            send_booking_email_task.delay(booking_id=booking.id, property_id=property_id)

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


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/send_message', methods=['POST', 'OPTIONS'],
           strict_slashes=False)
@require_permission('manage_bookings')
def send_guest_message(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = request.get_json()
        subject = data.get('subject')
        message_body = data.get('message')

        if not subject or not message_body:
            return make_response(jsonify({'status': 'fail', 'message': 'Subject and message are required.'})), 400

        booking = db.session.query(Booking).filter_by(id=booking_id, property_id=property_id).first()

        if not booking or not booking.email:
            return make_response(jsonify({'status': 'fail', 'message': 'Booking or guest email not found.'})), 404

        # Send the custom email
        from app.api.utils.guest_communication_task import send_guest_message
        send_guest_message.delay(
            email=booking.email,
            subject=f"{subject} DO NOT REPLY",
            message_body=message_body,
            property_id=property_id,
            first_name=booking.first_name,
            last_name=booking.last_name
        )

        return make_response(jsonify({'status': 'success', 'message': 'Message sent to guest.'})), 200

    except Exception as e:
        logging.exception("Error in send_guest_message: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to send message.'})), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_bookings')
def edit_booking(property_id, booking_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking_data = request.get_json()

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

        # ==========================================
        # NEW: VERIFY AVAILABILITY BEFORE UPDATING
        # ==========================================
        new_room_id = booking_data.get('room_id', booking.room_id)
        new_check_in_str = booking_data.get('check_in', str(booking.check_in))
        new_check_out_str = booking_data.get('check_out', str(booking.check_out))

        # Safely convert incoming strings to Date objects
        if isinstance(new_check_in_str, str):
            new_check_in = datetime.strptime(new_check_in_str[:10], '%Y-%m-%d').date()
        else:
            new_check_in = new_check_in_str

        if isinstance(new_check_out_str, str):
            new_check_out = datetime.strptime(new_check_out_str[:10], '%Y-%m-%d').date()
        else:
            new_check_out = new_check_out_str

        # Use the reusable helper to check for overlaps, excluding this specific booking ID
        is_available = check_room_availability(
            room_id=new_room_id,
            check_in=new_check_in,
            check_out=new_check_out,
            exclude_booking_id=booking.id
        )

        if not is_available:
            return make_response(jsonify({
                "status": "error",
                "message": "The selected room is already booked for these dates. Please choose different dates or another room."
            })), 409
        # ==========================================

        # Update fields dynamically (amount_paid is already supported here)
        updateable_fields = [
            'first_name', 'last_name', 'email', 'phone', 'number_of_adults',
            'number_of_children', 'payment_status_id', 'status_id', 'note',
            'special_request', 'check_in', 'check_out', 'check_in_day',
            'check_in_month', 'check_in_year', 'check_out_day', 'check_out_month',
            'check_out_year', 'number_of_days', 'rate', 'room_id', 'amount_paid'
        ]

        for field in updateable_fields:
            if field in booking_data:
                setattr(booking, field, booking_data[field])

        BookingRate.query.filter_by(booking_id=booking.id).delete()
        assign_nightly_rates(booking)

        # Automatically resolve the payment status after any rate or payment changes
        booking.update_payment_status()

        handle_same_day_checkin_housekeeping(booking)

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


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>', methods=['DELETE', 'OPTIONS'],
           strict_slashes=False)
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


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/check_in', methods=['POST', 'OPTIONS'],
           strict_slashes=False)
@require_permission('manage_bookings')
def check_in_booking(property_id, booking_id):
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


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/check_out', methods=['POST', 'OPTIONS'],
           strict_slashes=False)
@require_permission('manage_bookings')
def check_out_booking(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking = db.session.query(Booking).filter_by(id=booking_id, property_id=property_id).first()

        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found.'
            })), 404

        checked_out_status = db.session.query(BookingStatus).filter_by(code='CHECKED OUT').first()
        if not checked_out_status:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Checked Out status not configured in the system.'
            })), 500

        booking.change_status(checked_out_status.id)

        room = db.session.query(Room).filter_by(id=booking.room_id).first()
        if room:
            room.cleaning_status_id = Constants.RoomCleaningStatusCoding['Dirty']

        db.session.commit()

        try:
            queue_booking_transition_ari_sync(
                old_property_id=booking.property_id,
                old_room_id=booking.room_id,
                old_check_in=booking.check_in,
                old_check_out=booking.check_out,
                booking=booking,
                reason='booking_checked_out',
            )
        except Exception as sync_err:
            logging.warning(f"Failed to sync checkout to PMS: {sync_err}")

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking status updated to CHECKED OUT.'
        })), 200

    except Exception as e:
        logging.exception("Error in check_out_booking: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update booking status.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/check_extension', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_bookings')
def check_extension(property_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = request.get_json()
        room_id = data.get('room_id')
        current_check_out_str = data.get('current_check_out')
        new_check_out_str = data.get('new_check_out')

        if not all([room_id, current_check_out_str, new_check_out_str]):
            return make_response(jsonify({'status': 'fail', 'message': 'Missing required fields'})), 400

        current_check_out = datetime.strptime(current_check_out_str, '%Y-%m-%d').date()
        new_check_out = datetime.strptime(new_check_out_str, '%Y-%m-%d').date()

        if new_check_out <= current_check_out:
            return make_response(
                jsonify({'status': 'fail', 'message': 'New check-out must be after current check-out'})), 400

        # Step 1: Verify Availability
        overlapping_bookings = db.session.query(Booking).filter(
            Booking.property_id == property_id,
            Booking.room_id == room_id,
            Booking.status_id != 5,  # Exclude cancelled
            Booking.check_in < new_check_out,
            Booking.check_out > current_check_out
        ).count()

        if overlapping_bookings > 0:
            return make_response(jsonify({'status': 'success', 'available': False, 'extra_cost': 0.0})), 200

        # Step 2: Calculate Exact Extra Cost based on RoomOnline daily rates
        extra_cost = 0.0
        curr_date = current_check_out
        while curr_date < new_check_out:
            room_online = RoomOnline.query.filter_by(room_id=room_id, date=curr_date).first()
            if room_online:
                extra_cost += float(room_online.price)
            curr_date += timedelta(days=1)

        return make_response(jsonify({
            'status': 'success',
            'available': True,
            'extra_cost': extra_cost
        })), 200

    except Exception as e:
        logging.exception("Error in check_extension: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to check extension availability.'})), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/extend', methods=['POST', 'OPTIONS'],
           strict_slashes=False)
@require_permission('manage_bookings')
def extend_booking(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = request.get_json()
        new_check_out_str = data.get('new_check_out')
        is_paid = data.get('is_paid', False)
        extra_cost = float(data.get('extra_cost', 0.0))

        if not new_check_out_str:
            return make_response(jsonify({'status': 'fail', 'message': 'New check-out date is required.'})), 400

        booking = db.session.query(Booking).filter_by(id=booking_id, property_id=property_id).first()
        if not booking:
            return make_response(jsonify({'status': 'fail', 'message': 'Booking not found.'})), 404

        new_check_out = datetime.strptime(new_check_out_str, '%Y-%m-%d').date()
        old_check_out = booking.check_out

        if new_check_out <= old_check_out:
            return make_response(
                jsonify({'status': 'fail', 'message': 'New check-out must be after current check-out.'})), 400

        # Step 1: Update core booking dates and total rate
        booking.check_out = new_check_out
        booking.check_out_year = new_check_out.year
        booking.check_out_month = new_check_out.month
        booking.check_out_day = new_check_out.day
        booking.number_of_days = (new_check_out - booking.check_in).days

        # Increase the total bill by the extension cost
        booking.rate = float(booking.rate or 0.0) + extra_cost

        # Step 2: Generate new BookingRate entries for the extended days
        curr_date = old_check_out
        while curr_date < new_check_out:
            room_online = RoomOnline.query.filter_by(room_id=booking.room_id, date=curr_date).first()
            nightly_rate = room_online.price if room_online else 0.0

            booking.booking_rates.append(
                BookingRate(
                    booking_id=booking.id,
                    rate_date=curr_date,
                    nightly_rate=nightly_rate,
                )
            )
            curr_date += timedelta(days=1)

        # 👉 Step 3: THE NEW FINANCIAL LOGIC
        # If the user checked the box saying "Guest paid the extra amount now"
        if is_paid and extra_cost > 0:
            booking.amount_paid = float(booking.amount_paid or 0.0) + extra_cost

        # Auto-resolve the status!
        booking.update_payment_status()

        db.session.commit()

        # Step 4: Notify Channel Manager / PMS sync that dates have shifted
        try:
            queue_booking_transition_ari_sync(
                old_property_id=booking.property_id,
                old_room_id=booking.room_id,
                old_check_in=booking.check_in,
                old_check_out=old_check_out,
                booking=booking,
                reason='booking_extended',
            )
        except Exception as sync_err:
            logging.warning(f"Failed to sync extension to PMS: {sync_err}")

        return make_response(jsonify({'status': 'success', 'message': 'Booking extended successfully.'})), 200

    except Exception as e:
        logging.exception("Error in extend_booking: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to extend booking.'})), 500


@api.route('/properties/<int:property_id>/bookings/by_state', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_bookings')
def bookings_by_date_and_state(property_id):
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


from app.api.models import User, RoomCleaningLog


def handle_same_day_checkin_housekeeping(booking):
    """
    Automatically updates room cleaning status from 'Clean' to 'Refresh'
    if a booking is created/edited for a same-day check-in, provided
    no other booking checks out of that room today.
    """
    today = datetime.today().date()

    # 1. Check if the check-in is scheduled for today
    if booking.check_in == today:
        room = db.session.query(Room).filter_by(id=booking.room_id).first()

        clean_status_id = Constants.RoomCleaningStatusCoding.get('Clean')
        refresh_status_id = Constants.RoomCleaningStatusCoding.get('Refresh')

        # 2. Check if the room is currently clean
        if room and room.cleaning_status_id == clean_status_id:

            # 3. Verify no other booking is checking out today
            checkout_today = db.session.query(Booking).filter(
                Booking.room_id == booking.room_id,
                Booking.check_out == today,
                Booking.id != booking.id,  # Exclude the current booking
                Booking.status_id != 5  # 5 = Canceled (exclude canceled bookings)
            ).first()

            if not checkout_today:
                # Update Room Status
                old_status = room.cleaning_status_id
                room.cleaning_status_id = refresh_status_id
                db.session.add(room)

                # Maintain Audit Log
                user = db.session.query(User).filter_by(uid=booking.creator_id).first()
                user_name = user.username if user else "System Auto-Refresh"

                cleaning_log = RoomCleaningLog(
                    property_id=booking.property_id,
                    room_id=room.id,
                    user_name=user_name,
                    old_status_id=old_status,
                    new_status_id=refresh_status_id
                )
                db.session.add(cleaning_log)

def check_room_availability(room_id, check_in, check_out, exclude_booking_id=None):
    """
    Checks if a room is available for the given dates.
    Returns True if available, False if there is an overlapping booking.
    """
    # Base query: same room, exclude canceled bookings (assuming status_id 5 is Canceled)
    query = db.session.query(Booking).filter(
        Booking.room_id == room_id,
        Booking.status_id != 5,
        Booking.check_in < check_out,  # New booking starts before existing ends
        Booking.check_out > check_in  # New booking ends after existing starts
    )

    # If editing an existing booking, exclude it from the overlap check
    if exclude_booking_id:
        query = query.filter(Booking.id != exclude_booking_id)

    conflicting_booking = query.first()

    return conflicting_booking is None

# ==========================================
# 💬 GUEST COMMUNICATION (CHAT/TWILIO)
# ==========================================

@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/chat', methods=['GET', 'OPTIONS'])
@require_permission('view_bookings')
def get_chat_history(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    messages = GuestMessage.query.filter_by(booking_id=booking_id, property_id=property_id).order_by(
        GuestMessage.timestamp.asc()).all()

    # Mark inbound messages as read since the staff is opening the chat
    unread_messages = [m for m in messages if m.direction == 'inbound' and not m.is_read]
    for msg in unread_messages:
        msg.is_read = True
    if unread_messages:
        db.session.commit()

    return jsonify({'status': 'success', 'data': [m.to_json() for m in messages]}), 200


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/chat', methods=['POST', 'OPTIONS'])
@require_permission('manage_bookings')
def send_chat_message(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    data = request.get_json()
    message_body = data.get('message')
    channel = data.get('channel', 'whatsapp')

    # 1. Save to database INSTANTLY
    chat_log = GuestMessage(
        booking_id=booking_id,
        property_id=property_id,
        direction='outbound',
        channel=channel,
        message_body=message_body,
        is_read=True
    )
    db.session.add(chat_log)
    db.session.commit()

    # 2. Queue Twilio delivery in the background
    from app.api.utils.guest_communication_task import send_sms_whatsapp_task
    send_sms_whatsapp_task.delay(booking_id, property_id, message_body, channel)

    return jsonify({'status': 'success', 'message': 'Message queued.'}), 200


@api.route('/webhooks/twilio/receive', methods=['POST'])
def twilio_webhook():
    # Twilio sends data as form-urlencoded
    from_number = request.form.get('From', '')
    body = request.form.get('Body', '')

    # Clean 'WhatsApp:' prefix if present
    clean_number = from_number.replace('whatsapp:', '')
    channel = 'whatsapp' if 'whatsapp:' in from_number else 'sms'

    # Find the most recent active booking for this phone number
    booking = Booking.query.filter(Booking.phone.like(f"%{clean_number}%")).order_by(Booking.id.desc()).first()

    if booking:
        # Log the inbound message
        inbound_msg = GuestMessage(
            booking_id=booking.id,
            property_id=booking.property_id,
            direction='inbound',
            channel=channel,
            message_body=body,
            is_read=False
        )
        db.session.add(inbound_msg)
        db.session.commit()

    # Twilio requires an empty TwiML response to acknowledge receipt
    from twilio.twiml.messaging_response import MessagingResponse
    return str(MessagingResponse()), 200, {'Content-Type': 'application/xml'}