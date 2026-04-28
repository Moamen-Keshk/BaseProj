import logging
from datetime import datetime, timedelta

from flask import jsonify, make_response, request

from . import api
from .. import db
from app.api.channel_manager.services.sync_dispatcher import SyncDispatcher
from app.api.decorators import require_permission
from app.api.models import DailyRatePlanState, MarketEvent, RatePlan, RevenuePolicy, RevenueRecommendation
from app.api.utils.revenue_management import (
    BASE_CHANNEL_CODE,
    DIRECT_CHANNEL_CODE,
    apply_recommendation,
    get_available_channel_codes,
    get_or_create_policy,
    get_room_ids_for_sellable_type,
    normalize_channel_code,
    recompute_recommendations,
    reset_daily_rate,
    set_manual_override,
)
from app.auth.utils import get_current_user


def _parse_date(value, *, field_name):
    if not value:
        raise ValueError(f'{field_name} is required.')
    try:
        return datetime.fromisoformat(value).date()
    except ValueError as exc:
        raise ValueError(f'Invalid {field_name}. Expected YYYY-MM-DD.') from exc


def _coerce_sellable_type_id(payload):
    value = None
    if isinstance(payload, dict):
        value = payload.get('sellable_type_id') or payload.get('room_type_id') or payload.get('category_id')
    else:
        value = payload
    if value in (None, ''):
        return None
    return int(value)


def _queue_revenue_ari_sync(
    property_id: int,
    sellable_type_id: int,
    dates: list,
    reason: str,
    channel_code: str | None = None,
):
    room_ids = get_room_ids_for_sellable_type(property_id, sellable_type_id)
    if not room_ids or not dates:
        return
    normalized_channel = normalize_channel_code(channel_code, default=BASE_CHANNEL_CODE)
    if normalized_channel == DIRECT_CHANNEL_CODE:
        return
    SyncDispatcher.queue_ari_push(
        property_id=property_id,
        room_ids=room_ids,
        dates=dates,
        reason=reason,
        channel_code=None if normalized_channel == BASE_CHANNEL_CODE else normalized_channel,
    )


