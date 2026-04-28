from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import and_, func

from app import db
from app.api.channel_manager.models import ChannelConnection, ChannelRatePlanMap, ChannelRoomMap
from app.api.models import (
    Block,
    Booking,
    DailyRatePlanState,
    MarketEvent,
    RatePlan,
    RevenueAuditLog,
    RevenuePolicy,
    RevenueRecommendation,
    Room,
)
from app.api.utils.housekeeping_logic import ACTIVE_BOOKING_STATUS_IDS
from app.api.utils.pricing_engine import (
    calculate_nightly_rate,
    get_effective_restrictions,
    get_rate_plan_room_type_id,
    get_room_sellable_type_id,
    get_seasons_for_property,
)


BASE_CHANNEL_CODE = 'base'
DIRECT_CHANNEL_CODE = 'direct'

SOURCE_RATE_PLAN = 'rate_plan'
SOURCE_MANUAL_OVERRIDE = 'manual_override'
SOURCE_RECOMMENDATION = 'recommendation'


def normalize_channel_code(channel_code: str | None, *, default: str = BASE_CHANNEL_CODE) -> str:
    normalized = (channel_code or '').strip().lower()
    return normalized or default


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def iterate_stay_dates(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def resolve_sellable_type_id(*, room: Room | None = None, rate_plan: RatePlan | None = None, sellable_type_id: int | None = None):
    if sellable_type_id:
        return int(sellable_type_id)
    if room is not None:
        resolved = get_room_sellable_type_id(room)
        if resolved:
            return int(resolved)
    if rate_plan is not None:
        resolved = get_rate_plan_room_type_id(rate_plan)
        if resolved:
            return int(resolved)
    return None


def get_rooms_for_sellable_type(property_id: int, sellable_type_id: int) -> list[Room]:
    return [
        room for room in Room.query.filter_by(property_id=property_id).all()
        if get_room_sellable_type_id(room) == sellable_type_id
    ]


def get_room_ids_for_sellable_type(property_id: int, sellable_type_id: int) -> list[int]:
    return [room.id for room in get_rooms_for_sellable_type(property_id, sellable_type_id)]


def get_available_channel_codes(property_id: int, rate_plan_id: int | None = None) -> list[str]:
    codes = {BASE_CHANNEL_CODE, DIRECT_CHANNEL_CODE}

    connection_codes = ChannelConnection.query.filter_by(
        property_id=property_id,
        status='active',
    ).with_entities(ChannelConnection.channel_code).all()
    codes.update(code for (code,) in connection_codes if code)

    rate_map_query = ChannelRatePlanMap.query.filter_by(property_id=property_id, is_active=True)
    if rate_plan_id is not None:
        rate_map_query = rate_map_query.filter_by(internal_rate_plan_id=rate_plan_id)
    mapped_codes = rate_map_query.with_entities(ChannelRatePlanMap.channel_code).all()
    codes.update(code for (code,) in mapped_codes if code)

    return sorted(codes)


def get_rate_plan_channels(rate_plan: RatePlan) -> list[str]:
    return get_available_channel_codes(rate_plan.property_id, rate_plan.id)


def get_or_create_policy(property_id: int, sellable_type_id: int, channel_code: str) -> RevenuePolicy:
    normalized_channel = normalize_channel_code(channel_code)
    policy = RevenuePolicy.query.filter_by(
        property_id=property_id,
        sellable_type_id=sellable_type_id,
        channel_code=normalized_channel,
    ).first()
    if policy is None:
        policy = RevenuePolicy(
            property_id=property_id,
            sellable_type_id=sellable_type_id,
            channel_code=normalized_channel,
        )
        db.session.add(policy)
        db.session.flush()
    return policy


def _build_transient_daily_state(rate_plan: RatePlan, stay_date: date, sellable_type_id: int):
    restrictions = get_effective_restrictions(rate_plan)
    base_amount = calculate_nightly_rate(
        rate_plan=rate_plan,
        target_date=stay_date,
        stay_length=1,
        adults=rate_plan.included_occupancy or 2,
        children=0,
        seasons=get_seasons_for_property(rate_plan.property_id),
    )
    return SimpleNamespace(
        id=None,
        property_id=rate_plan.property_id,
        sellable_type_id=sellable_type_id,
        rate_plan_id=rate_plan.id,
        stay_date=stay_date,
        channel_code=BASE_CHANNEL_CODE,
        base_amount=base_amount,
        amount=base_amount,
        min_los=restrictions.get('min_los'),
        max_los=restrictions.get('max_los'),
        closed=restrictions.get('closed'),
        closed_to_arrival=restrictions.get('closed_to_arrival'),
        closed_to_departure=restrictions.get('closed_to_departure'),
        source_type=SOURCE_RATE_PLAN,
        is_locked=False,
        explanation_json={},
    )


def materialize_daily_rates_for_rate_plan(rate_plan: RatePlan):
    sellable_type_id = resolve_sellable_type_id(rate_plan=rate_plan)
    if sellable_type_id is None:
        return

    seasons = get_seasons_for_property(rate_plan.property_id)
    restrictions = get_effective_restrictions(rate_plan)

    existing_rows = {
        row.stay_date: row
        for row in DailyRatePlanState.query.filter_by(
            property_id=rate_plan.property_id,
            sellable_type_id=sellable_type_id,
            rate_plan_id=rate_plan.id,
            channel_code=BASE_CHANNEL_CODE,
        ).filter(
            DailyRatePlanState.stay_date >= rate_plan.start_date,
            DailyRatePlanState.stay_date <= rate_plan.end_date,
        ).all()
    }

    for stay_date in iterate_stay_dates(rate_plan.start_date, rate_plan.end_date):
        base_amount = calculate_nightly_rate(
            rate_plan=rate_plan,
            target_date=stay_date,
            stay_length=1,
            adults=rate_plan.included_occupancy or 2,
            children=0,
            seasons=seasons,
        )
        row = existing_rows.get(stay_date)
        if row is None:
            row = DailyRatePlanState(
                property_id=rate_plan.property_id,
                sellable_type_id=sellable_type_id,
                rate_plan_id=rate_plan.id,
                stay_date=stay_date,
                channel_code=BASE_CHANNEL_CODE,
                base_amount=base_amount,
                amount=base_amount,
                source_type=SOURCE_RATE_PLAN,
            )
            db.session.add(row)
            existing_rows[stay_date] = row
        row.base_amount = base_amount
        if row.source_type == SOURCE_RATE_PLAN and not row.is_locked:
            row.amount = base_amount
        row.min_los = restrictions.get('min_los')
        row.max_los = restrictions.get('max_los')
        row.closed = bool(restrictions.get('closed'))
        row.closed_to_arrival = bool(restrictions.get('closed_to_arrival'))
        row.closed_to_departure = bool(restrictions.get('closed_to_departure'))

    channel_rows = DailyRatePlanState.query.filter(
        DailyRatePlanState.property_id == rate_plan.property_id,
        DailyRatePlanState.sellable_type_id == sellable_type_id,
        DailyRatePlanState.rate_plan_id == rate_plan.id,
        DailyRatePlanState.channel_code != BASE_CHANNEL_CODE,
        DailyRatePlanState.stay_date >= rate_plan.start_date,
        DailyRatePlanState.stay_date <= rate_plan.end_date,
    ).all()
    for row in channel_rows:
        base_row = existing_rows.get(row.stay_date) or DailyRatePlanState.query.filter_by(
            property_id=rate_plan.property_id,
            sellable_type_id=sellable_type_id,
            rate_plan_id=rate_plan.id,
            stay_date=row.stay_date,
            channel_code=BASE_CHANNEL_CODE,
        ).first()
        if base_row is not None:
            row.base_amount = float(base_row.amount or base_row.base_amount)
        row.min_los = restrictions.get('min_los')
        row.max_los = restrictions.get('max_los')
        row.closed = bool(restrictions.get('closed'))
        row.closed_to_arrival = bool(restrictions.get('closed_to_arrival'))
        row.closed_to_departure = bool(restrictions.get('closed_to_departure'))


def refresh_daily_rates_for_rate_plan(
    rate_plan: RatePlan,
    *,
    previous_sellable_type_id: int | None = None,
    previous_start_date: date | None = None,
    previous_end_date: date | None = None,
):
    current_sellable_type_id = resolve_sellable_type_id(rate_plan=rate_plan)

    stale_query = DailyRatePlanState.query.filter_by(
        property_id=rate_plan.property_id,
        rate_plan_id=rate_plan.id,
    )
    if previous_sellable_type_id is not None:
        stale_query = stale_query.filter(
            (DailyRatePlanState.sellable_type_id == previous_sellable_type_id)
            | (DailyRatePlanState.sellable_type_id == current_sellable_type_id)
        )

    stale_rows = stale_query.all()
    for row in stale_rows:
        if row.sellable_type_id != current_sellable_type_id:
            db.session.delete(row)
            continue
        if row.stay_date < rate_plan.start_date or row.stay_date > rate_plan.end_date:
            db.session.delete(row)

    stale_recommendations = RevenueRecommendation.query.filter_by(
        property_id=rate_plan.property_id,
        rate_plan_id=rate_plan.id,
    ).all()
    for recommendation in stale_recommendations:
        if recommendation.sellable_type_id != current_sellable_type_id:
            db.session.delete(recommendation)
            continue
        if recommendation.stay_date < rate_plan.start_date or recommendation.stay_date > rate_plan.end_date:
            db.session.delete(recommendation)

    materialize_daily_rates_for_rate_plan(rate_plan)


def rebuild_daily_rates_for_property_range(property_id: int, start_date: date, end_date: date):
    rate_plans = RatePlan.query.filter_by(property_id=property_id, is_active=True).filter(
        RatePlan.start_date <= end_date,
        RatePlan.end_date >= start_date,
    ).all()
    for rate_plan in rate_plans:
        materialize_daily_rates_for_rate_plan(rate_plan)


def delete_daily_revenue_for_rate_plan(property_id: int, rate_plan_id: int):
    DailyRatePlanState.query.filter_by(property_id=property_id, rate_plan_id=rate_plan_id).delete(
        synchronize_session=False
    )
    RevenueRecommendation.query.filter_by(property_id=property_id, rate_plan_id=rate_plan_id).delete(
        synchronize_session=False
    )
    RevenueAuditLog.query.filter_by(property_id=property_id, rate_plan_id=rate_plan_id).delete(
        synchronize_session=False
    )


def get_daily_rate_state(
    *,
    property_id: int,
    rate_plan_id: int,
    stay_date: date,
    channel_code: str | None = None,
    room_id: int | None = None,
    sellable_type_id: int | None = None,
):
    normalized_channel = normalize_channel_code(channel_code)
    rate_plan = RatePlan.query.filter_by(id=rate_plan_id, property_id=property_id).first()
    if rate_plan is None:
        return None

    room = None
    if room_id is not None:
        room = Room.query.filter_by(id=room_id, property_id=property_id).first()
    resolved_sellable_type_id = resolve_sellable_type_id(
        room=room,
        rate_plan=rate_plan,
        sellable_type_id=sellable_type_id,
    )
    if resolved_sellable_type_id is None:
        return None

    if normalized_channel != BASE_CHANNEL_CODE:
        exact_row = DailyRatePlanState.query.filter_by(
            property_id=property_id,
            sellable_type_id=resolved_sellable_type_id,
            rate_plan_id=rate_plan_id,
            stay_date=stay_date,
            channel_code=normalized_channel,
        ).first()
        if exact_row is not None:
            return exact_row

    base_row = DailyRatePlanState.query.filter_by(
        property_id=property_id,
        sellable_type_id=resolved_sellable_type_id,
        rate_plan_id=rate_plan_id,
        stay_date=stay_date,
        channel_code=BASE_CHANNEL_CODE,
    ).first()
    if base_row is not None:
        return base_row

    return _build_transient_daily_state(rate_plan, stay_date, resolved_sellable_type_id)


def get_daily_state_restrictions(state) -> dict:
    return {
        'rate_plan_id': getattr(state, 'rate_plan_id', None),
        'min_los': getattr(state, 'min_los', None),
        'max_los': getattr(state, 'max_los', None),
        'closed': bool(getattr(state, 'closed', False)),
        'closed_to_arrival': bool(getattr(state, 'closed_to_arrival', False)),
        'closed_to_departure': bool(getattr(state, 'closed_to_departure', False)),
    }


def resolve_dynamic_nightly_rate(
    *,
    rate_plan: RatePlan,
    stay_date: date,
    stay_length: int,
    adults: int,
    children: int,
    channel_code: str | None = None,
    room_id: int | None = None,
    sellable_type_id: int | None = None,
):
    state = get_daily_rate_state(
        property_id=rate_plan.property_id,
        rate_plan_id=rate_plan.id,
        stay_date=stay_date,
        channel_code=channel_code,
        room_id=room_id,
        sellable_type_id=sellable_type_id,
    )
    raw_rate = calculate_nightly_rate(
        rate_plan=rate_plan,
        target_date=stay_date,
        stay_length=stay_length,
        adults=adults,
        children=children,
    )
    if state is None:
        return round(float(raw_rate), 2)

    state_base_amount = float(getattr(state, 'base_amount', 0.0) or 0.0)
    state_amount = float(getattr(state, 'amount', raw_rate) or raw_rate)
    if state_base_amount <= 0:
        return round(state_amount, 2)

    factor = state_amount / state_base_amount
    return round(float(raw_rate) * factor, 2)


def build_dynamic_quote(
    *,
    rate_plan: RatePlan,
    check_in: date,
    check_out: date,
    adults: int = 2,
    children: int = 0,
    channel_code: str | None = None,
    sellable_type_id: int | None = None,
):
    stay_length = (check_out - check_in).days
    if stay_length < 1:
        raise ValueError('Stay must be at least one night.')

    arrival_state = get_daily_rate_state(
        property_id=rate_plan.property_id,
        rate_plan_id=rate_plan.id,
        stay_date=check_in,
        channel_code=channel_code,
        sellable_type_id=sellable_type_id,
    )
    restrictions = get_daily_state_restrictions(arrival_state)
    if restrictions['closed']:
        raise ValueError('Rate plan is closed.')
    if restrictions['closed_to_arrival']:
        raise ValueError('Rate plan is closed to arrival.')
    if restrictions['closed_to_departure']:
        raise ValueError('Rate plan is closed to departure.')
    if restrictions['min_los'] is not None and stay_length < int(restrictions['min_los']):
        raise ValueError(f"Minimum stay is {int(restrictions['min_los'])} night(s).")
    if restrictions['max_los'] is not None and stay_length > int(restrictions['max_los']):
        raise ValueError(f"Maximum stay is {int(restrictions['max_los'])} night(s).")

    total_amount = 0.0
    nightly_rates = []
    current_date = check_in
    while current_date < check_out:
        nightly_rate = resolve_dynamic_nightly_rate(
            rate_plan=rate_plan,
            stay_date=current_date,
            stay_length=stay_length,
            adults=adults,
            children=children,
            channel_code=channel_code,
            sellable_type_id=sellable_type_id,
        )
        nightly_rates.append({
            'date': current_date.isoformat(),
            'rate': nightly_rate,
        })
        total_amount += nightly_rate
        current_date += timedelta(days=1)

    return {
        'rate_plan_id': rate_plan.id,
        'pricing_type': rate_plan.pricing_type,
        'channel_code': normalize_channel_code(channel_code, default=DIRECT_CHANNEL_CODE),
        'check_in': check_in.isoformat(),
        'check_out': check_out.isoformat(),
        'adults': adults,
        'children': children,
        'nights': stay_length,
        'nightly_rates': nightly_rates,
        'total_amount': round(total_amount, 2),
        'restrictions': restrictions,
    }


def compute_sellable_inventory(property_id: int, sellable_type_id: int, stay_date: date) -> int:
    rooms = get_rooms_for_sellable_type(property_id, sellable_type_id)
    if not rooms:
        return 0

    room_ids = [room.id for room in rooms]
    booked_room_ids = {
        room_id
        for (room_id,) in db.session.query(Booking.room_id).filter(
            Booking.property_id == property_id,
            Booking.room_id.in_(room_ids),
            Booking.status_id.in_(list(ACTIVE_BOOKING_STATUS_IDS)),
            Booking.check_in <= stay_date,
            Booking.check_out > stay_date,
        ).distinct().all()
    }
    blocked_room_ids = {
        room_id
        for (room_id,) in db.session.query(Block.room_id).filter(
            Block.property_id == property_id,
            Block.room_id.in_(room_ids),
            Block.start_date <= stay_date,
            Block.end_date > stay_date,
        ).distinct().all()
    }
    unavailable_room_ids = booked_room_ids | blocked_room_ids
    return max(0, len(room_ids) - len(unavailable_room_ids))


def compute_demand_metrics(property_id: int, sellable_type_id: int, stay_date: date, pickup_window_days: int):
    room_ids = get_room_ids_for_sellable_type(property_id, sellable_type_id)
    total_rooms = len(room_ids)
    if total_rooms == 0:
        return {
            'total_rooms': 0,
            'occupied_rooms': 0,
            'remaining_inventory': 0,
            'occupancy_pct': 0.0,
            'pickup_count': 0,
            'days_out': (stay_date - utc_today()).days,
            'event_uplift_pct': 0.0,
            'event_flat_delta': 0.0,
            'event_names': [],
        }

    occupied_rooms = db.session.query(func.count(func.distinct(Booking.room_id))).filter(
        Booking.property_id == property_id,
        Booking.room_id.in_(room_ids),
        Booking.status_id.in_(list(ACTIVE_BOOKING_STATUS_IDS)),
        Booking.check_in <= stay_date,
        Booking.check_out > stay_date,
    ).scalar() or 0

    booking_window_start = utc_today() - timedelta(days=max(1, int(pickup_window_days or 1)))
    pickup_count = db.session.query(func.count(Booking.id)).filter(
        Booking.property_id == property_id,
        Booking.room_id.in_(room_ids),
        Booking.status_id.in_(list(ACTIVE_BOOKING_STATUS_IDS)),
        Booking.check_in <= stay_date,
        Booking.check_out > stay_date,
        Booking.booking_date >= booking_window_start,
    ).scalar() or 0

    event_rows = MarketEvent.query.filter(
        MarketEvent.property_id == property_id,
        MarketEvent.is_active.is_(True),
        MarketEvent.start_date <= stay_date,
        MarketEvent.end_date >= stay_date,
        db.or_(MarketEvent.sellable_type_id.is_(None), MarketEvent.sellable_type_id == sellable_type_id),
    ).all()

    event_uplift_pct = sum(float(event.uplift_pct or 0.0) for event in event_rows)
    event_flat_delta = sum(float(event.flat_delta or 0.0) for event in event_rows)

    return {
        'total_rooms': int(total_rooms),
        'occupied_rooms': int(occupied_rooms),
        'remaining_inventory': max(0, int(total_rooms) - int(occupied_rooms)),
        'occupancy_pct': round(float(occupied_rooms) / float(total_rooms), 4),
        'pickup_count': int(pickup_count),
        'days_out': (stay_date - utc_today()).days,
        'event_uplift_pct': round(event_uplift_pct, 2),
        'event_flat_delta': round(event_flat_delta, 2),
        'event_names': [event.name for event in event_rows],
    }


def _clamp_rate(value: float, policy: RevenuePolicy) -> float:
    if policy.min_rate is not None:
        value = max(float(policy.min_rate), value)
    if policy.max_rate is not None:
        value = min(float(policy.max_rate), value)
    return round(value, 2)


def generate_recommendation(
    *,
    rate_plan: RatePlan,
    stay_date: date,
    channel_code: str | None = None,
):
    sellable_type_id = resolve_sellable_type_id(rate_plan=rate_plan)
    if sellable_type_id is None:
        raise ValueError('Rate plan is not assigned to a sellable room type.')

    normalized_channel = normalize_channel_code(channel_code, default=DIRECT_CHANNEL_CODE)
    policy = get_or_create_policy(rate_plan.property_id, sellable_type_id, normalized_channel)
    baseline_amount = resolve_dynamic_nightly_rate(
        rate_plan=rate_plan,
        stay_date=stay_date,
        stay_length=1,
        adults=rate_plan.included_occupancy or 2,
        children=0,
        channel_code=normalized_channel,
        sellable_type_id=sellable_type_id,
    )
    demand = compute_demand_metrics(
        rate_plan.property_id,
        sellable_type_id,
        stay_date,
        pickup_window_days=policy.pickup_window_days,
    )

    adjustment_pct = float(policy.channel_adjustment_pct or 0.0)
    reasons = []

    occupancy_pct = float(demand['occupancy_pct'] or 0.0)
    days_out = int(demand['days_out'] or 0)
    pickup_count = int(demand['pickup_count'] or 0)
    event_uplift_pct = float(demand['event_uplift_pct'] or 0.0)
    event_flat_delta = float(demand['event_flat_delta'] or 0.0)

    if occupancy_pct >= float(policy.high_occupancy_threshold or 0.0):
        adjustment_pct += float(policy.high_occupancy_uplift_pct or 0.0)
        reasons.append('high_occupancy')
    elif occupancy_pct <= float(policy.low_occupancy_threshold or 0.0) and days_out >= int(policy.long_lead_time_days or 0):
        adjustment_pct -= float(policy.low_occupancy_discount_pct or 0.0)
        reasons.append('low_occupancy')

    if days_out <= int(policy.short_lead_time_days or 0) and occupancy_pct >= 0.5:
        adjustment_pct += float(policy.short_lead_uplift_pct or 0.0)
        reasons.append('short_lead_strength')
    elif days_out >= int(policy.long_lead_time_days or 0) and occupancy_pct <= 0.5:
        adjustment_pct -= float(policy.long_lead_discount_pct or 0.0)
        reasons.append('long_lead_softness')

    if pickup_count > 0:
        adjustment_pct += float(policy.pickup_uplift_pct or 0.0)
        reasons.append('pickup_acceleration')

    if event_uplift_pct:
        adjustment_pct += event_uplift_pct
        reasons.append('market_event')

    recommended_amount = baseline_amount * (1.0 + (adjustment_pct / 100.0)) + event_flat_delta
    recommended_amount = _clamp_rate(recommended_amount, policy)

    confidence_score = 0.55
    if demand['total_rooms']:
        confidence_score += 0.1
    if occupancy_pct > 0:
        confidence_score += 0.1
    if pickup_count > 0:
        confidence_score += 0.05
    if days_out <= 30:
        confidence_score += 0.05
    if event_uplift_pct or event_flat_delta:
        confidence_score += 0.1
    if len(reasons) >= 2:
        confidence_score += 0.05
    confidence_score = round(min(confidence_score, 0.95), 2)

    recommendation = RevenueRecommendation.query.filter_by(
        property_id=rate_plan.property_id,
        sellable_type_id=sellable_type_id,
        rate_plan_id=rate_plan.id,
        stay_date=stay_date,
        channel_code=normalized_channel,
    ).first()
    if recommendation is None:
        recommendation = RevenueRecommendation(
            property_id=rate_plan.property_id,
            sellable_type_id=sellable_type_id,
            rate_plan_id=rate_plan.id,
            stay_date=stay_date,
            channel_code=normalized_channel,
        )
        db.session.add(recommendation)

    recommendation.baseline_amount = baseline_amount
    recommendation.recommended_amount = recommended_amount
    recommendation.confidence_score = confidence_score
    recommendation.status = 'pending'
    recommendation.reason_codes_json = reasons
    recommendation.explanation_json = {
        'demand': demand,
        'adjustment_pct': round(adjustment_pct, 2),
        'policy_id': policy.id,
    }
    return recommendation


def recompute_recommendations(
    *,
    property_id: int,
    start_date: date,
    end_date: date,
    rate_plan_id: int | None = None,
    sellable_type_id: int | None = None,
    channel_code: str | None = None,
):
    query = RatePlan.query.filter_by(property_id=property_id, is_active=True).filter(
        RatePlan.start_date <= end_date,
        RatePlan.end_date >= start_date,
    )
    if rate_plan_id is not None:
        query = query.filter_by(id=rate_plan_id)

    recommendations = []
    for rate_plan in query.all():
        rate_plan_sellable_type_id = resolve_sellable_type_id(rate_plan=rate_plan)
        if sellable_type_id is not None and rate_plan_sellable_type_id != sellable_type_id:
            continue

        channels = [normalize_channel_code(channel_code, default=DIRECT_CHANNEL_CODE)] if channel_code else get_rate_plan_channels(rate_plan)
        effective_start = max(start_date, rate_plan.start_date)
        effective_end = min(end_date, rate_plan.end_date)
        for stay_date in iterate_stay_dates(effective_start, effective_end):
            for resolved_channel in channels:
                if resolved_channel == BASE_CHANNEL_CODE:
                    continue
                recommendations.append(
                    generate_recommendation(
                        rate_plan=rate_plan,
                        stay_date=stay_date,
                        channel_code=resolved_channel,
                    )
                )

    return recommendations


def apply_recommendation(
    recommendation: RevenueRecommendation,
    *,
    lock: bool = False,
    applied_by: str | None = None,
):
    current_state = get_daily_rate_state(
        property_id=recommendation.property_id,
        rate_plan_id=recommendation.rate_plan_id,
        stay_date=recommendation.stay_date,
        channel_code=recommendation.channel_code,
        sellable_type_id=recommendation.sellable_type_id,
    )
    previous_amount = float(getattr(current_state, 'amount', recommendation.baseline_amount) or recommendation.baseline_amount)

    if getattr(current_state, 'is_locked', False) and getattr(current_state, 'source_type', None) == SOURCE_MANUAL_OVERRIDE:
        raise ValueError('This daily rate is locked by a manual override.')

    target_channel = normalize_channel_code(recommendation.channel_code, default=DIRECT_CHANNEL_CODE)
    target_state = DailyRatePlanState.query.filter_by(
        property_id=recommendation.property_id,
        sellable_type_id=recommendation.sellable_type_id,
        rate_plan_id=recommendation.rate_plan_id,
        stay_date=recommendation.stay_date,
        channel_code=target_channel if target_channel != BASE_CHANNEL_CODE else BASE_CHANNEL_CODE,
    ).first()

    if target_state is None:
        target_state = DailyRatePlanState(
            property_id=recommendation.property_id,
            sellable_type_id=recommendation.sellable_type_id,
            rate_plan_id=recommendation.rate_plan_id,
            stay_date=recommendation.stay_date,
            channel_code=target_channel,
            base_amount=recommendation.baseline_amount,
            amount=recommendation.baseline_amount,
            min_los=getattr(current_state, 'min_los', None),
            max_los=getattr(current_state, 'max_los', None),
            closed=bool(getattr(current_state, 'closed', False)),
            closed_to_arrival=bool(getattr(current_state, 'closed_to_arrival', False)),
            closed_to_departure=bool(getattr(current_state, 'closed_to_departure', False)),
            source_type=SOURCE_RATE_PLAN,
        )
        db.session.add(target_state)

    target_state.base_amount = float(recommendation.baseline_amount or target_state.base_amount)
    target_state.amount = float(recommendation.recommended_amount or recommendation.baseline_amount)
    target_state.source_type = SOURCE_RECOMMENDATION
    target_state.is_locked = bool(lock)
    target_state.explanation_json = {
        'recommendation_id': recommendation.id,
        'applied_by': applied_by,
        'reason_codes': recommendation.reason_codes_json or [],
    }

    recommendation.status = 'applied'
    db.session.add(
        RevenueAuditLog(
            property_id=recommendation.property_id,
            sellable_type_id=recommendation.sellable_type_id,
            rate_plan_id=recommendation.rate_plan_id,
            stay_date=recommendation.stay_date,
            channel_code=target_state.channel_code,
            action='apply_recommendation',
            previous_amount=previous_amount,
            new_amount=target_state.amount,
            metadata_json={'recommendation_id': recommendation.id, 'applied_by': applied_by},
        )
    )
    return target_state


def set_manual_override(
    *,
    property_id: int,
    rate_plan_id: int,
    stay_date: date,
    amount: float,
    channel_code: str | None = None,
    sellable_type_id: int | None = None,
    lock: bool = True,
    note: str | None = None,
    updated_by: str | None = None,
):
    normalized_channel = normalize_channel_code(channel_code, default=DIRECT_CHANNEL_CODE)
    base_state = get_daily_rate_state(
        property_id=property_id,
        rate_plan_id=rate_plan_id,
        stay_date=stay_date,
        channel_code=BASE_CHANNEL_CODE,
        sellable_type_id=sellable_type_id,
    )
    if base_state is None:
        raise ValueError('Unable to resolve the baseline daily rate for this override.')

    target_state = DailyRatePlanState.query.filter_by(
        property_id=property_id,
        sellable_type_id=base_state.sellable_type_id,
        rate_plan_id=rate_plan_id,
        stay_date=stay_date,
        channel_code=normalized_channel,
    ).first()
    if target_state is None:
        target_state = DailyRatePlanState(
            property_id=property_id,
            sellable_type_id=base_state.sellable_type_id,
            rate_plan_id=rate_plan_id,
            stay_date=stay_date,
            channel_code=normalized_channel,
            base_amount=float(base_state.amount or base_state.base_amount),
            amount=float(base_state.amount or base_state.base_amount),
            min_los=base_state.min_los,
            max_los=base_state.max_los,
            closed=bool(base_state.closed),
            closed_to_arrival=bool(base_state.closed_to_arrival),
            closed_to_departure=bool(base_state.closed_to_departure),
        )
        db.session.add(target_state)

    previous_amount = float(target_state.amount or target_state.base_amount)
    target_state.base_amount = float(base_state.amount or base_state.base_amount)
    target_state.amount = round(float(amount), 2)
    target_state.source_type = SOURCE_MANUAL_OVERRIDE
    target_state.is_locked = bool(lock)
    target_state.explanation_json = {'note': note, 'updated_by': updated_by}

    db.session.add(
        RevenueAuditLog(
            property_id=property_id,
            sellable_type_id=base_state.sellable_type_id,
            rate_plan_id=rate_plan_id,
            stay_date=stay_date,
            channel_code=normalized_channel,
            action='manual_override',
            previous_amount=previous_amount,
            new_amount=target_state.amount,
            metadata_json={'note': note, 'updated_by': updated_by, 'locked': bool(lock)},
        )
    )
    return target_state


def reset_daily_rate(
    *,
    property_id: int,
    rate_plan_id: int,
    stay_date: date,
    channel_code: str | None = None,
    sellable_type_id: int | None = None,
    updated_by: str | None = None,
):
    normalized_channel = normalize_channel_code(channel_code, default=DIRECT_CHANNEL_CODE)
    current_state = DailyRatePlanState.query.filter_by(
        property_id=property_id,
        sellable_type_id=sellable_type_id,
        rate_plan_id=rate_plan_id,
        stay_date=stay_date,
        channel_code=normalized_channel,
    ).first()

    if current_state is None:
        base_state = get_daily_rate_state(
            property_id=property_id,
            rate_plan_id=rate_plan_id,
            stay_date=stay_date,
            channel_code=BASE_CHANNEL_CODE,
            sellable_type_id=sellable_type_id,
        )
        if base_state is None:
            raise ValueError('No daily rate state found to reset.')
        current_state = base_state

    previous_amount = float(getattr(current_state, 'amount', 0.0) or 0.0)

    if normalized_channel == BASE_CHANNEL_CODE:
        current_state.amount = float(current_state.base_amount or 0.0)
        current_state.source_type = SOURCE_RATE_PLAN
        current_state.is_locked = False
        current_state.explanation_json = {}
    else:
        db.session.delete(current_state)

    db.session.add(
        RevenueAuditLog(
            property_id=property_id,
            sellable_type_id=sellable_type_id or getattr(current_state, 'sellable_type_id', None),
            rate_plan_id=rate_plan_id,
            stay_date=stay_date,
            channel_code=normalized_channel,
            action='reset_override',
            previous_amount=previous_amount,
            new_amount=float(getattr(current_state, 'base_amount', 0.0) or 0.0),
            metadata_json={'updated_by': updated_by},
        )
    )


def resolve_external_room_id(property_id: int, channel_code: str, room: Room) -> str | None:
    mapping = ChannelRoomMap.query.filter_by(
        property_id=property_id,
        channel_code=channel_code,
        internal_room_id=room.id,
        is_active=True,
    ).first()
    if mapping is not None:
        return mapping.external_room_id

    sellable_type_id = get_room_sellable_type_id(room)
    if sellable_type_id is None:
        return None

    type_mapping = ChannelRoomMap.query.filter_by(
        property_id=property_id,
        channel_code=channel_code,
        internal_room_type_id=sellable_type_id,
        is_active=True,
    ).first()
    if type_mapping is not None:
        return type_mapping.external_room_id

    return None
