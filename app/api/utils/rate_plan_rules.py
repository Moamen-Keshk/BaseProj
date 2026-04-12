from app import db
from app.api.models import RatePlan, Season


def date_ranges_overlap(start_date, end_date, other_start_date, other_end_date):
    return start_date <= other_end_date and end_date >= other_start_date


def get_overlapping_rate_plans(property_id, category_id, start_date, end_date, exclude_rate_plan_id=None):
    query = RatePlan.query.filter(
        RatePlan.property_id == property_id,
        db.or_(
            RatePlan.room_type_id == category_id,
            RatePlan.category_id == category_id,
        ),
        RatePlan.start_date <= end_date,
        RatePlan.end_date >= start_date,
    )

    if exclude_rate_plan_id is not None:
        query = query.filter(RatePlan.id != exclude_rate_plan_id)

    return query.order_by(RatePlan.start_date, RatePlan.id).all()


def get_overlapping_seasons(property_id, start_date, end_date, exclude_season_id=None):
    query = Season.query.filter_by(property_id=property_id).filter(
        Season.start_date <= end_date,
        Season.end_date >= start_date,
    )

    if exclude_season_id is not None:
        query = query.filter(Season.id != exclude_season_id)

    return query.order_by(Season.start_date, Season.id).all()
