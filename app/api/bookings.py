from flask import request, make_response, jsonify
from sqlalchemy import or_, and_
from . import api
import logging
from .models import Booking, RoomOnline, BookingRate, BookingStatus
from .. import db
from app.auth.views import get_current_user
from datetime import timedelta, datetime

@api.route('/new_booking', methods=['POST'])
def new_booking():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'expired',
                'message': 'Session expired, log in required!'
            })), 401

        booking_data = request.get_json()
        try:
            booking = Booking.from_json(booking_data)
        except ValueError as ve:
            print(str(ve))
            return make_response(jsonify({
                'status': 'fail',
                'message': str(ve)
            })), 400

        booking.creator_id = user_id
        assign_nightly_rates(booking)
        db.session.add(booking)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking submitted successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in new_booking: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to submit booking. Please try again.'
        })), 500

@api.route('/edit_booking/<int:booking_id>', methods=['PUT'])
def edit_booking(booking_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        booking_data = request.get_json()

        booking = db.session.query(Booking).filter_by(id=booking_id, creator_id=user_id).first()
        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found or you do not have permission to edit it.'
            })), 404

        if 'first_name' in booking_data:
            booking.first_name = booking_data['first_name']
        if 'last_name' in booking_data:
            booking.last_name = booking_data['last_name']
        if 'email' in booking_data:
            booking.email = booking_data['email']
        if 'phone' in booking_data:
            booking.phone = booking_data['phone']
        if 'number_of_adults' in booking_data:
            booking.number_of_adults = booking_data['number_of_adults']
        if 'number_of_children' in booking_data:
            booking.number_of_children = booking_data['number_of_children']
        if 'payment_status_id' in booking_data:
            booking.payment_status_id = booking_data['payment_status_id']
        if 'status_id' in booking_data:
            booking.status_id = booking_data['status_id']
        if 'note' in booking_data:
            booking.note = booking_data['note']
        if 'special_request' in booking_data:
            booking.special_request = booking_data['special_request']
        if 'check_in' in booking_data:
            booking.check_in = booking_data['check_in']
        if 'check_out' in booking_data:
            booking.check_out = booking_data['check_out']
        if 'check_in_day' in booking_data:
            booking.check_in_day = booking_data['check_in_day']
        if 'check_in_month' in booking_data:
            booking.check_in_month = booking_data['check_in_month']
        if 'check_in_year' in booking_data:
            booking.check_in_year = booking_data['check_in_year']
        if 'check_out_day' in booking_data:
            booking.check_out_day = booking_data['check_out_day']
        if 'check_out_month' in booking_data:
            booking.check_out_month = booking_data['check_out_month']
        if 'check_out_year' in booking_data:
            booking.check_out_year = booking_data['check_out_year']
        if 'number_of_days' in booking_data:
            booking.number_of_days = booking_data['number_of_days']
        if 'rate' in booking_data:
            booking.rate = booking_data['rate']
        if 'room_id' in booking_data:
            booking.room_id = booking_data['room_id']

        BookingRate.query.filter_by(booking_id=booking.id).delete()
        assign_nightly_rates(booking)

        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking updated successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in edit_booking: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update booking. Please try again.'
        })), 500

@api.route('/all-bookings', methods=['GET'])
def all_bookings():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        property_id = request.args.get('property_id', type=int)
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
        })), 201
    except Exception as e:
        logging.exception("Error in all_bookings: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch bookings.'
        })), 500

@api.route('/delete_booking/<int:booking_id>', methods=['DELETE'])
def delete_booking(booking_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        booking = db.session.query(Booking).filter_by(id=booking_id).first()

        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found or permission denied.'
            })), 404

        db.session.delete(booking)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking deleted successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in delete_booking: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete booking. Please try again.'
        })), 500

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



@api.route('/check_in_booking/<int:booking_id>', methods=['POST'])
def check_in_booking(booking_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        booking = db.session.query(Booking).filter_by(id=booking_id).first()

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
        })), 201

    except Exception as e:
        logging.exception("Error in check_in_booking: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update booking status.'
        })), 500

@api.route('/bookings_by_date', methods=['GET'])
def bookings_by_date():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        property_id = request.args.get('property_id', type=int)
        date_str = request.args.get('date')  # Expecting 'YYYY-MM-DD'

        if not property_id or not date_str:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Missing property_id or date parameter.'
            })), 400

        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Invalid date format. Expected YYYY-MM-DD.'
            })), 400

        # Fetch bookings with check_in or check_out equal to the date
        bookings = db.session.query(Booking).filter(
            Booking.property_id == property_id,
            or_(
                Booking.check_in == target_date,
                Booking.check_out == target_date
            )
        ).order_by(Booking.check_in).all()

        response_data = [booking.to_json() for booking in bookings]

        return make_response(jsonify({
            'status': 'success',
            'data': response_data
        })), 201

    except Exception as e:
        logging.exception("Error in bookings_by_date: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch bookings.'
        })), 500


@api.route('/booking/<int:booking_id>', methods=['GET'])
def get_booking_by_id(booking_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        booking = db.session.query(Booking).filter_by(id=booking_id).first()

        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found.'
            })), 404

        return make_response(jsonify({
            'status': 'success',
            'data': booking.to_json()
        })), 201

    except Exception as e:
        logging.exception("Error in get_booking_by_id: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch booking.'
        })), 500
