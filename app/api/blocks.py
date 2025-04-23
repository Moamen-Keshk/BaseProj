from flask import request, jsonify, make_response
from . import api
from .. import db
from .models import Block
import logging
from datetime import datetime, timedelta, date


def parse_date(value):
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    elif isinstance(value, (list, tuple)) and len(value) == 3:
        return date(*value)
    elif isinstance(value, date):
        return value
    return None


@api.route('/new_block', methods=['POST'])
def new_block():
    try:
        block_data = request.get_json()
        block = Block.from_json(block_data)
        db.session.add(block)
        update_room_online_for_block(block)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Block created.'
        })), 201

    except ValueError as ve:
        return make_response(jsonify({
            'status': 'fail',
            'message': str(ve)
        })), 400
    except Exception as e:
        logging.exception("Error in new_block: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to create block.'
        })), 500


@api.route('/edit_block/<int:block_id>', methods=['PUT'])
def edit_block(block_id):
    try:
        block_data = request.get_json()
        block = db.session.query(Block).filter_by(id=block_id).first()
        if not block:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Block not found.'
            })), 404

        block.note = block_data.get('note', block.note)
        block.start_date = parse_date(block_data.get('start_date', block.start_date))
        block.end_date = parse_date(block_data.get('end_date', block.end_date))
        block.property_id = block_data.get('property_id', block.property_id)
        block.room_id = block_data.get('room_id', block.room_id)

        block.calculate_fields()
        if block.overlaps_existing_block_or_booking():
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Block overlaps with existing booking or block.'
            })), 400

        db.session.commit()
        return make_response(jsonify({
            'status': 'success',
            'message': 'Block updated successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in edit_block: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update block.'
        })), 500


@api.route('/all_blocks', methods=['GET'])
def all_blocks():
    try:
        property_id = request.args.get('property_id', type=int)
        year = request.args.get('year', type=int)
        month = request.args.get('month', type=int)

        blocks = db.session.query(Block).filter(
            Block.property_id == property_id,
            db.or_(
                Block.start_year == year,
                Block.end_year == year
            ),
            db.or_(
                Block.start_month == month,
                Block.end_month == month
            )
        ).order_by(Block.start_year, Block.start_month, Block.start_day).all()

        return make_response(jsonify({
            'status': 'success',
            'data': [block.to_json() for block in blocks]
        })), 201

    except Exception as e:
        logging.exception("Error in all_blocks: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch blocks.'
        })), 500


@api.route('/delete_block/<int:block_id>', methods=['DELETE'])
def delete_block(block_id):
    try:
        block = db.session.query(Block).filter_by(id=block_id).first()
        if not block:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Block not found.'
            })), 404

        remove_blocked_status_for_block(block)
        db.session.delete(block)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Block deleted successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in delete_block: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete block.'
        })), 500


def update_room_online_for_block(block: Block):
    from .models import RoomOnline  # Import here to avoid circular imports
    from .constants import Constants

    current_date = block.start_date
    while current_date < block.end_date:
        room_online = RoomOnline.query.filter_by(room_id=block.room_id, date=current_date).first()
        if not room_online:
            room_online = RoomOnline(room_id=block.room_id, date=current_date)
            db.session.add(room_online)
        room_online.room_status_id = Constants.RoomStatusCoding['Blocked']
        current_date += timedelta(days=1)


def remove_blocked_status_for_block(block: Block):
    from .models import RoomOnline
    from .constants import Constants

    current_date = block.start_date
    while current_date < block.end_date:
        room_online = RoomOnline.query.filter_by(room_id=block.room_id, date=current_date).first()
        if room_online and room_online.room_status_id == Constants.RoomStatusCoding['Blocked']:
            room_online.room_status_id = Constants.RoomStatusCoding['Available']
        current_date += timedelta(days=1)
