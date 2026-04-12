from datetime import datetime, timezone, timedelta

from app import db
from app.celery_app import celery
from app.api.channel_manager.adapters import get_adapter
from app.api.channel_manager.models import ChannelConnection, ChannelMessageLog, ChannelSyncJob
from app.api.channel_manager.services.reconciliation_service import ReconciliationService
from app.api.utils.notifications import notify_channel_sync_issue


@celery.task
def process_reconciliation_job(job_id: int):
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

        result = adapter.pull_reservations(
            connection=connection,
            cursor=job.payload_json.get('cursor')
        )

        reconciliation_summary = ReconciliationService.reconcile_reservations(
            connection=connection,
            reservations=result.get('reservations', []),
            snapshot_complete=bool(job.payload_json.get('snapshot_complete', True)),
            queue_acknowledgements=bool(job.payload_json.get('queue_acknowledgements', False)),
            mark_missing_as_cancelled=bool(job.payload_json.get('mark_missing_as_cancelled', False)),
        )

        log = ChannelMessageLog(
            property_id=job.property_id,
            channel_code=job.channel_code,
            direction='inbound',
            message_type='reconcile',
            related_job_id=job.id,
            http_status=result.get('http_status'),
            success=True,
            response_body=str(reconciliation_summary),
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
            message_type='reconcile',
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
