from app.api.models import Room, RoomOnline, RatePlan, Season
from datetime import timedelta
from app import db

def generate_or_update_room_online_for_rate_plan(rate_plan):
    rooms = Room.query.filter_by(
        property_id=rate_plan.property_id,
        category_id=rate_plan.category_id
    ).all()

    seasons = Season.query.filter_by(property_id=rate_plan.property_id).all()

    date = rate_plan.start_date
    while date <= rate_plan.end_date:
        for room in rooms:
            # Check if weekend
            is_weekend = date.weekday() in [5, 6]
            price = rate_plan.weekend_rate if is_weekend and rate_plan.weekend_rate else rate_plan.base_rate

            # Apply seasonal multiplier if applicable
            for season in seasons:
                if season.start_date <= date <= season.end_date and rate_plan.seasonal_multiplier:
                    price *= rate_plan.seasonal_multiplier
                    break

            # Upsert RoomOnline
            room_online = RoomOnline.query.filter_by(room_id=room.id, date=date).first()
            if room_online:
                room_online.price = price
            else:
                room_online = RoomOnline(
                    room_id=room.id,
                    property_id=rate_plan.property_id,
                    category_id=rate_plan.category_id,
                    date=date,
                    price=price
                )
                db.session.add(room_online)
        date += timedelta(days=1)

    db.session.commit()


def update_room_online_for_season(season):
    room_rates = RoomOnline.query.filter(
        RoomOnline.property_id == season.property_id,
        RoomOnline.date >= season.start_date,
        RoomOnline.date <= season.end_date
    ).all()

    for ro in room_rates:
        # reapply seasonal multiplier if applicable
        rate_plan = RatePlan.query.filter_by(
            property_id=ro.property_id,
            category_id=ro.category_id
        ).filter(
            RatePlan.start_date <= ro.date,
            RatePlan.end_date >= ro.date
        ).first()

        if rate_plan:
            is_weekend = ro.date.weekday() in [5, 6]
            base = rate_plan.weekend_rate if is_weekend and rate_plan.weekend_rate else rate_plan.base_rate
            if rate_plan.seasonal_multiplier:
                base *= rate_plan.seasonal_multiplier
            ro.price = base

    db.session.commit()
