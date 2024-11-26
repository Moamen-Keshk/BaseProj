from flask import request, make_response, jsonify
from . import api
import logging
from .models import Room
from .. import db
from app.auth.views import get_current_user


@api.route('/new-room', methods=['POST'])
def new_room():
    resp = get_current_user()
    if isinstance(resp, str):
        try:
            room = Room.from_json(dict(request.json))
            db.session.add(room)
            db.session.flush()
            db.session.commit()
            responseObject = {
                'status': 'success',
                'message': 'Room added successfully.'
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

@api.route('/all-rooms/<int:property_id>')
def all_rooms(property_id):
    resp = get_current_user()
    if isinstance(resp, str):
        rooms_list = Room.query.filter_by(property_id=property_id).order_by(Room.room_number).all()
        for x in rooms_list:
            rooms_list[rooms_list.index(x)] = x.to_json()
        responseObject = {
            'status': 'success',
            'data': rooms_list,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 201
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401