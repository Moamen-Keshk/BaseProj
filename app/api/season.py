from flask import request, make_response, jsonify
from . import api
import logging
from .models import Season
from .. import db
from app.auth.views import get_current_user


@api.route('/new_season', methods=['POST'])
def new_season():
    user = get_current_user()
    if not isinstance(user, str):
        return _unauthorized_response()

    try:
        season = Season.from_json(request.json)
        db.session.add(season)
        db.session.commit()
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
    user = get_current_user()
    if not isinstance(user, str):
        return _unauthorized_response()

    try:
        season = Season.query.get(season_id)
        if not season:
            return _not_found_response('Season not found.')

        db.session.delete(season)
        db.session.commit()
        return _success_response('Season deleted successfully.', 201)

    except Exception as e:
        logging.exception("Error deleting season: %s", e)
        return _error_response('Failed to delete season.', 500)


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
