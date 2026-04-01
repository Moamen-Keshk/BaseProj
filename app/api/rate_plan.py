import logging
from datetime import datetime
from types import SimpleNamespace
from flask import request, make_response, jsonify
from . import api
from app.api.models import RatePlan, RoomOnline
from .. import db
from app.api.decorators import require_permission
from app.api.utils.room_online_generator import generate_or_update_room_online_for_rate_plan
from app.api.channel_manager.services.pms_sync import (
    queue_rate_plan_ari_sync,
    queue_rate_plan_transition_ari_sync,
)


@api.route('/properties/<int:property_id>/rate_plans', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def new_rate_plan(property_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        rate_data = dict(request.json)
        # Enforce property_id from the secured URL
        rate_data['property_id'] = property_id

        rate_plan = RatePlan.from_json(rate_data)
        db.session.add(rate_plan)
        db.session.flush()
        db.session.commit()

        generate_or_update_room_online_for_rate_plan(rate_plan)
        queue_rate_plan_ari_sync(rate_plan, 'rate_plan_created')

        responseObject = {
            'status': 'success',
            'message': 'Rate Plan added successfully.'
        }
        return make_response(jsonify(responseObject)), 201

    except Exception as e:
        logging.exception(e)
        db.session.rollback()
        responseObject = {
            'status': 'error',
            'message': 'Some error occurred. Please try again.'
        }
        return make_response(jsonify(responseObject)), 500


@api.route('/properties/<int:property_id>/rate_plans/<int:rate_plan_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def edit_rate_plan(property_id, rate_plan_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        rate_data = request.get_json()

        # Ensure the rate plan exists and belongs to this property
        rate_plan = db.session.query(RatePlan).filter_by(id=rate_plan_id, property_id=property_id).first()

        if not rate_plan:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Rate Plan not found in this property.'
            })), 404

        old_property_id = rate_plan.property_id
        old_category_id = rate_plan.category_id
        old_start_date = rate_plan.start_date
        old_end_date = rate_plan.end_date

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
        generate_or_update_room_online_for_rate_plan(rate_plan)

        queue_rate_plan_transition_ari_sync(
            old_property_id=old_property_id,
            old_category_id=old_category_id,
            old_start_date=old_start_date,
            old_end_date=old_end_date,
            rate_plan=rate_plan,
            reason='rate_plan_updated',
        )

        return make_response(jsonify({
            'status': 'success',
            'message': 'Rate Plan updated successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error in edit_rate_plan: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update rate plan. Please try again.'
        })), 500


@api.route('/properties/<int:property_id>/categories/<int:category_id>/rate_plans', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_rates')
def get_rate_plans(property_id, category_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        rate_plans = RatePlan.query.filter_by(
            property_id=property_id,
            category_id=category_id
        ).order_by(RatePlan.start_date).all()

        data = [plan.to_json() for plan in rate_plans]

        responseObject = {
            'status': 'success',
            'data': data,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 200

    except Exception as e:
        logging.exception("Error in get_rate_plans: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch rate plans.'
        })), 500


@api.route('/properties/<int:property_id>/rate_plans', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_rates')
def all_rate_plans(property_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        rate_plans = RatePlan.query.filter_by(
            property_id=property_id
        ).order_by(RatePlan.start_date).all()

        data = [plan.to_json() for plan in rate_plans]

        responseObject = {
            'status': 'success',
            'data': data,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 200

    except Exception as e:
        logging.exception("Error in all_rate_plans: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch rate plans.'
        })), 500


@api.route('/properties/<int:property_id>/rate_plans/<int:rate_plan_id>', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_rates')
def get_rate_plan_by_id(property_id, rate_plan_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        rate_plan = db.session.query(RatePlan).filter_by(id=rate_plan_id, property_id=property_id).first()

        if not rate_plan:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Rate Plan not found.'
            })), 404

        return make_response(jsonify({
            'status': 'success',
            'data': rate_plan.to_json()
        })), 200

    except Exception as e:
        logging.exception("Error in get_rate_plan_by_id: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch rate plan.'
        })), 500


@api.route('/properties/<int:property_id>/rate_plans/<int:rate_plan_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def delete_rate_plan(property_id, rate_plan_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        rate_plan = db.session.query(RatePlan).filter_by(id=rate_plan_id, property_id=property_id).first()
        if not rate_plan:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Rate Plan not found in this property.'
            })), 404

        old_property_id = rate_plan.property_id
        old_category_id = rate_plan.category_id
        old_start_date = rate_plan.start_date
        old_end_date = rate_plan.end_date

        RoomOnline.query.filter(
            RoomOnline.property_id == rate_plan.property_id,
            RoomOnline.category_id == rate_plan.category_id,
            RoomOnline.date >= rate_plan.start_date,
            RoomOnline.date <= rate_plan.end_date
        ).delete(synchronize_session=False)

        db.session.delete(rate_plan)
        db.session.commit()

        deleted_snapshot = SimpleNamespace(
            property_id=old_property_id,
            category_id=old_category_id,
            start_date=old_start_date,
            end_date=old_end_date,
        )

        queue_rate_plan_ari_sync(deleted_snapshot, 'rate_plan_deleted')

        return make_response(jsonify({
            'status': 'success',
            'message': 'Rate Plan and linked RoomOnline entries deleted successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error in delete_rate_plan: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete rate plan. Please try again.'
        })), 500