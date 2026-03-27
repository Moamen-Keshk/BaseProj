from flask import Blueprint, jsonify, request

from app import db
from app.api.channel_manager.models import (
    ChannelConnection,
    ChannelRoomMap,
    ChannelRatePlanMap,
    ChannelSyncJob,
)

channel_manager_bp = Blueprint("channel_manager", __name__, url_prefix="/api/channel-manager")


@channel_manager_bp.get("/connections")
def list_connections():
    property_id = request.args.get("property_id", type=int)

    query = ChannelConnection.query
    if property_id:
        query = query.filter_by(property_id=property_id)

    items = query.all()

    return jsonify([
        {
            "id": item.id,
            "property_id": item.property_id,
            "channel_code": item.channel_code,
            "status": item.status,
            "polling_enabled": item.polling_enabled,
            "last_success_at": item.last_success_at.isoformat() if item.last_success_at else None,
            "last_error_at": item.last_error_at.isoformat() if item.last_error_at else None,
        }
        for item in items
    ])


@channel_manager_bp.post("/connections")
def create_connection():
    data = request.get_json() or {}

    item = ChannelConnection(
        property_id=data["property_id"],
        channel_code=data["channel_code"],
        status=data.get("status", "inactive"),
        credentials_json=data.get("credentials_json", {}),
        settings_json=data.get("settings_json", {}),
        polling_enabled=data.get("polling_enabled", True),
    )

    db.session.add(item)
    db.session.commit()

    return jsonify({"id": item.id}), 201


@channel_manager_bp.get("/room-maps")
def list_room_maps():
    property_id = request.args.get("property_id", type=int)
    channel_code = request.args.get("channel")

    query = ChannelRoomMap.query
    if property_id:
        query = query.filter_by(property_id=property_id)
    if channel_code:
        query = query.filter_by(channel_code=channel_code)

    items = query.all()

    return jsonify([
        {
            "id": item.id,
            "property_id": item.property_id,
            "channel_code": item.channel_code,
            "internal_room_id": item.internal_room_id,
            "external_room_id": item.external_room_id,
            "external_room_name": item.external_room_name,
            "is_active": item.is_active,
        }
        for item in items
    ])


@channel_manager_bp.post("/room-maps")
def create_room_map():
    data = request.get_json() or {}

    item = ChannelRoomMap(
        property_id=data["property_id"],
        channel_code=data["channel_code"],
        internal_room_id=data["internal_room_id"],
        external_room_id=data["external_room_id"],
        external_room_name=data.get("external_room_name"),
        is_active=data.get("is_active", True),
    )

    db.session.add(item)
    db.session.commit()

    return jsonify({"id": item.id}), 201


@channel_manager_bp.get("/rate-maps")
def list_rate_maps():
    property_id = request.args.get("property_id", type=int)
    channel_code = request.args.get("channel")

    query = ChannelRatePlanMap.query
    if property_id:
        query = query.filter_by(property_id=property_id)
    if channel_code:
        query = query.filter_by(channel_code=channel_code)

    items = query.all()

    return jsonify([
        {
            "id": item.id,
            "property_id": item.property_id,
            "channel_code": item.channel_code,
            "internal_rate_plan_id": item.internal_rate_plan_id,
            "external_rate_plan_id": item.external_rate_plan_id,
            "external_rate_plan_name": item.external_rate_plan_name,
            "pricing_model": item.pricing_model,
            "is_active": item.is_active,
        }
        for item in items
    ])


@channel_manager_bp.post("/rate-maps")
def create_rate_map():
    data = request.get_json() or {}

    item = ChannelRatePlanMap(
        property_id=data["property_id"],
        channel_code=data["channel_code"],
        internal_rate_plan_id=data["internal_rate_plan_id"],
        external_rate_plan_id=data["external_rate_plan_id"],
        external_rate_plan_name=data.get("external_rate_plan_name"),
        pricing_model=data.get("pricing_model"),
        is_active=data.get("is_active", True),
    )

    db.session.add(item)
    db.session.commit()

    return jsonify({"id": item.id}), 201


@channel_manager_bp.get("/jobs")
def list_jobs():
    property_id = request.args.get("property_id", type=int)
    channel_code = request.args.get("channel")

    query = ChannelSyncJob.query
    if property_id:
        query = query.filter_by(property_id=property_id)
    if channel_code:
        query = query.filter_by(channel_code=channel_code)

    items = query.order_by(ChannelSyncJob.created_at.desc()).limit(200).all()

    return jsonify([
        {
            "id": item.id,
            "property_id": item.property_id,
            "channel_code": item.channel_code,
            "job_type": item.job_type,
            "status": item.status,
            "attempts": item.attempts,
            "last_error": item.last_error,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        }
        for item in items
    ])