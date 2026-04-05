import logging
from flask import request, make_response, jsonify
from . import api
from app.api.models import BookingStatus
from .. import db
from app.api.decorators import require_active_staff


@api.route('/booking-statuses', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def new_booking_status():
    # 👉 Catch CORS preflight requests before they are processed
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = dict(request.json)

        # Validation
        if not data or 'name' not in data or not data['name'].strip():
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking status name is required.'
            })), 400

        if 'code' not in data or not data['code'].strip():
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking status code is required.'
            })), 400

        # Optional color field
        color_raw = data.get('color')
        color = color_raw.strip() if color_raw else ''

        status = BookingStatus(
            name=data['name'].strip(),
            code=data['code'].strip(),
            color=color
        )

        db.session.add(status)
        db.session.flush()
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking status added successfully.'
        })), 201

    except Exception as e:
        logging.exception(e)
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Some error occurred. Please try again.'
        })), 500


@api.route('/booking-statuses/<int:status_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def edit_booking_status(status_id):
    # 👉 Catch CORS preflight
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = request.get_json()
        status = db.session.query(BookingStatus).filter_by(id=status_id).first()

        if not status:
            return make_response(jsonify({'status': 'fail', 'message': 'Booking status not found.'})), 404

        if 'name' in data and data['name'] and data['name'].strip():
            status.name = data['name'].strip()

        if 'code' in data and data['code'] and data['code'].strip():
            status.code = data['code'].strip()

        if 'color' in data:
            color_raw = data['color']
            status.color = color_raw.strip() if color_raw else ''

        db.session.commit()
        return make_response(jsonify({'status': 'success', 'message': 'Booking status updated successfully.'})), 200

    except Exception as e:
        logging.exception("Error in edit_booking_status: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to update booking status.'})), 500


@api.route('/booking-statuses', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def all_booking_statuses():
    # 👉 Catch CORS preflight
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    """Allows any active staff member to view global booking statuses (Read-Only)"""
    try:
        statuses_list = BookingStatus.query.order_by(BookingStatus.id).all()

        # Explicit serialization just in case BookingStatus doesn't have a to_json() method defined
        serialized_statuses = [
            {
                'id': stat.id,
                'code': stat.code,
                'name': stat.name,
                'color': stat.color
            } for stat in statuses_list
        ]

        return make_response(jsonify({
            'status': 'success',
            'data': serialized_statuses,
            'page': 0
        })), 200

    except Exception as e:
        logging.exception(e)
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch booking statuses.'})), 500


@api.route('/booking-statuses/<int:status_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def delete_booking_status(status_id):
    # 👉 Catch CORS preflight
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        status = BookingStatus.query.filter_by(id=status_id).first()
        if not status:
            return make_response(jsonify({'status': 'fail', 'message': 'Booking status not found.'})), 404

        db.session.delete(status)
        db.session.commit()

        return make_response(jsonify({'status': 'success', 'message': 'Booking status deleted successfully.'})), 200

    except Exception as e:
        logging.exception("An error occurred: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete booking status. It might be linked to existing bookings.'
        })), 500