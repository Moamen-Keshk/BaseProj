import logging
from flask import request, make_response, jsonify
from . import api
from app.api.models import Room
from .. import db
from app.api.decorators import require_permission, require_active_staff


@api.route('/properties/<int:property_id>/rooms', methods=['POST'])
@require_permission('manage_property')
def new_room(property_id):
    try:
        room_data = dict(request.json)
        # Enforce property ID from the secured URL
        room_data['property_id'] = property_id

        room = Room.from_json(room_data)
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
        db.session.rollback()
        responseObject = {
            'status': 'error',
            'message': 'Some error occurred. Please try again.'
        }
        return make_response(jsonify(responseObject)), 500


@api.route('/properties/<int:property_id>/rooms/<int:room_id>', methods=['PUT'])
@require_permission('manage_property')
def edit_room(property_id, room_id):
    """Full edit access for Property Admins"""
    try:
        room_data = request.get_json()

        # Find the room by ID and ensure it belongs to this property
        room = db.session.query(Room).filter_by(id=room_id, property_id=property_id).first()
        if not room:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Room not found in this property.'
            })), 404

        # Update room fields
        if 'room_number' in room_data:
            room.room_number = room_data['room_number']
        if 'category_id' in room_data:
            room.category_id = room_data['category_id']
        if 'floor_id' in room_data:
            room.floor_id = room_data['floor_id']
        if 'status_id' in room_data:
            room.status_id = room_data['status_id']

        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Room updated successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error in edit_room: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update room. Please try again.'
        })), 500


@api.route('/properties/<int:property_id>/rooms/<int:room_id>/status', methods=['PUT'])
@require_permission('update_room_status')
def update_room_status(property_id, room_id):
    """Dedicated route for Housekeeping and Front Desk to mark rooms Clean/Dirty"""
    try:
        room_data = request.get_json()

        room = db.session.query(Room).filter_by(id=room_id, property_id=property_id).first()
        if not room:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Room not found in this property.'
            })), 404

        if 'status_id' in room_data:
            room.status_id = room_data['status_id']
            db.session.commit()

            return make_response(jsonify({
                'status': 'success',
                'message': 'Room status updated successfully.'
            })), 200
        else:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'status_id is required.'
            })), 400

    except Exception as e:
        logging.exception("Error in update_room_status: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update room status. Please try again.'
        })), 500


@api.route('/properties/<int:property_id>/rooms', methods=['GET'])
@require_active_staff
def all_rooms(property_id):
    """Allows any active staff member to view the rooms (Read-Only)"""
    try:
        rooms_list = Room.query.filter_by(property_id=property_id).order_by(Room.room_number).all()

        serialized_rooms = [room.to_json() for room in rooms_list]

        responseObject = {
            'status': 'success',
            'data': serialized_rooms,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 200

    except Exception as e:
        logging.exception(e)
        responseObject = {
            'status': 'error',
            'message': 'Failed to fetch rooms.'
        }
        return make_response(jsonify(responseObject)), 500


@api.route('/properties/<int:property_id>/rooms/<int:room_id>', methods=['DELETE'])
@require_permission('manage_property')
def delete_room(property_id, room_id):
    try:
        room = db.session.query(Room).filter_by(id=room_id, property_id=property_id).first()
        if not room:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Room not found in this property.'
            })), 404

        db.session.delete(room)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Room deleted successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error in delete_room: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete room. Please try again.'
        })), 500