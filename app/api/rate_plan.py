from flask import request, make_response, jsonify
from . import api
import logging
from .models import RatePlan
from .. import db
from app.auth.views import get_current_user
from datetime import datetime

@api.route('/new_rate_plan', methods=['POST'])
def new_rate_plan():
    resp = get_current_user()
    if isinstance(resp, str):
        try:
            rate_plan = RatePlan.from_json(dict(request.json))
            db.session.add(rate_plan)
            db.session.flush()
            db.session.commit()
            responseObject = {
                'status': 'success',
                'message': 'Rate Plan added successfully.'
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


@api.route('/edit_rate_plan/<int:rate_plan_id>', methods=['PUT'])
def edit_rate_plan(rate_plan_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        rate_data = request.get_json()
        rate_plan = db.session.query(RatePlan).filter_by(id=rate_plan_id).first()

        if not rate_plan:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Rate Plan not found.'
            })), 404

        if 'name' in rate_data:
            rate_plan.name = rate_data['name']
        if 'base_rate' in rate_data:
            rate_plan.base_rate = rate_data['base_rate']
        if 'category_id' in rate_data:
            rate_plan.category_id = rate_data['category_id']
        if 'start_date' in rate_data:
            rate_plan.start_date = datetime.fromisoformat(rate_data['start_date']).date()
        if 'end_date' in rate_data:
            rate_plan.end_date = datetime.fromisoformat(rate_data['end_date']).date()
        if 'weekend_rate' in rate_data:
            rate_plan.weekend_rate = rate_data['weekend_rate']
        if 'seasonal_multiplier' in rate_data:
            rate_plan.seasonal_multiplier = rate_data['seasonal_multiplier']
        if 'is_active' in rate_data:
            rate_plan.is_active = rate_data['is_active']

        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Rate Plan updated successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in edit_rate_plan: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update rate plan. Please try again.'
        })), 500


@api.route('/get_rate_plans/<int:property_id>/<int:category_id>')
def get_rate_plans(property_id, category_id):
    resp = get_current_user()
    if isinstance(resp, str):
        rate_plans = RatePlan.query.filter(
            RatePlan.property_id == property_id & RatePlan.category_id == category_id
        ).order_by(RatePlan.start_date).all()

        data = [plan.to_json() for plan in rate_plans]

        responseObject = {
            'status': 'success',
            'data': data,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 201

    return make_response(jsonify({
        'status': 'fail',
        'message': resp
    })), 401


@api.route('/all_rate_plans/<int:property_id>')
def all_rate_plans(property_id):
    resp = get_current_user()
    if isinstance(resp, str):
        rate_plans = RatePlan.query.filter(
            RatePlan.property_id == property_id
        ).order_by(RatePlan.start_date).all()

        data = [plan.to_json() for plan in rate_plans]

        responseObject = {
            'status': 'success',
            'data': data,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 201

    return make_response(jsonify({
        'status': 'fail',
        'message': resp
    })), 401

@api.route('/rate_plan/<int:rate_plan_id>', methods=['GET'])
def get_rate_plan_by_id(rate_plan_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        rate_plan = db.session.query(RatePlan).filter_by(id=rate_plan_id).first()

        if not rate_plan:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Rate Plan not found.'
            })), 404

        return make_response(jsonify({
            'status': 'success',
            'data': rate_plan.to_json()
        })), 201

    except Exception as e:
        logging.exception("Error in get_rate_plan_by_id: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch rate plan.'
        })), 500



@api.route('/delete_rate_plan/<int:rate_plan_id>', methods=['DELETE'])
def delete_rate_plan(rate_plan_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        rate_plan = db.session.query(RatePlan).filter_by(id=rate_plan_id).first()
        if not rate_plan:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Rate Plan not found.'
            })), 404

        db.session.delete(rate_plan)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Rate Plan deleted successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in delete_rate_plan: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete rate plan. Please try again.'
        })), 500
