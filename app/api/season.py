import logging
from datetime import datetime
from types import SimpleNamespace
from flask import request, make_response, jsonify

from . import api
from app.api.models import Season
from .. import db
from app.api.decorators import require_permission
from app.api.utils.room_online_generator import update_room_online_for_season
from app.api.utils.rate_plan_rules import get_overlapping_seasons
from app.api.utils.revenue_management import rebuild_daily_rates_for_property_range
from app.api.channel_manager.services.pms_sync import (
    queue_season_ari_sync,
    queue_season_transition_ari_sync,
)


def _season_conflict_payload(seasons):
    return [
        {
            'id': season.id,
            'label': season.label,
            'start_date': season.start_date.isoformat() if season.start_date else None,
            'end_date': season.end_date.isoformat() if season.end_date else None,
        }
        for season in seasons
    ]


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
        start_date = season.start_date
        end_date = season.end_date

        if start_date > end_date:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Start date cannot be after end date.'
            })), 400

        overlapping = get_overlapping_seasons(
            property_id=property_id,
            start_date=start_date,
            end_date=end_date,
        )
        if overlapping:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Season dates overlap an existing season.',
                'conflicts': _season_conflict_payload(overlapping),
            })), 409

        db.session.add(season)
        db.session.commit()

        rebuild_daily_rates_for_property_range(property_id, start_date, end_date)
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

        new_start_date = data.get('start_date')
        if new_start_date is not None:
            new_start_date = datetime.fromisoformat(new_start_date).date()
        else:
            new_start_date = season.start_date

        new_end_date = data.get('end_date')
        if new_end_date is not None:
            new_end_date = datetime.fromisoformat(new_end_date).date()
        else:
            new_end_date = season.end_date

        if new_start_date > new_end_date:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Start date cannot be after end date.'
            })), 400

        overlapping = get_overlapping_seasons(
            property_id=property_id,
            start_date=new_start_date,
            end_date=new_end_date,
            exclude_season_id=season.id,
        )
        if overlapping:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Season dates overlap an existing season.',
                'conflicts': _season_conflict_payload(overlapping),
            })), 409

        season.start_date = new_start_date
        season.end_date = new_end_date
        if 'label' in data:
            season.label = data['label']

        db.session.commit()
        rebuild_daily_rates_for_property_range(property_id, new_start_date, new_end_date)
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

        rebuild_daily_rates_for_property_range(property_id_stored, start_date, end_date)
        update_room_online_for_season(SimpleNamespace(
            property_id=property_id_stored,
            start_date=start_date,
            end_date=end_date,
        ))

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
