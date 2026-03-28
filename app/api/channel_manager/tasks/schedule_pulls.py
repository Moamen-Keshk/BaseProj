from app import db
from app.celery_app import celery
from app.api.channel_manager.models import ChannelConnection, ChannelSyncJob


@celery.task
def schedule_reservation_pull_jobs():
    active_connections = ChannelConnection.query.filter_by(
        status='active',
        polling_enabled=True
    ).all()

    created = 0

    for connection in active_connections:
        existing_pending = ChannelSyncJob.query.filter(
            ChannelSyncJob.property_id == connection.property_id,
            ChannelSyncJob.channel_code == connection.channel_code,
            ChannelSyncJob.job_type == 'reservation_pull',
            ChannelSyncJob.status.in_(['pending', 'queued', 'processing', 'retrying'])
        ).first()

        if existing_pending:
            continue

        job = ChannelSyncJob(
            property_id=connection.property_id,
            channel_code=connection.channel_code,
            job_type='reservation_pull',
            payload_json={},
            status='pending',
        )
        db.session.add(job)
        created += 1

    db.session.commit()
    return {'created': created}