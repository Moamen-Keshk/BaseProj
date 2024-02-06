from flask import request, make_response, jsonify, current_app
from . import api
import logging
from .models import Order
from .. import db
from app.auth.views import get_current_user
from werkzeug.utils import secure_filename
import os
from flask import send_from_directory


@api.route('/orders', methods=['POST'])
def new_order():
    resp = get_current_user()
    if not isinstance(resp, str):
        try:
            order = Order.from_json(dict(request.form))
            order.creator_id = resp
            db.session.add(order)
            db.session.flush()
            files = request.files
            order_id = order.id
            for i in range(len(request.files)):
                filename = str(order_id) + ': ' + secure_filename(files[str(i)].filename)
                files[str(i)].save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            db.session.commit()
            responseObject = {
                'status': 'success',
                'message': 'Order submitted.'
            }
            return make_response(jsonify(responseObject)), 200
        except Exception as e:
            logging.exception(e)
            responseObject = {
                'status': 'error',
                'message': 'Some error occurred. Please try again.'
            }
            return make_response(jsonify(responseObject)), 401
    responseObject = {
        'status': 'expired',
        'message': 'Session expired, log in required!'
    }
    return make_response(jsonify(responseObject)), 202


@api.route('/uploads/<name>')
def download_file(name):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], name)
