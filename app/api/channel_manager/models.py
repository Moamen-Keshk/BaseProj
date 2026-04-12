from datetime import datetime, timezone

from app import db

class ChannelConnection(db.Model):
    __tablename__ = 'channel_connections'

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, index=True)
    channel_code = db.Column(db.String(32), db.ForeignKey('supported_channels.code'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='inactive')  # inactive, active, error
    credentials_json = db.Column(db.JSON, nullable=False, default=dict)
    settings_json = db.Column(db.JSON, nullable=False, default=dict)
    polling_enabled = db.Column(db.Boolean, default=True)
    last_success_at = db.Column(db.DateTime(timezone=True))
    last_error_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        db.UniqueConstraint('property_id', 'channel_code', name='uq_channel_connection_property_channel'),
    )

    def to_json(self):
        return {
            'id': self.id,
            'property_id': self.property_id,
            'channel_code': self.channel_code,
            'status': self.status,
            'credentials_json': self.credentials_json or {},
            'settings_json': self.settings_json or {},
            'polling_enabled': self.polling_enabled,
            'last_success_at': self.last_success_at.isoformat() if self.last_success_at else None,
            'last_error_at': self.last_error_at.isoformat() if self.last_error_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ChannelRoomMap(db.Model):
    __tablename__ = 'channel_room_maps'

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, index=True)
    channel_code = db.Column(db.String(32), nullable=False, index=True)
    internal_room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False, index=True)
    external_room_id = db.Column(db.String(128), nullable=False)
    external_room_name = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint('property_id', 'channel_code', 'internal_room_id', name='uq_room_map_internal'),
        db.UniqueConstraint('property_id', 'channel_code', 'external_room_id', name='uq_room_map_external'),
    )

    def to_json(self):
        return {
            'id': self.id,
            'property_id': self.property_id,
            'channel_code': self.channel_code,
            'internal_room_id': self.internal_room_id,
            'external_room_id': self.external_room_id,
            'external_room_name': self.external_room_name,
            'is_active': self.is_active,
        }


class ChannelRatePlanMap(db.Model):
    __tablename__ = 'channel_rate_plan_maps'

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, index=True)
    channel_code = db.Column(db.String(32), nullable=False, index=True)
    internal_rate_plan_id = db.Column(db.Integer, db.ForeignKey('rate_plans.id'), nullable=False, index=True)
    external_rate_plan_id = db.Column(db.String(128), nullable=False)
    external_rate_plan_name = db.Column(db.String(255))
    pricing_model = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint('property_id', 'channel_code', 'internal_rate_plan_id', name='uq_rate_map_internal'),
        db.UniqueConstraint('property_id', 'channel_code', 'external_rate_plan_id', name='uq_rate_map_external'),
    )

    def to_json(self):
        return {
            'id': self.id,
            'property_id': self.property_id,
            'channel_code': self.channel_code,
            'internal_rate_plan_id': self.internal_rate_plan_id,
            'external_rate_plan_id': self.external_rate_plan_id,
            'external_rate_plan_name': self.external_rate_plan_name,
            'pricing_model': self.pricing_model,
            'is_active': self.is_active,
        }


class ChannelSyncJob(db.Model):
    __tablename__ = 'channel_sync_jobs'

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, index=True)
    channel_code = db.Column(db.String(32), nullable=False, index=True)
    job_type = db.Column(db.String(32), nullable=False, index=True)  # ari_push, reservation_pull, reservation_ack, reconcile
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    payload_json = db.Column(db.JSON, nullable=False, default=dict)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=10)
    next_retry_at = db.Column(db.DateTime(timezone=True))
    correlation_id = db.Column(db.String(64), index=True)
    last_error = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))

    def to_json(self):
        return {
            'id': self.id,
            'property_id': self.property_id,
            'channel_code': self.channel_code,
            'job_type': self.job_type,
            'status': self.status,
            'payload_json': self.payload_json or {},
            'attempts': self.attempts,
            'max_attempts': self.max_attempts,
            'next_retry_at': self.next_retry_at.isoformat() if self.next_retry_at else None,
            'correlation_id': self.correlation_id,
            'last_error': self.last_error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class ChannelReservationLink(db.Model):
    __tablename__ = 'channel_reservation_links'

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, index=True)
    channel_code = db.Column(db.String(32), nullable=False, index=True)
    external_reservation_id = db.Column(db.String(128), nullable=False, index=True)
    external_version = db.Column(db.String(128))
    internal_booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='imported')
    last_seen_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint(
            'property_id', 'channel_code', 'external_reservation_id',
            name='uq_channel_reservation_link'
        ),
    )

    def to_json(self):
        return {
            'id': self.id,
            'property_id': self.property_id,
            'channel_code': self.channel_code,
            'external_reservation_id': self.external_reservation_id,
            'external_version': self.external_version,
            'internal_booking_id': self.internal_booking_id,
            'status': self.status,
            'last_seen_at': self.last_seen_at.isoformat() if self.last_seen_at else None,
        }


class ChannelMessageLog(db.Model):
    __tablename__ = 'channel_message_logs'

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, index=True)
    channel_code = db.Column(db.String(32), nullable=False, index=True)
    direction = db.Column(db.String(10), nullable=False)  # inbound / outbound
    message_type = db.Column(db.String(32), nullable=False)  # ari / reservation / ack
    related_job_id = db.Column(db.Integer, db.ForeignKey('channel_sync_jobs.id'))
    http_status = db.Column(db.Integer)
    success = db.Column(db.Boolean, default=False)
    request_body = db.Column(db.Text)
    response_body = db.Column(db.Text)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_json(self):
        return {
            'id': self.id,
            'property_id': self.property_id,
            'channel_code': self.channel_code,
            'direction': self.direction,
            'message_type': self.message_type,
            'related_job_id': self.related_job_id,
            'http_status': self.http_status,
            'success': self.success,
            'request_body': self.request_body,
            'response_body': self.response_body,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class SupportedChannel(db.Model):
    __tablename__ = 'supported_channels'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)  # e.g., 'booking_com'
    name = db.Column(db.String(64), unique=True, nullable=False)  # e.g., 'Booking.com'
    logo = db.Column(db.String(32))  # e.g., '🏨'
    is_active = db.Column(db.Boolean, default=True)

    @staticmethod
    def insert_channels():
        # Mapping: { 'Name': ['code', 'logo'] }
        channels = {
            'Booking.com': ['booking_com', '🏨'],
            'Expedia': ['expedia', '✈️']
        }

        for name, data in channels.items():
            channel = SupportedChannel.query.filter_by(code=data[0]).first()
            if channel is None:
                channel = SupportedChannel(name=name, code=data[0], logo=data[1])
            db.session.add(channel)
        db.session.commit()

    def to_json(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'logo': self.logo,
            'is_active': self.is_active
        }
