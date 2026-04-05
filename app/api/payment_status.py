import logging
from flask import request, make_response, jsonify
from . import api
from app.api.models import PaymentStatus
from .. import db
from app.api.decorators import require_active_staff


@api.route('/payment-statuses', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def new_payment_status():
    # 👉 Catch CORS preflight requests before they are processed
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = dict(request.json)

        # Validation
        if not data or 'name' not in data or not data['name'].strip():
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Payment status name is required.'
            })), 400

        if 'code' not in data or not data['code'].strip():
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Payment status code is required.'
            })), 400

        # Optional color field
        color_raw = data.get('color')
        color = color_raw.strip() if color_raw else ''

        status = PaymentStatus(
            name=data['name'].strip(),
            code=data['code'].strip(),
            color=color
        )

        db.session.add(status)
        db.session.flush()
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Payment status added successfully.'
        })), 201

    except Exception as e:
        logging.exception(e)
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Some error occurred. Please try again.'
        })), 500


@api.route('/payment-statuses/<int:status_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def edit_payment_status(status_id):
    # 👉 Catch CORS preflight
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = request.get_json()
        status = db.session.query(PaymentStatus).filter_by(id=status_id).first()

        if not status:
            return make_response(jsonify({'status': 'fail', 'message': 'Payment status not found.'})), 404

        if 'name' in data and data['name'] and data['name'].strip():
            status.name = data['name'].strip()

        if 'code' in data and data['code'] and data['code'].strip():
            status.code = data['code'].strip()

        if 'color' in data:
            color_raw = data['color']
            status.color = color_raw.strip() if color_raw else ''

        db.session.commit()
        return make_response(jsonify({'status': 'success', 'message': 'Payment status updated successfully.'})), 200

    except Exception as e:
        logging.exception("Error in edit_payment_status: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to update payment status.'})), 500


@api.route('/all-payment-statuses', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def all_payment_statuses():
    # 👉 Catch CORS preflight
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    """Allows any active staff member to view global payment statuses (Read-Only)"""
    try:
        statuses_list = PaymentStatus.query.order_by(PaymentStatus.id).all()

        # Using the model's built-in to_json() method
        serialized_statuses = [stat.to_json() for stat in statuses_list]

        return make_response(jsonify({
            'status': 'success',
            'data': serialized_statuses,
            'page': 0
        })), 200

    except Exception as e:
        logging.exception(e)
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch payment statuses.'})), 500


@api.route('/payment-statuses/<int:status_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def delete_payment_status(status_id):
    # 👉 Catch CORS preflight
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        status = PaymentStatus.query.filter_by(id=status_id).first()
        if not status:
            return make_response(jsonify({'status': 'fail', 'message': 'Payment status not found.'})), 404

        db.session.delete(status)
        db.session.commit()

        return make_response(jsonify({'status': 'success', 'message': 'Payment status deleted successfully.'})), 200

    except Exception as e:
        logging.exception("An error occurred: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete payment status. It might be linked to existing bookings or transactions.'
        })), 500