from flask import request, make_response, jsonify
import logging

from app import db
from app.auth.utils import get_current_user
from . import channel_manager
from app.api.channel_manager.models import (
    ChannelConnection,
    ChannelRoomMap,
    ChannelRatePlanMap,
    ChannelSyncJob,
    ChannelMessageLog,
    SupportedChannel
)


# ==========================================
# CONNECTIONS
# ==========================================

@channel_manager.route('/connections', methods=['GET'])
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
        })), 201

    except Exception as e:
        logging.exception("Error in list_channel_connections: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch channel connections.'})), 500


@channel_manager.route('/connections', methods=['POST'])
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


@channel_manager.route('/connections/<int:connection_id>', methods=['PUT'])
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
        })), 201

    except Exception as e:
        logging.exception("Error in edit_channel_connection: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to update channel connection.'})), 500


@channel_manager.route('/connections/<int:connection_id>', methods=['DELETE'])
def delete_channel_connection(connection_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        item = ChannelConnection.query.get(connection_id)
        if item:
            db.session.delete(item)
            db.session.commit()

        return make_response(jsonify({'status': 'success', 'message': 'Connection deleted.'})), 201
    except Exception as e:
        logging.exception("Error deleting connection: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to delete connection.'})), 500


@channel_manager.route('/connections/<int:connection_id>/sync', methods=['POST'])
def force_sync_connection(connection_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        connection = ChannelConnection.query.get(connection_id)
        if not connection:
            return make_response(jsonify({'status': 'fail', 'message': 'Connection not found.'})), 404

        # Trigger an ARI push to sync rates and availability immediately
        from app.api.channel_manager.tasks.bulk_push_ari import process_bulk_ari_push
        process_bulk_ari_push.delay(connection.property_id)

        return make_response(jsonify({'status': 'success', 'message': 'Sync started.'})), 201
    except Exception as e:
        logging.exception("Error forcing sync: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to sync.'})), 500


@channel_manager.route('/connections/property/<int:property_id>', methods=['GET'])
def get_property_connections(property_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        connections = ChannelConnection.query.filter_by(property_id=property_id).all()

        data = []
        for conn in connections:
            data.append({
                'id': conn.id,
                'channel_code': conn.channel_code,
                'status': conn.status,
                'created_at': conn.created_at.isoformat() if conn.created_at else None
            })

        return make_response(jsonify({'status': 'success', 'data': data})), 201

    except Exception as e:
        return make_response(jsonify({'status': 'error', 'message': str(e)})), 500


# ==========================================
# ROOM MAPS
# ==========================================

@channel_manager.route('/room_maps', methods=['GET'])
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
        })), 201

    except Exception as e:
        logging.exception("Error in list_channel_room_maps: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch room maps.'})), 500


@channel_manager.route('/room_maps', methods=['POST'])
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


@channel_manager.route('/room_maps/<int:map_id>', methods=['DELETE'])
def delete_room_map(map_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail'})), 401

        item = ChannelRoomMap.query.get(map_id)
        if item:
            db.session.delete(item)
            db.session.commit()
        return make_response(jsonify({'status': 'success'})), 201
    except Exception as e:
        logging.exception("Error deleting room map: %s", str(e))
        return make_response(jsonify({'status': 'error'})), 500


# ==========================================
# RATE MAPS
# ==========================================

@channel_manager.route('/rate_maps', methods=['GET'])
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
        })), 201

    except Exception as e:
        logging.exception("Error in list_channel_rate_maps: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch rate maps.'})), 500


@channel_manager.route('/rate_maps', methods=['POST'])
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


@channel_manager.route('/rate_maps/<int:map_id>', methods=['DELETE'])
def delete_rate_map(map_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail'})), 401

        item = ChannelRatePlanMap.query.get(map_id)
        if item:
            db.session.delete(item)
            db.session.commit()
        return make_response(jsonify({'status': 'success'})), 201
    except Exception as e:
        logging.exception("Error deleting rate map: %s", str(e))
        return make_response(jsonify({'status': 'error'})), 500


# ==========================================
# JOBS & LOGS
# ==========================================

@channel_manager.route('/jobs', methods=['GET'])
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
        })), 201

    except Exception as e:
        logging.exception("Error in list_channel_jobs: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch jobs.'})), 500


@channel_manager.route('/logs', methods=['GET'])
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
        })), 201

    except Exception as e:
        logging.exception("Error in list_channel_logs: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch logs.'})), 500


@channel_manager.route('/jobs/<int:job_id>/run', methods=['POST'])
def run_channel_job(job_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        job = ChannelSyncJob.query.get(job_id)
        if not job:
            return make_response(jsonify({'status': 'fail', 'message': 'Job not found.'})), 404

        if job.job_type == 'ari_push':
            from .tasks.push_ari import process_ari_push_job
            process_ari_push_job.delay(job.id)
        elif job.job_type == 'reservation_pull':
            from .tasks.pull_reservations import process_reservation_pull_job
            process_reservation_pull_job.delay(job.id)
        else:
            from .tasks.retry_jobs import retry_channel_job
            retry_channel_job.delay(job.id)

        return make_response(jsonify({
            'status': 'success',
            'message': 'Job dispatched successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in run_channel_job: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to dispatch job.'})), 500


@channel_manager.route('/jobs/dispatch', methods=['POST'])
def dispatch_channel_jobs():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401
        from .tasks.dispatch_jobs import dispatch_pending_channel_jobs
        dispatch_pending_channel_jobs.delay()

        return make_response(jsonify({'status': 'success', 'message': 'Pending channel jobs dispatched.'})), 201

    except Exception as e:
        logging.exception("Error in dispatch_channel_jobs: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to dispatch pending jobs.'})), 500


@channel_manager.route('/jobs/schedule-pulls', methods=['POST'])
def trigger_schedule_reservation_pulls():
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401
        from .tasks.schedule_pulls import schedule_reservation_pull_jobs
        schedule_reservation_pull_jobs.delay()

        return make_response(jsonify({'status': 'success', 'message': 'Reservation pull scheduling started.'})), 201

    except Exception as e:
        logging.exception("Error in trigger_schedule_reservation_pulls: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to schedule reservation pulls.'})), 500


# ==========================================
# EXTERNAL DISCOVERY ENDPOINTS
# ==========================================

@channel_manager.route('/connections/<int:connection_id>/external_rooms', methods=['GET'])
def get_external_rooms(connection_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        connection = ChannelConnection.query.get(connection_id)
        if not connection:
            return make_response(jsonify({'status': 'fail', 'message': 'Connection not found.'})), 404
        from app.api.channel_manager.adapters import get_adapter
        adapter = get_adapter(connection.channel_code)
        rooms = adapter.fetch_external_rooms(connection)

        return make_response(jsonify({'status': 'success', 'data': rooms})), 201
    except Exception as e:
        logging.exception("Error fetching external rooms: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': str(e)})), 500


@channel_manager.route('/connections/<int:connection_id>/external_rate_plans', methods=['GET'])
def get_external_rate_plans(connection_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        connection = ChannelConnection.query.get(connection_id)
        if not connection:
            return make_response(jsonify({'status': 'fail', 'message': 'Connection not found.'})), 404
        from app.api.channel_manager.adapters import get_adapter
        adapter = get_adapter(connection.channel_code)
        rates = adapter.fetch_external_rate_plans(connection)

        return make_response(jsonify({'status': 'success', 'data': rates})), 201
    except Exception as e:
        logging.exception("Error fetching external rate plans: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': str(e)})), 500


# ==========================================
# BULK MAPPING ACTIONS
# ==========================================

@channel_manager.route('/connections/<int:connection_id>/bulk_map_rooms', methods=['POST'])
def bulk_map_rooms(connection_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        connection = ChannelConnection.query.get(connection_id)
        if not connection:
            return make_response(jsonify({'status': 'fail', 'message': 'Connection not found.'})), 404

        data = request.get_json()
        mappings = data.get('mappings', [])

        ChannelRoomMap.query.filter_by(
            property_id=connection.property_id,
            channel_code=connection.channel_code
        ).update({'is_active': False})

        for item in mappings:
            internal_room_id = item.get('internal_room_id')
            external_room_id = item.get('external_room_id')

            if not internal_room_id or not external_room_id:
                continue

            existing_map = ChannelRoomMap.query.filter_by(
                property_id=connection.property_id,
                channel_code=connection.channel_code,
                internal_room_id=internal_room_id,
                external_room_id=external_room_id
            ).first()

            if existing_map:
                existing_map.is_active = True
            else:
                new_map = ChannelRoomMap(
                    property_id=connection.property_id,
                    channel_code=connection.channel_code,
                    internal_room_id=internal_room_id,
                    external_room_id=external_room_id,
                    is_active=True
                )
                db.session.add(new_map)

        db.session.commit()

        from app.api.channel_manager.tasks.bulk_push_ari import process_bulk_ari_push
        process_bulk_ari_push.delay(connection.property_id)

        return make_response(jsonify({'status': 'success', 'message': 'Rooms mapped successfully.'})), 201

    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': str(e)})), 500


@channel_manager.route('/connections/<int:connection_id>/bulk_map_rate_plans', methods=['POST'])
def bulk_map_rate_plans(connection_id):
    try:
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

        connection = ChannelConnection.query.get(connection_id)
        if not connection:
            return make_response(jsonify({'status': 'fail', 'message': 'Connection not found.'})), 404

        data = request.get_json()
        mappings = data.get('mappings', [])

        ChannelRatePlanMap.query.filter_by(
            property_id=connection.property_id,
            channel_code=connection.channel_code
        ).update({'is_active': False})

        for item in mappings:
            internal_rate_plan_id = item.get('internal_rate_plan_id')
            external_rate_plan_id = item.get('external_rate_plan_id')

            if not internal_rate_plan_id or not external_rate_plan_id:
                continue

            existing_map = ChannelRatePlanMap.query.filter_by(
                property_id=connection.property_id,
                channel_code=connection.channel_code,
                internal_rate_plan_id=internal_rate_plan_id,
                external_rate_plan_id=external_rate_plan_id
            ).first()

            if existing_map:
                existing_map.is_active = True
            else:
                new_map = ChannelRatePlanMap(
                    property_id=connection.property_id,
                    channel_code=connection.channel_code,
                    internal_rate_plan_id=internal_rate_plan_id,
                    external_rate_plan_id=external_rate_plan_id,
                    is_active=True
                )
                db.session.add(new_map)

        db.session.commit()

        from app.api.channel_manager.tasks.bulk_push_ari import process_bulk_ari_push
        process_bulk_ari_push.delay(connection.property_id)

        return make_response(jsonify({'status': 'success', 'message': 'Rate Plans mapped successfully.'})), 201

    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': str(e)})), 500


# ==========================================
# WEBHOOKS
# ==========================================

@channel_manager.route('/webhooks/booking_com', methods=['POST'])
def booking_com_webhook():
    raw_payload = request.get_data(as_text=True)
    property_id = 1
    from app.api.channel_manager.services.sync_dispatcher import SyncDispatcher
    SyncDispatcher.queue_reservation_pull(property_id=property_id, channel_code='booking_com',
                                          cursor={"payload": raw_payload})
    return make_response(jsonify({"status": "acknowledged"})), 201


@channel_manager.route('/webhooks/expedia', methods=['POST'])
def expedia_webhook():
    raw_payload = request.get_data(as_text=True)
    property_id = 1
    from app.api.channel_manager.services.sync_dispatcher import SyncDispatcher
    SyncDispatcher.queue_reservation_pull(property_id=property_id, channel_code='expedia',
                                          cursor={"payload": raw_payload})
    return make_response(jsonify({"status": "acknowledged"})), 201


@channel_manager.route('/supported-channels', methods=['GET'])
def get_supported_channels():
    """Fetch all active supported channels."""
    channels = SupportedChannel.query.filter_by(is_active=True).all()
    return jsonify([channel.to_json() for channel in channels]), 201


@channel_manager.route('/supported-channels', methods=['POST'])
def add_supported_channel():
    """Add a new supported channel from the frontend."""
    data = request.get_json()

    # Basic validation
    if not data or not data.get('name') or not data.get('code'):
        return jsonify({'error': 'Name and code are required'}), 400

    # Check if code already exists to prevent duplicate entries
    if SupportedChannel.query.filter_by(code=data['code']).first():
        return jsonify({'error': 'Channel with this code already exists'}), 409

    new_channel = SupportedChannel(
        name=data['name'],
        code=data['code'],
        logo=data.get('logo', '🔗'),  # Default logo if none provided
        is_active=data.get('is_active', True)
    )

    db.session.add(new_channel)
    db.session.commit()

    return jsonify(new_channel.to_json()), 201