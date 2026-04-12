from datetime import datetime, timezone

from app import db
from app.celery_app import celery
from app.api.channel_manager.models import ChannelSyncJob
from app.api.channel_manager.tasks.push_ari import process_ari_push_job
from app.api.channel_manager.tasks.pull_reservations import process_reservation_pull_job
from app.api.channel_manager.tasks.ack_reservations import process_reservation_ack_job
from app.api.channel_manager.tasks.reconcile import process_reconciliation_job


def _dispatch_job(job: ChannelSyncJob):
    if job.status not in ('pending', 'retrying'):
        return

    job.status = 'queued'
    db.session.commit()

    if job.job_type == 'ari_push':
        process_ari_push_job.delay(job.id)
    elif job.job_type == 'reservation_pull':
        process_reservation_pull_job.delay(job.id)
    elif job.job_type == 'reservation_ack':
        process_reservation_ack_job.delay(job.id)
    elif job.job_type == 'reconcile':
        process_reconciliation_job.delay(job.id)
    else:
        job.status = 'failed'
        job.last_error = f'Unsupported job_type: {job.job_type}'
        job.completed_at = datetime.now(timezone.utc)
        db.session.commit()


@celery.task
def dispatch_pending_channel_jobs(limit: int = 100):
    jobs = (
        ChannelSyncJob.query
        .filter(ChannelSyncJob.status.in_(['pending', 'retrying']))
        .order_by(ChannelSyncJob.created_at.asc())
        .limit(limit)
        .all()
    )

    dispatched = 0

    for job in jobs:
        if job.status == 'retrying' and job.next_retry_at:
            if job.next_retry_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
                continue

        _dispatch_job(job)
        dispatched += 1

    return {
        'dispatched': dispatched,
        'scanned': len(jobs),
    }
