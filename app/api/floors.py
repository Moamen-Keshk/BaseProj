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

@api.route('/all-floors/<int:property_id>')
def all_floors(property_id):
    resp = get_current_user()
    if isinstance(resp, str):
        floors_list = Floor.query.filter_by(property_id=property_id).order_by(Floor.floor_number).all()
        for x in floors_list:
            floors_list[floors_list.index(x)] = x.to_json()
        responseObject = {
            'status': 'success',
            'data': floors_list,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 201
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401