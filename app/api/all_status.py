import logging
from flask import request, make_response, jsonify
from . import api
from app.api.models import PaymentStatus
from app.auth.utils import get_current_user


@api.route('/all-payment-status', methods=['GET', 'OPTIONS'], strict_slashes=False)
def all_payment_status():
    """Returns a list of all global payment statuses available in the PMS."""

    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        # 2. Standard authentication check
        user_id = get_current_user()
        if not user_id:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access. Session expired or login required.'
            })), 401

        # Fetch and serialize
        payment_statuses = PaymentStatus.query.order_by(PaymentStatus.id).all()

        responseObject = {
            'status': 'success',
            'data': [status.to_json() for status in payment_statuses],
            'page': 0
        }
        return make_response(jsonify(responseObject)), 200

    except Exception as e:
        logging.exception("Error in all_payment_status: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch payment statuses. Please try again.'
        })), 500