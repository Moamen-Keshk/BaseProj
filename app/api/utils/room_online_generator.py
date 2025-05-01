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
            # Determine base rate
            is_weekend = date.weekday() in [5, 6]
            base_price = rate_plan.weekend_rate if is_weekend and rate_plan.weekend_rate else rate_plan.base_rate

            # Check if date is in any season
            in_season = any(season.start_date <= date <= season.end_date for season in seasons)
            if in_season and rate_plan.seasonal_multiplier:
                base_price *= rate_plan.seasonal_multiplier

            # Upsert RoomOnline
            room_online = RoomOnline.query.filter_by(room_id=room.id, date=date).first()
            if room_online:
                room_online.price = base_price
            else:
                room_online = RoomOnline(
                    room_id=room.id,
                    property_id=rate_plan.property_id,
                    category_id=rate_plan.category_id,
                    date=date,
                    price=base_price
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
        rate_plan = RatePlan.query.filter_by(
            property_id=ro.property_id,
            category_id=ro.category_id
        ).filter(
            RatePlan.start_date <= ro.date,
            RatePlan.end_date >= ro.date,
            RatePlan.is_active == True
        ).first()

        if rate_plan:
            is_weekend = ro.date.weekday() in [5, 6]
            base_price = rate_plan.weekend_rate if is_weekend and rate_plan.weekend_rate else rate_plan.base_rate

            # Only apply seasonal multiplier if this date is still in a valid season
            if rate_plan.seasonal_multiplier:
                in_season = season.start_date <= ro.date <= season.end_date
                if in_season:
                    base_price *= rate_plan.seasonal_multiplier

            ro.price = base_price

    db.session.commit()

