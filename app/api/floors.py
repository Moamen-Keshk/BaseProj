from flask import request, make_response, jsonify
from . import api
import logging
from .models import Floor, Room
from .. import db
from app.auth.views import get_current_user


@api.route('/new-floor', methods=['POST'])
def new_floor():
    resp = get_current_user()
    if isinstance(resp, str):
        try:
            floor = Floor.from_json(dict(request.json))
            db.session.add(floor)
            db.session.flush()
            db.session.commit()
            responseObject = {
                'status': 'success',
                'message': 'Floor added successfully.'
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


@api.route('/edit_floor/<int:floor_id>', methods=['PUT'])
def edit_floor(floor_id):
    try:
        # Get the current user ID and ensure they are authorized
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        # Fetch the booking data from the request
        floor_data = request.get_json()

        # Find the booking by ID
        floor = db.session.query(Floor).filter_by(id=floor_id).first()
        if not floor:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Floor not found or you do not have permission to edit it.'
            })), 404

        # Update booking fields
        if 'floor_number' in floor_data:
            floor.floor_number = floor_data['floor_number']
        if 'property_id' in floor_data:
            floor.property_id = floor_data['property_id']
        if 'rooms' in floor_data:
            for room_data in floor_data['rooms']:
                # Assuming you have a Room.from_json method
                room = db.session.query(Room).filter_by(id=room_data['id']).first()
                if not room:
                    new_room = Room.from_json(room_data)
                    floor.rooms.append(new_room)

                else:# Update booking fields
                    if 'room_number' in room_data:
                        room.room_number = room_data['room_number']
                    if 'category_id' in room_data:
                        room.category_id = room_data['category_id']


        # Additional fields can be updated here
        # ...

        # Save changes to the database
        db.session.flush()
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Floor updated successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in edit_floor: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update floor. Please try again.'
        })), 500


@api.route('/all-floors/<int:property_id>')
def all_floors(property_id):
    resp = get_current_user()
    if isinstance(resp, str):
        floors_list = Floor.query.filter_by(property_id=property_id).order_by(Floor.floor_number).all()
        for x in floors_list:
            floors_list[floors_list.index(x)] = x.to_json()
        responseObject = {
            'status': 'success',
            'data': floors_list,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 201
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401