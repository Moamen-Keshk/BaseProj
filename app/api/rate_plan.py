import logging
from datetime import datetime
from types import SimpleNamespace
from flask import request, make_response, jsonify
from . import api
from app.api.models import RatePlan
from .. import db
from app.api.decorators import require_permission
from app.api.utils.room_online_generator import (
    generate_or_update_room_online_for_rate_plan,
    rebuild_room_online_for_category_range,
)
from app.api.utils.pricing_engine import build_rate_plan_validation_errors, calculate_quote
from app.api.channel_manager.services.pms_sync import (
    queue_rate_plan_ari_sync,
    queue_rate_plan_transition_ari_sync,
)


def _rate_plan_conflict_payload(rate_plans):
    return [
        {
            'id': plan.id,
            'name': plan.name,
            'start_date': plan.start_date.isoformat() if plan.start_date else None,
            'end_date': plan.end_date.isoformat() if plan.end_date else None,
        }
        for plan in rate_plans
    ]


def _ensure_parent_rate_plan_is_valid(rate_plan):
    if not rate_plan.parent_rate_plan_id:
        return None

    parent_rate_plan = RatePlan.query.filter_by(
        id=rate_plan.parent_rate_plan_id,
        property_id=rate_plan.property_id,
        is_active=True,
    ).first()
    if parent_rate_plan is None:
        return 'Parent rate plan not found.'
    if parent_rate_plan.category_id != rate_plan.category_id:
        return 'Parent rate plan must belong to the same category.'
    return None


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

        start_date = datetime.fromisoformat(rate_data['start_date']).date()
        end_date = datetime.fromisoformat(rate_data['end_date']).date()
        category_id = rate_data.get('category_id')

        if start_date > end_date:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Start date cannot be after end date.'
            })), 400

        rate_plan = RatePlan.from_json(rate_data)
        validation_errors = build_rate_plan_validation_errors(rate_plan)
        parent_validation_error = _ensure_parent_rate_plan_is_valid(rate_plan)
        if parent_validation_error:
            validation_errors.append(parent_validation_error)
        if validation_errors:
            return make_response(jsonify({
                'status': 'fail',
                'message': validation_errors[0],
                'errors': validation_errors,
            })), 400

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

        merged_data = rate_plan.to_json()
        merged_data.update(rate_data)
        merged_data['property_id'] = property_id
        draft_rate_plan = RatePlan.from_json(merged_data)
        draft_rate_plan.id = rate_plan.id

        new_name = draft_rate_plan.name
        new_base_rate = draft_rate_plan.base_rate
        new_category_id = draft_rate_plan.category_id
        new_start_date = draft_rate_plan.start_date
        new_end_date = draft_rate_plan.end_date
        new_weekend_rate = draft_rate_plan.weekend_rate
        new_seasonal_multiplier = draft_rate_plan.seasonal_multiplier
        new_is_active = draft_rate_plan.is_active

        if new_start_date > new_end_date:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Start date cannot be after end date.'
            })), 400

        validation_errors = build_rate_plan_validation_errors(draft_rate_plan)
        parent_validation_error = _ensure_parent_rate_plan_is_valid(draft_rate_plan)
        if parent_validation_error:
            validation_errors.append(parent_validation_error)
        if validation_errors:
            return make_response(jsonify({
                'status': 'fail',
                'message': validation_errors[0],
                'errors': validation_errors,
            })), 400

        rate_plan.name = new_name
        rate_plan.base_rate = new_base_rate
        rate_plan.category_id = new_category_id
        rate_plan.start_date = new_start_date
        rate_plan.end_date = new_end_date
        rate_plan.weekend_rate = new_weekend_rate
        rate_plan.seasonal_multiplier = new_seasonal_multiplier
        rate_plan.pricing_type = draft_rate_plan.pricing_type
        rate_plan.parent_rate_plan_id = draft_rate_plan.parent_rate_plan_id
        rate_plan.derived_adjustment_type = draft_rate_plan.derived_adjustment_type
        rate_plan.derived_adjustment_value = draft_rate_plan.derived_adjustment_value
        rate_plan.included_occupancy = draft_rate_plan.included_occupancy
        rate_plan.single_occupancy_rate = draft_rate_plan.single_occupancy_rate
        rate_plan.extra_adult_rate = draft_rate_plan.extra_adult_rate
        rate_plan.extra_child_rate = draft_rate_plan.extra_child_rate
        rate_plan.min_los = draft_rate_plan.min_los
        rate_plan.max_los = draft_rate_plan.max_los
        rate_plan.closed = draft_rate_plan.closed
        rate_plan.closed_to_arrival = draft_rate_plan.closed_to_arrival
        rate_plan.closed_to_departure = draft_rate_plan.closed_to_departure
        rate_plan.meal_plan_code = draft_rate_plan.meal_plan_code
        rate_plan.cancellation_policy = draft_rate_plan.cancellation_policy
        rate_plan.los_pricing = draft_rate_plan.los_pricing
        rate_plan.is_active = new_is_active

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


@api.route('/properties/<int:property_id>/rate_plans/<int:rate_plan_id>/quote', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_rates')
def quote_rate_plan(property_id, rate_plan_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        rate_plan = db.session.query(RatePlan).filter_by(id=rate_plan_id, property_id=property_id).first()
        if not rate_plan:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Rate Plan not found.'
            })), 404

        check_in_raw = request.args.get('check_in')
        check_out_raw = request.args.get('check_out')
        if not check_in_raw or not check_out_raw:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'check_in and check_out are required.'
            })), 400

        check_in = datetime.fromisoformat(check_in_raw).date()
        check_out = datetime.fromisoformat(check_out_raw).date()
        adults = int(request.args.get('adults', 2))
        children = int(request.args.get('children', 0))

        quote = calculate_quote(
            rate_plan=rate_plan,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            children=children,
        )

        return make_response(jsonify({
            'status': 'success',
            'data': quote,
        })), 200

    except ValueError as exc:
        return make_response(jsonify({
            'status': 'fail',
            'message': str(exc),
        })), 400
    except Exception as e:
        logging.exception("Error in quote_rate_plan: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to quote rate plan.'
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

        db.session.delete(rate_plan)
        db.session.flush()

        rebuild_room_online_for_category_range(
            property_id=old_property_id,
            category_id=old_category_id,
            start_date=old_start_date,
            end_date=old_end_date,
        )

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
