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

@api.route('/edit_room/<int:room_id>', methods=['PUT'])
def edit_room(room_id):
    try:
        # Get the current user ID and ensure they are authorized
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        # Fetch the booking data from the request
        room_data = request.get_json()

        # Find the booking by ID
        room = db.session.query(Room).filter_by(id=room_id, creator_id=user_id).first()
        if not room:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Room not found or you do not have permission to edit it.'
            })), 404

        # Update booking fields
        if 'room_number' in room_data:
            room.room_number = room_data['room_number']
        if 'property_id' in room_data:
            room.property_id = room_data['property_id']
        if 'category_id' in room_data:
            room.category_id = room_data['category_id']
        if 'floor_id' in room_data:
            room.floor_id = room_data['floor_id']
        if 'status_id' in room_data:
            room.status_id = room_data['status_id']

        # Additional fields can be updated here
        # ...

        # Save changes to the database
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Room updated successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in edit_room: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update room. Please try again.'
        })), 500

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

@api.route('/delete_room/<int:room_id>', methods=['DELETE'])
def delete_room(room_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        # Check if room exists and belongs to the user
        room = db.session.query(Room).filter_by(id=room_id).first()
        if not room:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Room not found or you do not have permission to delete it.'
            })), 404

        db.session.delete(room)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Room deleted successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in delete_room: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete room. Please try again.'
        })), 500
