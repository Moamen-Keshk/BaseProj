from datetime import datetime, timezone
from app import db


class ChannelConnection(db.Model):
    __tablename__ = "channel_connections"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id"), nullable=False, index=True)
    channel_code = db.Column(db.String(32), nullable=False, index=True)  # booking_com, expedia
    status = db.Column(db.String(20), nullable=False, default="inactive")  # inactive, active, error
    credentials_json = db.Column(db.JSON, nullable=False, default=dict)
    settings_json = db.Column(db.JSON, nullable=False, default=dict)
    polling_enabled = db.Column(db.Boolean, default=True)
    last_success_at = db.Column(db.DateTime(timezone=True))
    last_error_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint("property_id", "channel_code", name="uq_channel_connection_property_channel"),
    )


class ChannelRoomMap(db.Model):
    __tablename__ = "channel_room_maps"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id"), nullable=False, index=True)
    channel_code = db.Column(db.String(32), nullable=False, index=True)
    internal_room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False, index=True)
    external_room_id = db.Column(db.String(128), nullable=False)
    external_room_name = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint("property_id", "channel_code", "internal_room_id", name="uq_room_map_internal"),
        db.UniqueConstraint("property_id", "channel_code", "external_room_id", name="uq_room_map_external"),
    )


class ChannelRatePlanMap(db.Model):
    __tablename__ = "channel_rate_plan_maps"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id"), nullable=False, index=True)
    channel_code = db.Column(db.String(32), nullable=False, index=True)
    internal_rate_plan_id = db.Column(db.Integer, db.ForeignKey("rate_plans.id"), nullable=False, index=True)
    external_rate_plan_id = db.Column(db.String(128), nullable=False)
    external_rate_plan_name = db.Column(db.String(255))
    pricing_model = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint("property_id", "channel_code", "internal_rate_plan_id", name="uq_rate_map_internal"),
        db.UniqueConstraint("property_id", "channel_code", "external_rate_plan_id", name="uq_rate_map_external"),
    )


class ChannelSyncJob(db.Model):
    __tablename__ = "channel_sync_jobs"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id"), nullable=False, index=True)
    channel_code = db.Column(db.String(32), nullable=False, index=True)
    job_type = db.Column(db.String(32), nullable=False, index=True)  # ari_push, reservation_pull, reservation_ack, reconcile
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    payload_json = db.Column(db.JSON, nullable=False, default=dict)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=10)
    next_retry_at = db.Column(db.DateTime(timezone=True))
    correlation_id = db.Column(db.String(64), index=True)
    last_error = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))


class ChannelReservationLink(db.Model):
    __tablename__ = "channel_reservation_links"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id"), nullable=False, index=True)
    channel_code = db.Column(db.String(32), nullable=False, index=True)
    external_reservation_id = db.Column(db.String(128), nullable=False, index=True)
    external_version = db.Column(db.String(128))
    internal_booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="imported")
    last_seen_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint(
            "property_id",
            "channel_code",
            "external_reservation_id",
            name="uq_channel_reservation_link",
        ),
    )


class ChannelMessageLog(db.Model):
    __tablename__ = "channel_message_logs"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id"), nullable=False, index=True)
    channel_code = db.Column(db.String(32), nullable=False, index=True)
    direction = db.Column(db.String(10), nullable=False)  # inbound / outbound
    message_type = db.Column(db.String(32), nullable=False)  # ari / reservation / ack / reconcile
    related_job_id = db.Column(db.Integer, db.ForeignKey("channel_sync_jobs.id"))
    http_status = db.Column(db.Integer)
    success = db.Column(db.Boolean, default=False)
    request_body = db.Column(db.Text)
    response_body = db.Column(db.Text)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))