@api.route('/properties/<int:property_id>/revenue/metadata', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_rates')
def revenue_metadata(property_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({'status': 'ok'})), 200

    try:
        rate_plans = RatePlan.query.filter_by(property_id=property_id).order_by(RatePlan.name).all()
        sellable_types = sorted({
            _coerce_sellable_type_id({'sellable_type_id': plan.room_type_id or plan.category_id})
            for plan in rate_plans
            if (plan.room_type_id or plan.category_id) is not None
        })
        return make_response(jsonify({
            'status': 'success',
            'data': {
                'channel_codes': get_available_channel_codes(property_id),
                'default_channel_code': DIRECT_CHANNEL_CODE,
                'base_channel_code': BASE_CHANNEL_CODE,
                'sellable_type_ids': sellable_types,
                'rate_plans': [plan.to_json() for plan in rate_plans],
            },
        })), 200
    except Exception as exc:
        logging.exception('Failed to load revenue metadata: %s', str(exc))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to load revenue metadata.'})), 500


@api.route('/properties/<int:property_id>/revenue/policies', methods=['GET', 'PUT', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def revenue_policies(property_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({'status': 'ok'})), 200

    if request.method == 'GET':
        try:
            sellable_type_id = _coerce_sellable_type_id(request.args)
            channel_code = request.args.get('channel_code')
            query = RevenuePolicy.query.filter_by(property_id=property_id)
            if sellable_type_id is not None:
                query = query.filter_by(sellable_type_id=sellable_type_id)
            if channel_code:
                query = query.filter_by(channel_code=normalize_channel_code(channel_code, default=DIRECT_CHANNEL_CODE))
            return make_response(jsonify({
                'status': 'success',
                'data': [policy.to_json() for policy in query.order_by(RevenuePolicy.sellable_type_id).all()],
            })), 200
        except Exception as exc:
            logging.exception('Failed to load revenue policies: %s', str(exc))
            return make_response(jsonify({'status': 'error', 'message': 'Failed to load revenue policies.'})), 500

    try:
        if not request.json:
            return make_response(jsonify({'status': 'fail', 'message': 'Request body is required.'})), 400

        sellable_type_id = _coerce_sellable_type_id(request.json)
        if sellable_type_id is None:
            return make_response(jsonify({'status': 'fail', 'message': 'sellable_type_id is required.'})), 400

        channel_code = normalize_channel_code(request.json.get('channel_code'), default=DIRECT_CHANNEL_CODE)
        policy = get_or_create_policy(property_id, sellable_type_id, channel_code)

        for field in (
            'min_rate',
            'max_rate',
            'high_occupancy_threshold',
            'low_occupancy_threshold',
            'high_occupancy_uplift_pct',
            'low_occupancy_discount_pct',
            'short_lead_time_days',
            'short_lead_uplift_pct',
            'long_lead_time_days',
            'long_lead_discount_pct',
            'pickup_window_days',
            'pickup_uplift_pct',
            'channel_adjustment_pct',
            'auto_apply_min_confidence',
        ):
            if field in request.json:
                setattr(policy, field, request.json.get(field))

        db.session.commit()
        return make_response(jsonify({'status': 'success', 'data': policy.to_json()})), 200
    except Exception as exc:
        logging.exception('Failed to save revenue policy: %s', str(exc))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to save revenue policy.'})), 500


@api.route('/properties/<int:property_id>/revenue/events', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def revenue_events(property_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({'status': 'ok'})), 200

    if request.method == 'GET':
        try:
            sellable_type_id = _coerce_sellable_type_id(request.args)
            query = MarketEvent.query.filter_by(property_id=property_id)
            if sellable_type_id is not None:
                query = query.filter(
                    (MarketEvent.sellable_type_id == sellable_type_id) | (MarketEvent.sellable_type_id.is_(None))
                )
            return make_response(jsonify({
                'status': 'success',
                'data': [event.to_json() for event in query.order_by(MarketEvent.start_date, MarketEvent.id).all()],
            })), 200
        except Exception as exc:
            logging.exception('Failed to load market events: %s', str(exc))
            return make_response(jsonify({'status': 'error', 'message': 'Failed to load market events.'})), 500

    try:
        payload = request.get_json() or {}
        name = (payload.get('name') or '').strip()
        if not name:
            return make_response(jsonify({'status': 'fail', 'message': 'Event name is required.'})), 400
        start_date = _parse_date(payload.get('start_date'), field_name='start_date')
        end_date = _parse_date(payload.get('end_date'), field_name='end_date')
        if start_date > end_date:
            return make_response(jsonify({'status': 'fail', 'message': 'start_date cannot be after end_date.'})), 400

        event = MarketEvent(
            property_id=property_id,
            sellable_type_id=_coerce_sellable_type_id(payload),
            name=name,
            start_date=start_date,
            end_date=end_date,
            uplift_pct=float(payload.get('uplift_pct') or 0.0),
            flat_delta=float(payload.get('flat_delta') or 0.0),
            is_active=bool(payload.get('is_active', True)),
        )
        db.session.add(event)
        db.session.commit()
        return make_response(jsonify({'status': 'success', 'data': event.to_json()})), 201
    except ValueError as exc:
        db.session.rollback()
        return make_response(jsonify({'status': 'fail', 'message': str(exc)})), 400
    except Exception as exc:
        logging.exception('Failed to create market event: %s', str(exc))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to create market event.'})), 500


@api.route('/properties/<int:property_id>/revenue/events/<int:event_id>', methods=['PUT', 'DELETE', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def revenue_event_detail(property_id, event_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({'status': 'ok'})), 200

    event = MarketEvent.query.filter_by(id=event_id, property_id=property_id).first()
    if event is None:
        return make_response(jsonify({'status': 'fail', 'message': 'Event not found.'})), 404

    if request.method == 'DELETE':
        try:
            db.session.delete(event)
            db.session.commit()
            return make_response(jsonify({'status': 'success'})), 200
        except Exception as exc:
            logging.exception('Failed to delete market event: %s', str(exc))
            db.session.rollback()
            return make_response(jsonify({'status': 'error', 'message': 'Failed to delete market event.'})), 500

    try:
        payload = request.get_json() or {}
        if 'name' in payload:
            event.name = (payload.get('name') or '').strip()
        if 'start_date' in payload:
            event.start_date = _parse_date(payload.get('start_date'), field_name='start_date')
        if 'end_date' in payload:
            event.end_date = _parse_date(payload.get('end_date'), field_name='end_date')
        if event.start_date > event.end_date:
            return make_response(jsonify({'status': 'fail', 'message': 'start_date cannot be after end_date.'})), 400
        if 'uplift_pct' in payload:
            event.uplift_pct = float(payload.get('uplift_pct') or 0.0)
        if 'flat_delta' in payload:
            event.flat_delta = float(payload.get('flat_delta') or 0.0)
        if 'is_active' in payload:
            event.is_active = bool(payload.get('is_active'))
        if any(key in payload for key in ('sellable_type_id', 'room_type_id', 'category_id')):
            event.sellable_type_id = _coerce_sellable_type_id(payload)
        db.session.commit()
        return make_response(jsonify({'status': 'success', 'data': event.to_json()})), 200
    except ValueError as exc:
        db.session.rollback()
        return make_response(jsonify({'status': 'fail', 'message': str(exc)})), 400
    except Exception as exc:
        logging.exception('Failed to update market event: %s', str(exc))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to update market event.'})), 500


@api.route('/properties/<int:property_id>/revenue/recommendations', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
@require_permission('view_rates')
def revenue_recommendations(property_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({'status': 'ok'})), 200

    if request.method == 'GET':
        try:
            sellable_type_id = _coerce_sellable_type_id(request.args)
            rate_plan_id = request.args.get('rate_plan_id', type=int)
            channel_code = request.args.get('channel_code')
            status = request.args.get('status')
            start_date_raw = request.args.get('start_date')
            end_date_raw = request.args.get('end_date')

            query = RevenueRecommendation.query.filter_by(property_id=property_id)
            if sellable_type_id is not None:
                query = query.filter_by(sellable_type_id=sellable_type_id)
            if rate_plan_id is not None:
                query = query.filter_by(rate_plan_id=rate_plan_id)
            if channel_code:
                query = query.filter_by(channel_code=normalize_channel_code(channel_code, default=DIRECT_CHANNEL_CODE))
            if status:
                query = query.filter_by(status=status)
            if start_date_raw:
                query = query.filter(RevenueRecommendation.stay_date >= _parse_date(start_date_raw, field_name='start_date'))
            if end_date_raw:
                query = query.filter(RevenueRecommendation.stay_date <= _parse_date(end_date_raw, field_name='end_date'))

            data = [
                {
                    **recommendation.to_json(),
                    'applied_state': (
                        DailyRatePlanState.query.filter_by(
                            property_id=property_id,
                            sellable_type_id=recommendation.sellable_type_id,
                            rate_plan_id=recommendation.rate_plan_id,
                            stay_date=recommendation.stay_date,
                            channel_code=normalize_channel_code(
                                recommendation.channel_code,
                                default=DIRECT_CHANNEL_CODE,
                            ),
                        ).first().to_json()
                        if DailyRatePlanState.query.filter_by(
                            property_id=property_id,
                            sellable_type_id=recommendation.sellable_type_id,
                            rate_plan_id=recommendation.rate_plan_id,
                            stay_date=recommendation.stay_date,
                            channel_code=normalize_channel_code(
                                recommendation.channel_code,
                                default=DIRECT_CHANNEL_CODE,
                            ),
                        ).first() is not None else None
                    ),
                }
                for recommendation in query.order_by(
                    RevenueRecommendation.stay_date,
                    RevenueRecommendation.channel_code,
                ).all()
            ]
            return make_response(jsonify({'status': 'success', 'data': data})), 200
        except ValueError as exc:
            return make_response(jsonify({'status': 'fail', 'message': str(exc)})), 400
        except Exception as exc:
            logging.exception('Failed to load recommendations: %s', str(exc))
            return make_response(jsonify({'status': 'error', 'message': 'Failed to load recommendations.'})), 500

    try:
        payload = request.get_json() or {}
        start_date = _parse_date(payload.get('start_date'), field_name='start_date')
        end_date = _parse_date(payload.get('end_date'), field_name='end_date')
        if start_date > end_date:
            return make_response(jsonify({'status': 'fail', 'message': 'start_date cannot be after end_date.'})), 400

        recommendations = recompute_recommendations(
            property_id=property_id,
            start_date=start_date,
            end_date=end_date,
            rate_plan_id=payload.get('rate_plan_id'),
            sellable_type_id=_coerce_sellable_type_id(payload),
            channel_code=payload.get('channel_code'),
        )
        db.session.commit()
        return make_response(jsonify({
            'status': 'success',
            'data': [recommendation.to_json() for recommendation in recommendations],
        })), 200
    except ValueError as exc:
        db.session.rollback()
        return make_response(jsonify({'status': 'fail', 'message': str(exc)})), 400
    except Exception as exc:
        logging.exception('Failed to recompute recommendations: %s', str(exc))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to recompute recommendations.'})), 500


@api.route('/properties/<int:property_id>/revenue/recommendations/<int:recommendation_id>/apply', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def apply_revenue_recommendation(property_id, recommendation_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({'status': 'ok'})), 200

    try:
        recommendation = RevenueRecommendation.query.filter_by(
            id=recommendation_id,
            property_id=property_id,
        ).first()
        if recommendation is None:
            return make_response(jsonify({'status': 'fail', 'message': 'Recommendation not found.'})), 404

        payload = request.get_json() or {}
        updated_state = apply_recommendation(
            recommendation,
            lock=bool(payload.get('lock', False)),
            applied_by=get_current_user(),
        )
        db.session.commit()
        _queue_revenue_ari_sync(
            property_id,
            recommendation.sellable_type_id,
            [recommendation.stay_date],
            'revenue_recommendation_applied',
            recommendation.channel_code,
        )
        return make_response(jsonify({'status': 'success', 'data': updated_state.to_json()})), 200
    except ValueError as exc:
        db.session.rollback()
        return make_response(jsonify({'status': 'fail', 'message': str(exc)})), 400
    except Exception as exc:
        logging.exception('Failed to apply recommendation: %s', str(exc))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to apply recommendation.'})), 500


@api.route('/properties/<int:property_id>/revenue/daily_rates', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_rates')
def revenue_daily_rates(property_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({'status': 'ok'})), 200

    try:
        query = DailyRatePlanState.query.filter_by(property_id=property_id)
        sellable_type_id = _coerce_sellable_type_id(request.args)
        if sellable_type_id is not None:
            query = query.filter_by(sellable_type_id=sellable_type_id)
        rate_plan_id = request.args.get('rate_plan_id', type=int)
        if rate_plan_id is not None:
            query = query.filter_by(rate_plan_id=rate_plan_id)
        channel_code = request.args.get('channel_code')
        if channel_code:
            query = query.filter_by(channel_code=normalize_channel_code(channel_code, default=DIRECT_CHANNEL_CODE))
        start_date_raw = request.args.get('start_date')
        end_date_raw = request.args.get('end_date')
        if start_date_raw:
            query = query.filter(DailyRatePlanState.stay_date >= _parse_date(start_date_raw, field_name='start_date'))
        if end_date_raw:
            query = query.filter(DailyRatePlanState.stay_date <= _parse_date(end_date_raw, field_name='end_date'))
        data = [row.to_json() for row in query.order_by(DailyRatePlanState.stay_date, DailyRatePlanState.channel_code).all()]
        return make_response(jsonify({'status': 'success', 'data': data})), 200
    except ValueError as exc:
        return make_response(jsonify({'status': 'fail', 'message': str(exc)})), 400
    except Exception as exc:
        logging.exception('Failed to load daily rates: %s', str(exc))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to load daily rates.'})), 500


@api.route('/properties/<int:property_id>/revenue/daily_rates/override', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def revenue_daily_rate_override(property_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({'status': 'ok'})), 200

    try:
        payload = request.get_json() or {}
        sellable_type_id = _coerce_sellable_type_id(payload)
        if sellable_type_id is None:
            return make_response(jsonify({'status': 'fail', 'message': 'sellable_type_id is required.'})), 400
        rate_plan_id = payload.get('rate_plan_id')
        if rate_plan_id in (None, ''):
            return make_response(jsonify({'status': 'fail', 'message': 'rate_plan_id is required.'})), 400
        stay_date = _parse_date(payload.get('stay_date'), field_name='stay_date')
        amount = payload.get('amount')
        if amount in (None, ''):
            return make_response(jsonify({'status': 'fail', 'message': 'amount is required.'})), 400

        updated_state = set_manual_override(
            property_id=property_id,
            rate_plan_id=int(rate_plan_id),
            stay_date=stay_date,
            amount=float(amount),
            channel_code=payload.get('channel_code'),
            sellable_type_id=sellable_type_id,
            lock=bool(payload.get('lock', True)),
            note=payload.get('note'),
            updated_by=get_current_user(),
        )
        db.session.commit()
        _queue_revenue_ari_sync(
            property_id,
            sellable_type_id,
            [stay_date],
            'revenue_manual_override',
            payload.get('channel_code'),
        )
        return make_response(jsonify({'status': 'success', 'data': updated_state.to_json()})), 200
    except ValueError as exc:
        db.session.rollback()
        return make_response(jsonify({'status': 'fail', 'message': str(exc)})), 400
    except Exception as exc:
        logging.exception('Failed to save daily rate override: %s', str(exc))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to save daily rate override.'})), 500


@api.route('/properties/<int:property_id>/revenue/daily_rates/reset', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def revenue_daily_rate_reset(property_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({'status': 'ok'})), 200

    try:
        payload = request.get_json() or {}
        sellable_type_id = _coerce_sellable_type_id(payload)
        if sellable_type_id is None:
            return make_response(jsonify({'status': 'fail', 'message': 'sellable_type_id is required.'})), 400
        rate_plan_id = payload.get('rate_plan_id')
        if rate_plan_id in (None, ''):
            return make_response(jsonify({'status': 'fail', 'message': 'rate_plan_id is required.'})), 400
        stay_date = _parse_date(payload.get('stay_date'), field_name='stay_date')

        reset_daily_rate(
            property_id=property_id,
            rate_plan_id=int(rate_plan_id),
            stay_date=stay_date,
            channel_code=payload.get('channel_code'),
            sellable_type_id=sellable_type_id,
            updated_by=get_current_user(),
        )
        db.session.commit()
        _queue_revenue_ari_sync(
            property_id,
            sellable_type_id,
            [stay_date],
            'revenue_override_reset',
            payload.get('channel_code'),
        )
        return make_response(jsonify({'status': 'success'})), 200
    except ValueError as exc:
        db.session.rollback()
        return make_response(jsonify({'status': 'fail', 'message': str(exc)})), 400
    except Exception as exc:
        logging.exception('Failed to reset daily rate override: %s', str(exc))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to reset daily rate override.'})), 500
