from flask import request, make_response, jsonify
from sqlalchemy.orm import session

from . import api
import logging
from .models import Booking
from sqlalchemy import extract
from .. import db
from app.auth.views import get_current_user

@api.route('/new_booking', methods=['POST'])
def new_booking():
    resp = get_current_user()
    if isinstance(resp, str):
        try:
            booking = Booking.from_json(dict(request.json))
            booking.creator_id = resp
            db.session.add(booking)
            db.session.flush()
            db.session.commit()
            responseObject = {
                'status': 'success',
                'message': 'Booking submitted.'
            }
            return make_response(jsonify(responseObject)), 201
        except Exception as e:
            logging.exception(e)
            responseObject = {
                'status': 'error',
                'message': 'Some error occurred. Please try again.'
            }
            return make_response(jsonify(responseObject)), 401
    responseObject = {
        'status': 'expired',
        'message': 'Session expired, log in required!'
    }
    return make_response(jsonify(responseObject)), 202

@api.route('/all-bookings')
def all_bookings():
    resp = get_current_user()
    if isinstance(resp, str):
        bookings_list = Booking.query.filter_by(property_id=int(request.args.get('property_id')),
                                                check_in_year=int(request.args.get('check_in_year')),
                                                check_in_month=int(request.args.get('check_in_month'))
                                                ).order_by(Booking.check_in_day).all()
        for x in bookings_list:
            bookings_list[bookings_list.index(x)] = x.to_json()
        responseObject = {
            'status': 'success',
            'data': bookings_list,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 201
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401