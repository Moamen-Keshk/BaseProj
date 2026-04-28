from datetime import datetime, timezone, timedelta
from app.celery_app import celery

from app import db
from app.api.channel_manager.models import ChannelConnection, ChannelMessageLog, ChannelSyncJob
from app.api.channel_manager.adapters import get_adapter
from app.api.channel_manager.services.ari_service import ARIService
from app.api.utils.notifications import notify_channel_sync_issue


@celery.task
def process_ari_push_job(job_id: int):
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
        notify_channel_sync_issue(job, job.last_error)
        db.session.commit()
        return

    adapter = get_adapter(job.channel_code)

    try:
        job.status = 'processing'
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1
        db.session.commit()

        room_ids = job.payload_json.get('room_ids', [])
        dates = [datetime.fromisoformat(x).date() for x in job.payload_json.get('dates', [])]

        updates = ARIService.build_updates_for_room_dates(
            property_id=job.property_id,
            room_ids=room_ids,
            dates=dates,
            channel_code=job.channel_code,
        )

        result = adapter.push_ari(connection, updates)

        log = ChannelMessageLog(
            property_id=job.property_id,
            channel_code=job.channel_code,
            direction='outbound',
            message_type='ari',
            related_job_id=job.id,
            http_status=result.get('http_status'),
            success=result.get('success', False),
            request_body=result.get('request_body'),
            response_body=result.get('response_body'),
        )
        db.session.add(log)

        if result.get('success'):
            connection.last_success_at = datetime.now(timezone.utc)
        else:
            connection.last_error_at = datetime.now(timezone.utc)

        job.status = 'success' if result.get('success') else 'failed'
        if job.status == 'failed':
            job.last_error = result.get('response_body') or 'ARI push failed'
            notify_channel_sync_issue(job, job.last_error)
        job.completed_at = datetime.now(timezone.utc)
        db.session.commit()


    except Exception as exc:

        log = ChannelMessageLog(

            property_id=job.property_id,

            channel_code=job.channel_code,

            direction='outbound',

            message_type='ari',

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
        if job.status == 'failed':
            notify_channel_sync_issue(job, job.last_error)

        db.session.commit()

        raise
