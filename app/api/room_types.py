import logging

from flask import jsonify, make_response, request

from . import api
from app import db
from app.api.decorators import require_active_staff, require_permission
from app.api.models import RoomType


@api.route('/properties/<int:property_id>/room_types', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_property')
def new_room_type(property_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = dict(request.json or {})
        data['property_id'] = property_id
        room_type = RoomType.from_json(data)
        db.session.add(room_type)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Room type added successfully.',
            'data': room_type.to_json(),
        })), 201
    except Exception as e:
        logging.exception("Error in new_room_type: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to add room type.',
        })), 500


@api.route('/properties/<int:property_id>/room_types/<int:room_type_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_property')
def edit_room_type(property_id, room_type_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = request.get_json() or {}
        room_type = RoomType.query.filter_by(id=room_type_id, property_id=property_id).first()
        if not room_type:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Room type not found.',
            })), 404

        if 'name' in data and data['name']:
            room_type.name = data['name'].strip()
        if 'description' in data:
            room_type.description = (data['description'] or '').strip()
        if 'max_guests' in data or 'capacity' in data:
            room_type.max_guests = int(data.get('max_guests') or data.get('capacity') or room_type.max_guests)
        if 'max_adults' in data:
            room_type.max_adults = int(data['max_adults'])
        if 'max_children' in data:
            room_type.max_children = int(data['max_children'])
        if 'max_infants' in data:
            room_type.max_infants = int(data['max_infants'])
        if 'is_active' in data:
            room_type.is_active = bool(data['is_active'])

        db.session.commit()
        return make_response(jsonify({
            'status': 'success',
            'message': 'Room type updated successfully.',
            'data': room_type.to_json(),
        })), 200
    except Exception as e:
        logging.exception("Error in edit_room_type: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update room type.',
        })), 500


@api.route('/properties/<int:property_id>/room_types', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def all_room_types(property_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        room_types = RoomType.query.filter_by(property_id=property_id).order_by(RoomType.name).all()
        return make_response(jsonify({
            'status': 'success',
            'data': [item.to_json() for item in room_types],
            'page': 0,
        })), 200
    except Exception as e:
        logging.exception("Error in all_room_types: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch room types.',
        })), 500


@api.route('/properties/<int:property_id>/room_types/<int:room_type_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_property')
def delete_room_type(property_id, room_type_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        room_type = RoomType.query.filter_by(id=room_type_id, property_id=property_id).first()
        if not room_type:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Room type not found.',
            })), 404

        db.session.delete(room_type)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Room type deleted successfully.',
        })), 200
    except Exception as e:
        logging.exception("Error in delete_room_type: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete room type. It might still be linked to rooms or rates.',
        })), 500
