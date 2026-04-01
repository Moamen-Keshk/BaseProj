import logging
from types import SimpleNamespace
from flask import request, make_response, jsonify

from . import api
from app.api.models import Season, RatePlan, RoomOnline
from .. import db
from app.api.decorators import require_permission
from app.api.utils.room_online_generator import update_room_online_for_season
from app.api.channel_manager.services.pms_sync import (
    queue_season_ari_sync,
    queue_season_transition_ari_sync,
)


@api.route('/properties/<int:property_id>/seasons', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def new_season(property_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        season_data = request.get_json()
        # Enforce property_id from the secured URL
        season_data['property_id'] = property_id

        season = Season.from_json(season_data)
        db.session.add(season)
        db.session.commit()

        update_room_online_for_season(season)

        # New season = only queue the new range
        queue_season_ari_sync(season, 'season_created')

        return make_response(jsonify({
            'status': 'success',
            'message': 'Season added successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error adding season: %s", e)
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to add season.'
        })), 500


@api.route('/properties/<int:property_id>/seasons/<int:season_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def update_season(property_id, season_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = request.get_json()

        # Secure fetch with property_id
        season = Season.query.filter_by(id=season_id, property_id=property_id).first()

        if not season:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Season not found in this property.'
            })), 404

        old_property_id = season.property_id
        old_start_date = season.start_date
        old_end_date = season.end_date

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

        queue_season_transition_ari_sync(
            old_property_id=old_property_id,
            old_start_date=old_start_date,
            old_end_date=old_end_date,
            season=season,
            reason='season_updated',
        )

        return make_response(jsonify({
            'status': 'success',
            'message': 'Season updated successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error updating season: %s", e)
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update season.'
        })), 500


@api.route('/properties/<int:property_id>/seasons', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_rates')
def all_seasons(property_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        seasons = Season.query.filter_by(property_id=property_id).all()
        season_list = [s.to_json() for s in seasons]

        return make_response(jsonify({
            'status': 'success',
            'data': season_list,
            'page': 0
        })), 200

    except Exception as e:
        logging.exception("Error retrieving seasons: %s", e)
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to retrieve seasons.'
        })), 500


@api.route('/properties/<int:property_id>/seasons/<int:season_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_rates')
def delete_season(property_id, season_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        # Secure fetch with property_id
        season = db.session.query(Season).filter_by(id=season_id, property_id=property_id).first()
        if not season:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Season not found in this property.'
            })), 404

        # Store values before deletion
        property_id_stored = season.property_id
        start_date = season.start_date
        end_date = season.end_date

        # Delete the season
        db.session.delete(season)
        db.session.flush()  # Don't commit yet

        # Recalculate room_online prices for affected entries
        affected_room_online = RoomOnline.query.filter(
            RoomOnline.property_id == property_id_stored,
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
                entry.price = new_price

        db.session.commit()

        deleted_snapshot = SimpleNamespace(
            property_id=property_id_stored,
            start_date=start_date,
            end_date=end_date,
        )

        queue_season_ari_sync(deleted_snapshot, 'season_deleted')

        return make_response(jsonify({
            'status': 'success',
            'message': 'Season deleted and affected room rates reverted.'
        })), 200

    except Exception as e:
        logging.exception("Error in delete_season: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete season. Please try again.'
        })), 500