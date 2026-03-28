from datetime import datetime, timezone, timedelta
from app.celery_app import celery

from app import db
from app.api.channel_manager.models import ChannelConnection, ChannelMessageLog, ChannelSyncJob
from app.api.channel_manager.adapters import get_adapter
from app.api.channel_manager.services.reservation_import_service import ReservationImportService


@celery.task
def process_reservation_pull_job(job_id: int):
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

        result = adapter.pull_reservations(
            connection=connection,
            cursor=job.payload_json.get('cursor')
        )

        for reservation in result.get('reservations', []):
            ReservationImportService.import_one(connection, reservation)

        log = ChannelMessageLog(
            property_id=job.property_id,
            channel_code=job.channel_code,
            direction='inbound',
            message_type='reservation',
            related_job_id=job.id,
            http_status=result.get('http_status'),
            success=True,
            response_body=result.get('raw_body'),
        )
        db.session.add(log)

        connection.last_success_at = datetime.now(timezone.utc)
        job.status = 'success'
        job.completed_at = datetime.now(timezone.utc)
        db.session.commit()


    except Exception as exc:

        log = ChannelMessageLog(

            property_id=job.property_id,

            channel_code=job.channel_code,

            direction='inbound',

            message_type='reservation',

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