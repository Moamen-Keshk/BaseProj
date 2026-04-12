from app.celery_app import celery

from app.api.channel_manager.models import ChannelSyncJob
from app.api.channel_manager.tasks.push_ari import process_ari_push_job
from app.api.channel_manager.tasks.pull_reservations import process_reservation_pull_job
from app.api.channel_manager.tasks.reconcile import process_reconciliation_job


@celery.task
def retry_channel_job(job_id: int):
    job = ChannelSyncJob.query.get(job_id)
    if not job:
        return

    if job.job_type == 'ari_push':
        process_ari_push_job.delay(job.id)
    elif job.job_type == 'reservation_pull':
        process_reservation_pull_job.delay(job.id)
    elif job.job_type == 'reconcile':
        process_reconciliation_job.delay(job.id)
