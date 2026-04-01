import logging
from datetime import datetime
from types import SimpleNamespace

from flask import request, make_response, jsonify
from . import api
from app.api.models import RoomOnline
from .. import db
from app.api.decorators import require_permission
from app.api.channel_manager.services.pms_sync import (
    queue_room_online_ari_sync,
    queue_room_online_transition_ari_sync,
)


@api.route('/properties/<int:property_id>/room_online', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def new_room_online(property_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = dict(request.json)
        # Force property_id from the secured URL
        data['property_id'] = property_id

        room_id = data.get('room_id')
        date_str = data.get('date')
        category_id = data.get('category_id')

        if not all([room_id, date_str, category_id]):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Missing required fields (room_id, date, category_id).'
            })), 400

        target_date = datetime.fromisoformat(date_str).date()

        existing = RoomOnline.query.filter_by(
            room_id=room_id,
            date=target_date,
            property_id=property_id
        ).first()

        if existing:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Rate already exists for this room on the selected date.',
                'existing_rate': existing.to_json()
            })), 409

        room_online = RoomOnline.from_json(data)
        db.session.add(room_online)
        db.session.commit()

        queue_room_online_ari_sync(room_online, 'room_online_created')

        return make_response(jsonify({
            'status': 'success',
            'message': 'Room online added successfully.',
            'data': room_online.to_json()
        })), 201

    except Exception as e:
        logging.exception("Error adding room online: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to add room online.'
        })), 500


@api.route('/properties/<int:property_id>/room_online/<int:rate_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def update_room_online(property_id, rate_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = request.get_json()

        # Ensure the rate exists and belongs to this property
        room_online = RoomOnline.query.filter_by(id=rate_id, property_id=property_id).first()
        if not room_online:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Room rate not found in this property.'
            })), 404

        old_property_id = room_online.property_id
        old_room_id = room_online.room_id
        old_date = room_online.date

        if 'price' in data:
            room_online.price = data['price']
        if 'date' in data:
            room_online.date = datetime.fromisoformat(data['date']).date()
        if 'category_id' in data:
            room_online.category_id = data['category_id']
        if 'room_id' in data:
            room_online.room_id = data['room_id']
        if 'room_status_id' in data:
            room_online.room_status_id = data['room_status_id']

        db.session.commit()

        queue_room_online_transition_ari_sync(
            old_property_id=old_property_id,
            old_room_id=old_room_id,
            old_date=old_date,
            room_online=room_online,
            reason='room_online_updated',
        )

        return make_response(jsonify({
            'status': 'success',
            'message': 'Room online updated successfully.',
            'data': room_online.to_json()
        })), 200

    except Exception as e:
        logging.exception("Error updating room online: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update room online.'
        })), 500


@api.route('/properties/<int:property_id>/room_online/<int:rate_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def delete_room_online(property_id, rate_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        room_online = RoomOnline.query.filter_by(id=rate_id, property_id=property_id).first()
        if not room_online:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Room online not found in this property.'
            })), 404

        old_property_id = room_online.property_id
        old_room_id = room_online.room_id
        old_date = room_online.date

        db.session.delete(room_online)
        db.session.commit()

        deleted_snapshot = SimpleNamespace(
            property_id=old_property_id,
            room_id=old_room_id,
            date=old_date,
        )

        queue_room_online_ari_sync(deleted_snapshot, 'room_online_deleted')

        return make_response(jsonify({
            'status': 'success',
            'message': 'Room online deleted successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error deleting room online: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete room online.'
        })), 500


@api.route('/properties/<int:property_id>/room_online', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_rates')
def all_room_online(property_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        room_online = RoomOnline.query.filter_by(property_id=property_id).order_by(RoomOnline.date).all()
        return make_response(jsonify({
            'status': 'success',
            'data': [rate.to_json() for rate in room_online]
        })), 200

    except Exception as e:
        logging.exception("Error fetching room online: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Could not fetch room online.'
        })), 500


@api.route('/properties/<int:property_id>/room_online/by_category', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_rates')
def room_online_by_category(property_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        category_id = request.args.get('category_id')

        if not category_id:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Missing category_id'
            })), 400

        rooms = RoomOnline.query.filter_by(
            property_id=property_id,
            category_id=category_id
        ).order_by(RoomOnline.date).all()

        return make_response(jsonify({
            'status': 'success',
            'data': [r.to_json() for r in rooms]
        })), 200

    except Exception as e:
        logging.exception("Error fetching room online by category: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Could not fetch room rates.'
        })), 500