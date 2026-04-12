import logging
from flask import request, make_response, jsonify
from . import api
from app.api.models import Floor, Room
from .. import db
from app.api.decorators import require_permission, require_active_staff


@api.route('/properties/<int:property_id>/floors', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_property')
def new_floor(property_id):
    try:
        floor_data = dict(request.json)
        # Enforce the property ID from the secured URL
        floor_data['property_id'] = property_id

        floor = Floor.from_json(floor_data)
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
        db.session.rollback()
        responseObject = {
            'status': 'error',
            'message': 'Some error occurred. Please try again.'
        }
        return make_response(jsonify(responseObject)), 500


@api.route('/properties/<int:property_id>/floors/<int:floor_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_property')
def edit_floor(property_id, floor_id):
    try:
        floor_data = request.get_json()

        # Find the floor by ID and ensure it belongs to this property
        floor = db.session.query(Floor).filter_by(id=floor_id, property_id=property_id).first()
        if not floor:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Floor not found in this property.'
            })), 404

        # Update floor fields
        if 'floor_number' in floor_data:
            floor.floor_number = floor_data['floor_number']

        if 'rooms' in floor_data:
            for room_data in floor_data['rooms']:
                # Update existing room or create a new one
                if 'id' in room_data and room_data['id']:
                    room = db.session.query(Room).filter_by(id=room_data['id'], floor_id=floor.id).first()
                    if room:
                        if 'room_number' in room_data:
                            room.room_number = room_data['room_number']
                        if 'room_type_id' in room_data or 'category_id' in room_data:
                            room.room_type_id = room_data.get('room_type_id', room_data.get('category_id'))
                else:
                    new_room = Room.from_json(room_data)
                    floor.rooms.append(new_room)

        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Floor updated successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error in edit_floor: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update floor. Please try again.'
        })), 500


@api.route('/properties/<int:property_id>/floors', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def all_floors(property_id):
    """Allows any active staff member to view the floors (Read-Only)"""
    try:
        floors_list = Floor.query.filter_by(property_id=property_id).order_by(Floor.floor_number).all()

        serialized_floors = [floor.to_json() for floor in floors_list]

        responseObject = {
            'status': 'success',
            'data': serialized_floors,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 200

    except Exception as e:
        logging.exception(e)
        responseObject = {
            'status': 'error',
            'message': 'Failed to fetch floors.'
        }
        return make_response(jsonify(responseObject)), 500


@api.route('/properties/<int:property_id>/floors/<int:floor_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_property')
def delete_floor(property_id, floor_id):
    try:
        # Enforce property check
        floor = Floor.query.filter_by(id=floor_id, property_id=property_id).first()

        if not floor:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Floor not found in this property.'
            })), 404

        db.session.delete(floor)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Floor deleted successfully.'
        })), 200

    except Exception as e:
        logging.exception("An error occurred: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete floor. Please try again.'
        })), 500
