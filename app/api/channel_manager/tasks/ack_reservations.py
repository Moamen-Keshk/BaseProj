from datetime import datetime, timezone, timedelta

from app import db
from app.celery_app import celery
from app.api.channel_manager.models import ChannelConnection, ChannelMessageLog, ChannelSyncJob
from app.api.channel_manager.adapters import get_adapter


@celery.task
def process_reservation_ack_job(job_id: int):
    job = ChannelSyncJob.query.get(job_id)
    if not job or job.status not in ('pending', 'retrying', 'queued'):
        return

    connection = ChannelConnection.query.filter_by(
        property_id=job.property_id,
        channel_code=job.channel_code,
        status='active'
    ).first()

    if not connection:
        job.status = 'failed'
        job.last_error = 'No active channel connection'
        db.session.commit()
        return

    adapter = get_adapter(job.channel_code)

    try:
        job.status = 'processing'
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1
        db.session.commit()

        result = adapter.acknowledge_reservation(
            connection=connection,
            external_reservation_id=job.payload_json['external_reservation_id'],
            payload=job.payload_json.get('payload'),
        )

        log = ChannelMessageLog(
            property_id=job.property_id,
            channel_code=job.channel_code,
            direction='outbound',
            message_type='ack',
            related_job_id=job.id,
            http_status=result.get('http_status'),
            success=result.get('success', False),
            response_body=result.get('response_body'),
        )
        db.session.add(log)

        if result.get('success'):
            connection.last_success_at = datetime.now(timezone.utc)
            job.status = 'success'
        else:
            connection.last_error_at = datetime.now(timezone.utc)
            job.status = 'failed'
            job.last_error = result.get('response_body') or 'Reservation acknowledgement failed'

        job.completed_at = datetime.now(timezone.utc)
        db.session.commit()

    except Exception as exc:
        log = ChannelMessageLog(
            property_id=job.property_id,
            channel_code=job.channel_code,
            direction='outbound',
            message_type='ack',
            related_job_id=job.id,
            success=False,
            error_message=str(exc),
        )
        db.session.add(log)

        connection.last_error_at = datetime.now(timezone.utc)

        if job.attempts < job.max_attempts:
            backoff_minutes = min(60, 2 ** max(0, job.attempts - 1))
            job.status = 'retrying'
            job.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)
        else:
            job.status = 'failed'

        job.last_error = str(exc)
        db.session.commit()
        raise