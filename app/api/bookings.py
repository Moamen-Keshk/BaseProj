from flask import request, make_response, jsonify
from sqlalchemy import or_, and_
from . import api
import logging
from .models import Booking
from .. import db
from app.auth.views import get_current_user

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
        booking = Booking.from_json(booking_data)
        booking.creator_id = user_id
        db.session.add(booking)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking submitted.'
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
        # Get the current user ID and ensure they are authorized
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        # Fetch the booking data from the request
        booking_data = request.get_json()

        # Find the booking by ID
        booking = db.session.query(Booking).filter_by(id=booking_id, creator_id=user_id).first()
        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found or you do not have permission to edit it.'
            })), 404

        # Update booking fields
        if 'first_name' in booking_data:
            booking.first_name = booking_data['first_name']
        if 'last_name' in booking_data:
            booking.last_name = booking_data['last_name']
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

        # Additional fields can be updated here
        # ...

        # Save changes to the database
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

#        if not (property_id and check_in_year and check_in_month):
#            return make_response(jsonify({
#                'status': 'fail',
#                'message': 'Missing required query parameters.'
#            })), 400

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
