from flask import make_response, jsonify
from . import api
from .models import PaymentStatus
from app.auth.views import get_current_user

@api.route('/all-payment-status')
def all_payment_status():
    resp = get_current_user()
    if isinstance(resp, str):
        payment_status_list = PaymentStatus.query.order_by(PaymentStatus.id).all()
        for x in payment_status_list:
            payment_status_list[payment_status_list.index(x)] = x.to_json()
        responseObject = {
            'status': 'success',
            'data': payment_status_list,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 201
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401