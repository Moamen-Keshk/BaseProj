from flask import request, jsonify, make_response
from . import api
from .. import db
from .models import Block, Room, RoomOnline, RatePlan, Season, Booking
from .constants import Constants
from datetime import datetime, timedelta, date
import logging


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

        update_room_online_for_block(block)
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
            db.or_(Block.start_year == year, Block.end_year == year),
            db.or_(Block.start_month == month, Block.end_month == month)
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


def update_room_online_for_block(block):
    current_date = block.start_date
    room = Room.query.get(block.room_id)
    if not room:
        raise ValueError("Room not found for block")

    rate_plans = RatePlan.query.filter_by(
        property_id=block.property_id,
        category_id=room.category_id,
        is_active=True
    ).all()

    seasons = Season.query.filter_by(property_id=block.property_id).all()

    while current_date < block.end_date:
        room_online = RoomOnline.query.filter_by(
            room_id=block.room_id,
            date=current_date
        ).first()

        if not room_online:
            price = resolve_price_for_block(
                room_date=current_date,
                rate_plans=rate_plans,
                seasons=seasons
            )

            room_online = RoomOnline(
                room_id=block.room_id,
                property_id=block.property_id,
                category_id=room.category_id,
                date=current_date,
                price=price,
                room_status_id=Constants.RoomStatusCoding['Blocked'],
            )
            db.session.add(room_online)
        else:
            room_online.room_status_id = Constants.RoomStatusCoding['Blocked']

        current_date += timedelta(days=1)

    db.session.commit()


def resolve_price_for_block(room_date, rate_plans, seasons):
    plan = next((rp for rp in rate_plans if rp.start_date <= room_date <= rp.end_date), None)
    if not plan:
        return 0.0

    is_weekend = room_date.weekday() in [5, 6]
    base_price = plan.weekend_rate if is_weekend and plan.weekend_rate else plan.base_rate

    in_season = any(season.start_date <= room_date <= season.end_date for season in seasons)
    if in_season and plan.seasonal_multiplier:
        base_price *= plan.seasonal_multiplier

    return base_price


def remove_blocked_status_for_block(block):
    current_date = block.start_date
    while current_date < block.end_date:
        room_online = RoomOnline.query.filter_by(
            room_id=block.room_id,
            date=current_date
        ).first()

        if room_online and room_online.room_status_id == Constants.RoomStatusCoding['Blocked']:
            overlapping_booking = Booking.query.filter(
                Booking.room_id == block.room_id,
                Booking.check_in <= current_date,
                Booking.check_out > current_date
            ).first()

            overlapping_block = Block.query.filter(
                Block.id != block.id,
                Block.room_id == block.room_id,
                Block.start_date <= current_date,
                Block.end_date > current_date
            ).first()

            if not overlapping_booking and not overlapping_block:
                room_online.room_status_id = Constants.RoomStatusCoding['Available']

        current_date += timedelta(days=1)

    db.session.commit()