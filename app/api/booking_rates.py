import logging
from flask import request, make_response, jsonify

from . import api
from .. import db
from app.api.models import BookingRate, Booking
from app.api.decorators import require_permission


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/rates', methods=['GET'])
@require_permission('view_bookings')
def get_booking_rates_for_booking(property_id, booking_id):
    try:
        # Security check: Ensure the booking actually belongs to this property
        booking = Booking.query.filter_by(id=booking_id, property_id=property_id).first()
        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found in this property.'
            })), 404

        booking_rates = BookingRate.query.filter_by(booking_id=booking_id).order_by(BookingRate.rate_date).all()

        return make_response(jsonify({
            'status': 'success',
            'data': [rate.to_json() for rate in booking_rates]
        })), 200

    except Exception as e:
        logging.exception("Error in get_booking_rates_for_booking: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to retrieve booking rates.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/rates', methods=['POST'])
@require_permission('manage_bookings')
def create_booking_rate(property_id, booking_id):
    try:
        # Security check: Ensure the booking actually belongs to this property
        booking = Booking.query.filter_by(id=booking_id, property_id=property_id).first()
        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found in this property.'
            })), 404

        data = request.get_json()
        # Force the booking_id to match the secured URL
        data['booking_id'] = booking_id

        booking_rate = BookingRate.from_json(data)

        db.session.add(booking_rate)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking rate added successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in create_booking_rate: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to add booking rate.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/rates/<int:rate_id>', methods=['DELETE'])
@require_permission('manage_bookings')
def delete_booking_rate(property_id, booking_id, rate_id):
    try:
        # Security check: Ensure the booking actually belongs to this property
        booking = Booking.query.filter_by(id=booking_id, property_id=property_id).first()
        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found in this property.'
            })), 404

        rate = BookingRate.query.filter_by(id=rate_id, booking_id=booking_id).first()
        if not rate:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking rate not found.'
            })), 404

        db.session.delete(rate)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking rate deleted successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error in delete_booking_rate: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete booking rate.'
        })), 500