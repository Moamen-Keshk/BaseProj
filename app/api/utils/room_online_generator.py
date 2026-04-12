from datetime import timedelta

from app import db
from app.api.models import Room, RoomOnline, RatePlan
from app.api.utils.pricing_engine import (
    calculate_nightly_rate,
    get_rate_plan_room_type_id,
    get_room_sellable_type_id,
    get_seasons_for_property,
)


def _date_range(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _candidate_rate_plans(property_id, sellable_type_id, target_date):
    return RatePlan.query.filter_by(property_id=property_id, is_active=True).filter(
        db.or_(
            RatePlan.room_type_id == sellable_type_id,
            RatePlan.category_id == sellable_type_id,
        ),
        RatePlan.start_date <= target_date,
        RatePlan.end_date >= target_date,
    ).all()


def _choose_effective_rate_plan(candidate_rate_plans, target_date, seasons):
    priced_candidates = []
    for rate_plan in candidate_rate_plans:
        nightly_rate = calculate_nightly_rate(
            rate_plan=rate_plan,
            target_date=target_date,
            stay_length=1,
            adults=rate_plan.included_occupancy or 2,
            children=0,
            seasons=seasons,
        )
        priced_candidates.append((nightly_rate, rate_plan.id, rate_plan))

    if not priced_candidates:
        return None, None

    priced_candidates.sort(key=lambda item: (item[0], item[1]))
    chosen_rate, _, chosen_plan = priced_candidates[0]
    return chosen_plan, chosen_rate


def rebuild_room_online_for_category_range(property_id, category_id, start_date, end_date):
    rooms = [
        room for room in Room.query.filter_by(property_id=property_id).all()
        if get_room_sellable_type_id(room) == category_id
    ]
    seasons = get_seasons_for_property(property_id)

    for target_date in _date_range(start_date, end_date):
        candidate_rate_plans = _candidate_rate_plans(property_id, category_id, target_date)
        chosen_plan, chosen_rate = _choose_effective_rate_plan(candidate_rate_plans, target_date, seasons)

        for room in rooms:
            room_online = RoomOnline.query.filter_by(room_id=room.id, date=target_date).first()
            room_type_id = get_room_sellable_type_id(room)

            if room_online and room_online.rate_plan_id is None:
                continue

            if chosen_plan is None:
                if room_online is not None:
                    db.session.delete(room_online)
                continue

            if room_online is None:
                room_online = RoomOnline(
                    room_id=room.id,
                    property_id=property_id,
                    category_id=room.category_id,
                    room_type_id=room_type_id,
                    rate_plan_id=chosen_plan.id,
                    date=target_date,
                    price=chosen_rate,
                )
                db.session.add(room_online)
            else:
                room_online.property_id = property_id
                room_online.category_id = room.category_id
                room_online.room_type_id = room_type_id
                room_online.rate_plan_id = chosen_plan.id
                room_online.price = chosen_rate

    db.session.commit()


def rebuild_room_online_for_property_range(property_id, start_date, end_date):
    category_ids = {
        get_room_sellable_type_id(room)
        for room in Room.query.filter_by(property_id=property_id).all()
        if get_room_sellable_type_id(room)
    }

    for category_id in category_ids:
        rebuild_room_online_for_category_range(
            property_id=property_id,
            category_id=category_id,
            start_date=start_date,
            end_date=end_date,
        )


def generate_or_update_room_online_for_rate_plan(rate_plan):
    rebuild_room_online_for_category_range(
        property_id=rate_plan.property_id,
        category_id=get_rate_plan_room_type_id(rate_plan),
        start_date=rate_plan.start_date,
        end_date=rate_plan.end_date,
    )


def update_room_online_for_season(season):
    rebuild_room_online_for_property_range(
        property_id=season.property_id,
        start_date=season.start_date,
        end_date=season.end_date,
    )
