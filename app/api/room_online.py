from flask import request, make_response, jsonify
from . import api
import logging
from types import SimpleNamespace
from app.api.models import RoomOnline
from .. import db
from app.auth.utils import get_current_user
from datetime import datetime
from app.api.channel_manager.services.pms_sync import (
    queue_room_online_ari_sync,
    queue_room_online_transition_ari_sync,
)


@api.route('/new_room_online', methods=['POST'])
def new_room_online():
    resp = get_current_user()
    if isinstance(resp, str):
        try:
            data = dict(request.json)
            room_id = data.get('room_id')
            date = datetime.fromisoformat(data.get('date')).date()
            property_id = data.get('property_id')
            category_id = data.get('category_id')

            if not all([room_id, date, property_id, category_id]):
                return make_response(jsonify({
                    'status': 'fail',
                    'message': 'Missing required fields (room_id, date, property_id, category_id).'
                })), 400

            existing = RoomOnline.query.filter_by(
                room_id=room_id,
                date=date,
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
            return make_response(jsonify({
                'status': 'error',
                'message': 'Failed to add room online.'
            })), 500

    return make_response(jsonify({
        'status': 'expired',
        'message': 'Session expired, log in required!'
    })), 401


@api.route('/update_room_online/<int:rate_id>', methods=['PUT'])
def update_room_online(rate_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        data = request.get_json()
        room_online = RoomOnline.query.get(rate_id)
        if not room_online:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Room rate not found.'
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
        if 'property_id' in data:
            room_online.property_id = data['property_id']
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
        })), 201

    except Exception as e:
        logging.exception("Error updating room online: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update room online.'
        })), 500


@api.route('/delete_room_online/<int:rate_id>', methods=['DELETE'])
def delete_room_online(rate_id):
    try:
        user = get_current_user()
        if not isinstance(user, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        room_online = RoomOnline.query.get(rate_id)
        if not room_online:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Room online not found.'
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
        })), 201

    except Exception as e:
        logging.exception("Error deleting room online: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete room online.'
        })), 500


@api.route('/all_room_online/<int:property_id>', methods=['GET'])
def all_room_online(property_id):
    resp = get_current_user()
    if isinstance(resp, str):
        try:
            room_online = RoomOnline.query.filter_by(property_id=property_id).order_by(RoomOnline.date).all()
            return make_response(jsonify({
                'status': 'success',
                'data': [rate.to_json() for rate in room_online]
            })), 201
        except Exception as e:
            logging.exception("Error fetching room online: %s", str(e))
            return make_response(jsonify({
                'status': 'error',
                'message': 'Could not fetch room online.'
            })), 500

    return make_response(jsonify({
        'status': 'fail',
        'message': resp
    })), 401


@api.route('/room_online_by_category', methods=['GET'])
def room_online_by_category():
    user = get_current_user()
    if not isinstance(user, str):
        return make_response(jsonify({
            'status': 'fail',
            'message': 'Unauthorized access.'
        })), 401

    try:
        property_id = request.args.get('property_id', type=int)
        category_id = request.args.get('category_id')

        if not property_id or not category_id:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Missing property_id or category_id'
            })), 400

        rooms = RoomOnline.query.filter_by(
            property_id=property_id,
            category_id=category_id
        ).order_by(RoomOnline.date).all()

        return make_response(jsonify({
            'status': 'success',
            'data': [r.to_json() for r in rooms]
        })), 201

    except Exception as e:
        logging.exception("Error fetching room online by category: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Could not fetch room rates.'
        })), 500