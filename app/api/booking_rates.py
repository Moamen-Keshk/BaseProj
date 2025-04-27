from flask import request, make_response, jsonify
from . import api
from .. import db
from .models import BookingRate
from app.auth.views import get_current_user
import logging


@api.route('/booking_rates/<int:booking_id>', methods=['GET'])
def get_booking_rates_for_booking(booking_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return _unauthorized_response()

        booking_rates = BookingRate.query.filter_by(booking_id=booking_id).order_by(BookingRate.rate_date).all()

        return make_response(jsonify({
            'status': 'success',
            'data': [rate.to_json() for rate in booking_rates]
        })), 201

    except Exception as e:
        logging.exception("Error in get_booking_rates_for_booking: %s", str(e))
        return _server_error("Failed to retrieve booking rates.")


@api.route('/new_booking_rate', methods=['POST'])
def create_booking_rate():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return _unauthorized_response()

        data = request.get_json()
        booking_rate = BookingRate.from_json(data)

        db.session.add(booking_rate)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking rate added successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in create_booking_rate: %s", str(e))
        return _server_error("Failed to add booking rate.")


@api.route('/delete_booking_rate/<int:rate_id>', methods=['DELETE'])
def delete_booking_rate(rate_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return _unauthorized_response()

        rate = BookingRate.query.get(rate_id)
        if not rate:
            return _not_found("Booking rate not found.")

        db.session.delete(rate)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking rate deleted successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in delete_booking_rate: %s", str(e))
        return _server_error("Failed to delete booking rate.")


# 🔧 Common response helpers
def _unauthorized_response():
    return make_response(jsonify({
        'status': 'fail',
        'message': 'Unauthorized access.'
    })), 401


def _not_found(msg):
    return make_response(jsonify({
        'status': 'fail',
        'message': msg
    })), 404


def _server_error(msg):
    return make_response(jsonify({
        'status': 'error',
        'message': msg
    })), 500
