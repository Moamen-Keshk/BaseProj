from app import db
from app.api.channel_manager.models import ChannelConnection, ChannelSyncJob


class SyncDispatcher:
    @staticmethod
    def queue_ari_push(property_id: int, room_ids: list[int], dates: list, reason: str):
        active_connections = ChannelConnection.query.filter_by(
            property_id=property_id,
            status='active'
        ).all()

        for connection in active_connections:
            job = ChannelSyncJob(
                property_id=property_id,
                channel_code=connection.channel_code,
                job_type='ari_push',
                payload_json={
                    'room_ids': room_ids,
                    'dates': [d.isoformat() for d in dates],
                    'reason': reason,
                },
                status='pending',
            )
            db.session.add(job)

        db.session.commit()

    @staticmethod
    def queue_reservation_pull(property_id: int, channel_code: str, cursor: dict | None = None):
        job = ChannelSyncJob(
            property_id=property_id,
            channel_code=channel_code,
            job_type='reservation_pull',
            payload_json={'cursor': cursor or {}},
            status='pending',
        )
        db.session.add(job)
        db.session.commit()

    @staticmethod
    def queue_reservation_ack(property_id: int, channel_code: str, external_reservation_id: str, payload: dict | None = None):
        job = ChannelSyncJob(
            property_id=property_id,
            channel_code=channel_code,
            job_type='reservation_ack',
            payload_json={
                'external_reservation_id': external_reservation_id,
                'payload': payload or {},
            },
            status='pending',
        )
        db.session.add(job)
        db.session.commit()