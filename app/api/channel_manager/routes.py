from flask import request, make_response, jsonify
import logging

from app import db
from app.auth.utils import get_current_user
from app.api import api
from app.api.channel_manager.models import (
    ChannelConnection,
    ChannelRoomMap,
    ChannelRatePlanMap,
    ChannelSyncJob,
    ChannelMessageLog,
)
from app.api.channel_manager.tasks.push_ari import process_ari_push_job
from app.api.channel_manager.tasks.pull_reservations import process_reservation_pull_job
from app.api.channel_manager.tasks.retry_jobs import retry_channel_job
from app.api.channel_manager.tasks.dispatch_jobs import dispatch_pending_channel_jobs
from app.api.channel_manager.tasks.schedule_pulls import schedule_reservation_pull_jobs

@api.route('/channel_manager/connections', methods=['GET'])
def list_channel_connections():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        property_id = request.args.get('property_id', type=int)

        query = ChannelConnection.query
        if property_id:
            query = query.filter_by(property_id=property_id)

        items = query.all()

        return make_response(jsonify({
            'status': 'success',
            'data': [item.to_json() for item in items]
        })), 200

    except Exception as e:
        logging.exception("Error in list_channel_connections: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch channel connections.'})), 500


@api.route('/channel_manager/connections', methods=['POST'])
def create_channel_connection():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        data = request.get_json() or {}

        item = ChannelConnection(
            property_id=data['property_id'],
            channel_code=data['channel_code'],
            status=data.get('status', 'inactive'),
            credentials_json=data.get('credentials_json', {}),
            settings_json=data.get('settings_json', {}),
            polling_enabled=data.get('polling_enabled', True),
        )

        db.session.add(item)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Channel connection created successfully.',
            'data': item.to_json()
        })), 201

    except Exception as e:
        logging.exception("Error in create_channel_connection: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to create channel connection.'})), 500


@api.route('/channel_manager/connections/<int:connection_id>', methods=['PUT'])
def edit_channel_connection(connection_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        data = request.get_json() or {}
        item = ChannelConnection.query.get(connection_id)

        if not item:
            return make_response(jsonify({'status': 'fail', 'message': 'Channel connection not found.'})), 404

        if 'status' in data:
            item.status = data['status']
        if 'credentials_json' in data:
            item.credentials_json = data['credentials_json']
        if 'settings_json' in data:
            item.settings_json = data['settings_json']
        if 'polling_enabled' in data:
            item.polling_enabled = data['polling_enabled']

        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Channel connection updated successfully.',
            'data': item.to_json()
        })), 200

    except Exception as e:
        logging.exception("Error in edit_channel_connection: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to update channel connection.'})), 500


@api.route('/channel_manager/room_maps', methods=['GET'])
def list_channel_room_maps():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        property_id = request.args.get('property_id', type=int)
        channel_code = request.args.get('channel_code', type=str)

        query = ChannelRoomMap.query
        if property_id:
            query = query.filter_by(property_id=property_id)
        if channel_code:
            query = query.filter_by(channel_code=channel_code)

        items = query.all()

        return make_response(jsonify({
            'status': 'success',
            'data': [item.to_json() for item in items]
        })), 200

    except Exception as e:
        logging.exception("Error in list_channel_room_maps: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch room maps.'})), 500


@api.route('/channel_manager/room_maps', methods=['POST'])
def create_channel_room_map():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        data = request.get_json() or {}

        item = ChannelRoomMap(
            property_id=data['property_id'],
            channel_code=data['channel_code'],
            internal_room_id=data['internal_room_id'],
            external_room_id=data['external_room_id'],
            external_room_name=data.get('external_room_name'),
            is_active=data.get('is_active', True),
        )

        db.session.add(item)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Room mapping created successfully.',
            'data': item.to_json()
        })), 201

    except Exception as e:
        logging.exception("Error in create_channel_room_map: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to create room mapping.'})), 500


@api.route('/channel_manager/rate_maps', methods=['GET'])
def list_channel_rate_maps():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        property_id = request.args.get('property_id', type=int)
        channel_code = request.args.get('channel_code', type=str)

        query = ChannelRatePlanMap.query
        if property_id:
            query = query.filter_by(property_id=property_id)
        if channel_code:
            query = query.filter_by(channel_code=channel_code)

        items = query.all()

        return make_response(jsonify({
            'status': 'success',
            'data': [item.to_json() for item in items]
        })), 200

    except Exception as e:
        logging.exception("Error in list_channel_rate_maps: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch rate maps.'})), 500


@api.route('/channel_manager/rate_maps', methods=['POST'])
def create_channel_rate_map():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        data = request.get_json() or {}

        item = ChannelRatePlanMap(
            property_id=data['property_id'],
            channel_code=data['channel_code'],
            internal_rate_plan_id=data['internal_rate_plan_id'],
            external_rate_plan_id=data['external_rate_plan_id'],
            external_rate_plan_name=data.get('external_rate_plan_name'),
            pricing_model=data.get('pricing_model'),
            is_active=data.get('is_active', True),
        )

        db.session.add(item)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Rate mapping created successfully.',
            'data': item.to_json()
        })), 201

    except Exception as e:
        logging.exception("Error in create_channel_rate_map: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to create rate mapping.'})), 500


@api.route('/channel_manager/jobs', methods=['GET'])
def list_channel_jobs():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        property_id = request.args.get('property_id', type=int)
        channel_code = request.args.get('channel_code', type=str)

        query = ChannelSyncJob.query
        if property_id:
            query = query.filter_by(property_id=property_id)
        if channel_code:
            query = query.filter_by(channel_code=channel_code)

        items = query.order_by(ChannelSyncJob.created_at.desc()).limit(200).all()

        return make_response(jsonify({
            'status': 'success',
            'data': [item.to_json() for item in items]
        })), 200

    except Exception as e:
        logging.exception("Error in list_channel_jobs: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch jobs.'})), 500


@api.route('/channel_manager/logs', methods=['GET'])
def list_channel_logs():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        property_id = request.args.get('property_id', type=int)
        channel_code = request.args.get('channel_code', type=str)

        query = ChannelMessageLog.query
        if property_id:
            query = query.filter_by(property_id=property_id)
        if channel_code:
            query = query.filter_by(channel_code=channel_code)

        items = query.order_by(ChannelMessageLog.created_at.desc()).limit(200).all()

        return make_response(jsonify({
            'status': 'success',
            'data': [item.to_json() for item in items]
        })), 200

    except Exception as e:
        logging.exception("Error in list_channel_logs: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch logs.'})), 500


@api.route('/channel_manager/jobs/<int:job_id>/run', methods=['POST'])
def run_channel_job(job_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        job = ChannelSyncJob.query.get(job_id)
        if not job:
            return make_response(jsonify({'status': 'fail', 'message': 'Job not found.'})), 404

        if job.job_type == 'ari_push':
            process_ari_push_job.delay(job.id)
        elif job.job_type == 'reservation_pull':
            process_reservation_pull_job.delay(job.id)
        else:
            retry_channel_job.delay(job.id)

        return make_response(jsonify({
            'status': 'success',
            'message': 'Job dispatched successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error in run_channel_job: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to dispatch job.'})), 500

@api.route('/channel_manager/jobs/dispatch', methods=['POST'])
def dispatch_channel_jobs():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        dispatch_pending_channel_jobs.delay()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Pending channel jobs dispatched.'
        })), 200

    except Exception as e:
        logging.exception("Error in dispatch_channel_jobs: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to dispatch pending jobs.'
        })), 500


@api.route('/channel_manager/jobs/schedule-pulls', methods=['POST'])
def trigger_schedule_reservation_pulls():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        schedule_reservation_pull_jobs.delay()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Reservation pull scheduling started.'
        })), 200

    except Exception as e:
        logging.exception("Error in trigger_schedule_reservation_pulls: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to schedule reservation pulls.'
        })), 500