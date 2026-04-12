from datetime import timedelta

from app.api.models import RatePlan, Room, RoomOnline, Season


VALID_PRICING_TYPES = {'standard', 'derived', 'occupancy', 'los'}
VALID_DERIVED_ADJUSTMENT_TYPES = {'percent', 'amount'}


def normalize_los_pricing(los_pricing):
    normalized = {}
    if not los_pricing:
        return normalized

    for item in los_pricing:
        if not isinstance(item, dict):
            continue

        stay_length = item.get('stay_length')
        nightly_rate = item.get('nightly_rate')
        if stay_length in (None, '') or nightly_rate in (None, ''):
            continue

        normalized[int(stay_length)] = float(nightly_rate)

    return normalized


def build_rate_plan_validation_errors(rate_plan):
    errors = []

    if rate_plan.pricing_type not in VALID_PRICING_TYPES:
        errors.append('Invalid pricing_type.')

    if rate_plan.pricing_type == 'derived':
        if not rate_plan.parent_rate_plan_id:
            errors.append('Derived pricing requires a parent_rate_plan_id.')
        if rate_plan.derived_adjustment_type not in VALID_DERIVED_ADJUSTMENT_TYPES:
            errors.append('Derived pricing requires derived_adjustment_type of percent or amount.')
        if rate_plan.derived_adjustment_value is None:
            errors.append('Derived pricing requires derived_adjustment_value.')

    if rate_plan.parent_rate_plan_id == rate_plan.id and rate_plan.id is not None:
        errors.append('A rate plan cannot derive from itself.')

    if rate_plan.min_los is not None and int(rate_plan.min_los) < 1:
        errors.append('min_los must be at least 1.')
    if rate_plan.max_los is not None and int(rate_plan.max_los) < 1:
        errors.append('max_los must be at least 1.')
    if rate_plan.min_los is not None and rate_plan.max_los is not None and int(rate_plan.min_los) > int(rate_plan.max_los):
        errors.append('min_los cannot be greater than max_los.')

    if rate_plan.included_occupancy is not None and int(rate_plan.included_occupancy) < 1:
        errors.append('included_occupancy must be at least 1.')

    normalize_los_pricing(rate_plan.los_pricing)

    return errors


def get_seasons_for_property(property_id):
    return Season.query.filter_by(property_id=property_id).all()


def get_base_rate_for_date(rate_plan, target_date, seasons=None):
    seasons = seasons if seasons is not None else get_seasons_for_property(rate_plan.property_id)
    is_weekend = target_date.weekday() in [5, 6]
    base_rate = rate_plan.weekend_rate if is_weekend and rate_plan.weekend_rate is not None else rate_plan.base_rate

    in_season = any(season.start_date <= target_date <= season.end_date for season in seasons)
    if in_season and rate_plan.seasonal_multiplier:
        base_rate *= rate_plan.seasonal_multiplier

    return float(base_rate)


def _resolve_parent_rate_plan(rate_plan):
    if not rate_plan.parent_rate_plan_id:
        return None

    return RatePlan.query.filter_by(
        id=rate_plan.parent_rate_plan_id,
        property_id=rate_plan.property_id,
        is_active=True,
    ).first()


def get_effective_restrictions(rate_plan):
    return {
        'rate_plan_id': rate_plan.id,
        'min_los': rate_plan.min_los,
        'max_los': rate_plan.max_los,
        'closed': bool(rate_plan.closed),
        'closed_to_arrival': bool(rate_plan.closed_to_arrival),
        'closed_to_departure': bool(rate_plan.closed_to_departure),
    }


def validate_quote_request(rate_plan, check_in, check_out):
    stay_length = (check_out - check_in).days
    if stay_length < 1:
        return False, 'Stay must be at least one night.'
    if rate_plan.closed:
        return False, 'Rate plan is closed.'
    if rate_plan.closed_to_arrival:
        return False, 'Rate plan is closed to arrival.'
    if rate_plan.closed_to_departure:
        return False, 'Rate plan is closed to departure.'
    if rate_plan.min_los is not None and stay_length < int(rate_plan.min_los):
        return False, f'Minimum stay is {int(rate_plan.min_los)} night(s).'
    if rate_plan.max_los is not None and stay_length > int(rate_plan.max_los):
        return False, f'Maximum stay is {int(rate_plan.max_los)} night(s).'
    return True, None


