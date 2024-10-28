from flask import request, make_response, jsonify
from . import api
import logging
from .models import Floor
from .. import db
from app.auth.views import get_current_user


@api.route('/new-floor', methods=['POST'])
def new_floor():
    resp = get_current_user()
    if isinstance(resp, str):
        try:
            floor = Floor.from_json(dict(request.json))
            db.session.add(floor)
            db.session.flush()
            db.session.commit()
            responseObject = {
                'status': 'success',
                'message': 'Floor added successfully.'
            }
            return make_response(jsonify(responseObject)), 201
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
