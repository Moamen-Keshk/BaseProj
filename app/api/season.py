from flask import request, make_response, jsonify
from . import api
import logging
from .models import Season, RatePlan, RoomOnline
from .. import db
from app.auth.views import get_current_user
from app.api.utils.room_online_generator import update_room_online_for_season


@api.route('/new_season', methods=['POST'])
def new_season():
    user = get_current_user()
    if not isinstance(user, str):
        return _unauthorized_response()

    try:
        season = Season.from_json(request.json)
        db.session.add(season)
        db.session.commit()
        update_room_online_for_season(season)
        return _success_response('Season added successfully.', 201)
    except Exception as e:
        logging.exception("Error adding season: %s", e)
        return _error_response('Failed to add season.', 400)


@api.route('/update_season/<int:season_id>', methods=['PUT'])
def update_season(season_id):
    user = get_current_user()
    if not isinstance(user, str):
        return _unauthorized_response()

    try:
        data = request.get_json()
        season = Season.query.get(season_id)

        if not season:
            return _not_found_response('Season not found.')

        if 'property_id' in data:
            season.property_id = data['property_id']
        if 'rate_plan_id' in data:
            season.rate_plan_id = data['rate_plan_id']
        if 'start_date' in data:
            season.start_date = data['start_date']
        if 'end_date' in data:
            season.end_date = data['end_date']
        if 'label' in data:
            season.label = data['label']

        db.session.commit()
        update_room_online_for_season(season)
        return _success_response('Season updated successfully.', 201)

    except Exception as e:
        logging.exception("Error updating season: %s", e)
        return _error_response('Failed to update season.', 500)


@api.route('/all_seasons/<int:property_id>', methods=['GET'])
def all_seasons(property_id):
    user = get_current_user()
    if not isinstance(user, str):
        return _unauthorized_response()

    try:
        seasons = Season.query.filter_by(property_id=property_id).all()
        season_list = [s.to_json() for s in seasons]

        return make_response(jsonify({
            'status': 'success',
            'data': season_list,
            'page': 0
        })), 201

    except Exception as e:
        logging.exception("Error retrieving seasons: %s", e)
        return _error_response('Failed to retrieve seasons.', 500)


@api.route('/delete_season/<int:season_id>', methods=['DELETE'])
def delete_season(season_id):
    try:
        user = get_current_user()
        if not isinstance(user, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        season = db.session.query(Season).filter_by(id=season_id).first()
        if not season:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Season not found.'
            })), 404

        # Store values before deletion
        property_id = season.property_id
        start_date = season.start_date
        end_date = season.end_date

        # Delete the season
        db.session.delete(season)
        db.session.flush()  # Don't commit yet

        # Recalculate room_online prices for affected entries
        affected_room_online = RoomOnline.query.filter(
            RoomOnline.property_id == property_id,
            RoomOnline.date >= start_date,
            RoomOnline.date <= end_date
        ).all()

        for entry in affected_room_online:
            matching_plan = RatePlan.query.filter(
                RatePlan.property_id == entry.property_id,
                RatePlan.category_id == entry.category_id,
                RatePlan.start_date <= entry.date,
                RatePlan.end_date >= entry.date
            ).first()

            if matching_plan:
                is_weekend = entry.date.weekday() in [5, 6]
                new_price = (
                    matching_plan.weekend_rate
                    if is_weekend and matching_plan.weekend_rate is not None
                    else matching_plan.base_rate
                )
                entry.price = new_price  # ✅ Remove seasonal multiplier

        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Season deleted and affected room rates reverted.'
        })), 201

    except Exception as e:
        logging.exception("Error in delete_season: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete season. Please try again.'
        })), 500



# Helper Responses
def _success_response(message, code=201):
    return make_response(jsonify({
        'status': 'success',
        'message': message
    })), code


def _error_response(message, code=500):
    return make_response(jsonify({
        'status': 'error',
        'message': message
    })), code


def _not_found_response(message):
    return make_response(jsonify({
        'status': 'fail',
        'message': message
    })), 404


def _unauthorized_response():
    return make_response(jsonify({
        'status': 'fail',
        'message': 'Unauthorized access.'
    })), 401