def calculate_nightly_rate(rate_plan, target_date, stay_length=1, adults=2, children=0, seasons=None, _visited=None):
    _visited = _visited or set()
    if rate_plan.id in _visited:
        raise ValueError('Circular derived rate plan configuration detected.')
    _visited.add(rate_plan.id)

    if rate_plan.pricing_type == 'derived':
        parent_rate_plan = _resolve_parent_rate_plan(rate_plan)
        if parent_rate_plan is None:
            raise ValueError('Derived rate plan parent not found.')
        base_rate = calculate_nightly_rate(
            parent_rate_plan,
            target_date,
            stay_length=stay_length,
            adults=adults,
            children=children,
            seasons=seasons,
            _visited=_visited,
        )
        if rate_plan.derived_adjustment_type == 'percent':
            base_rate *= float(rate_plan.derived_adjustment_value) / 100.0
        else:
            base_rate += float(rate_plan.derived_adjustment_value)
        return round(base_rate, 2)

    base_rate = get_base_rate_for_date(rate_plan, target_date, seasons=seasons)

    if rate_plan.pricing_type == 'los':
        los_pricing = normalize_los_pricing(rate_plan.los_pricing)
        if stay_length in los_pricing:
            base_rate = los_pricing[stay_length]

    if rate_plan.pricing_type == 'occupancy':
        total_guests = max(0, adults) + max(0, children)
        included_occupancy = int(rate_plan.included_occupancy or max(1, adults or 1))

        if adults == 1 and rate_plan.single_occupancy_rate is not None:
            base_rate = float(rate_plan.single_occupancy_rate)

        additional_guests = max(0, total_guests - included_occupancy)
        extra_adults = max(0, adults - included_occupancy)
        extra_children = min(additional_guests, max(0, children))

        if extra_adults and rate_plan.extra_adult_rate:
            base_rate += extra_adults * float(rate_plan.extra_adult_rate)
        if extra_children and rate_plan.extra_child_rate:
            base_rate += extra_children * float(rate_plan.extra_child_rate)

    return round(float(base_rate), 2)


def calculate_quote(rate_plan, check_in, check_out, adults=2, children=0, seasons=None):
    is_valid, message = validate_quote_request(rate_plan, check_in, check_out)
    if not is_valid:
        raise ValueError(message)

    stay_length = (check_out - check_in).days
    seasons = seasons if seasons is not None else get_seasons_for_property(rate_plan.property_id)

    nightly_rates = []
    total_amount = 0.0
    current_date = check_in
    while current_date < check_out:
        nightly_rate = calculate_nightly_rate(
            rate_plan=rate_plan,
            target_date=current_date,
            stay_length=stay_length,
            adults=adults,
            children=children,
            seasons=seasons,
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
        'check_in': check_in.isoformat(),
        'check_out': check_out.isoformat(),
        'adults': adults,
        'children': children,
        'nights': stay_length,
        'nightly_rates': nightly_rates,
        'total_amount': round(total_amount, 2),
        'restrictions': get_effective_restrictions(rate_plan),
    }


def get_applicable_rate_plan_for_room(property_id, room_id, stay_date):
    room_online = RoomOnline.query.filter_by(
        property_id=property_id,
        room_id=room_id,
        date=stay_date,
    ).first()
    if room_online and room_online.rate_plan_id:
        return RatePlan.query.filter_by(
            id=room_online.rate_plan_id,
            property_id=property_id,
            is_active=True,
        ).first()

    room = Room.query.filter_by(id=room_id, property_id=property_id).first()
    if room is None:
        return None

    return RatePlan.query.filter_by(
        property_id=property_id,
        category_id=room.category_id,
        is_active=True,
    ).filter(
        RatePlan.start_date <= stay_date,
        RatePlan.end_date >= stay_date,
    ).order_by(RatePlan.start_date, RatePlan.id).first()
