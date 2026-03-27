from datetime import datetime, timezone

from celery import shared_task

from app import db
from app.api.channel_manager.models import (
    ChannelConnection,
    ChannelMessageLog,
    ChannelSyncJob,
)
from app.api.channel_manager.adapters import get_adapter
from app.api.channel_manager.services.ari_service import ARIService


@shared_task
def process_ari_push_job(job_id: int):
    job = ChannelSyncJob.query.get(job_id)
    if not job or job.status not in ("pending", "retrying"):
        return

    connection = ChannelConnection.query.filter_by(
        property_id=job.property_id,
        channel_code=job.channel_code,
        status="active",
    ).first()

    if not connection:
        job.status = "failed"
        job.last_error = "No active channel connection"
        db.session.commit()
        return

    adapter = get_adapter(job.channel_code)

    try:
        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1
        db.session.commit()

        room_ids = job.payload_json["room_ids"]
        dates = [datetime.fromisoformat(x).date() for x in job.payload_json["dates"]]

        updates = ARIService.build_updates_for_room_dates(
            property_id=job.property_id,
            room_ids=room_ids,
            dates=dates,
        )

        result = adapter.push_ari(connection, updates)

        log = ChannelMessageLog(
            property_id=job.property_id,
            channel_code=job.channel_code,
            direction="outbound",
            message_type="ari",
            related_job_id=job.id,
            http_status=result.get("http_status"),
            success=result.get("success", False),
            request_body=result.get("request_body"),
            response_body=result.get("response_body"),
        )
        db.session.add(log)

        job.status = "success"
        job.completed_at = datetime.now(timezone.utc)
        db.session.commit()

    except Exception as exc:
        log = ChannelMessageLog(
            property_id=job.property_id,
            channel_code=job.channel_code,
            direction="outbound",
            message_type="ari",
            related_job_id=job.id,
            success=False,
            error_message=str(exc),
        )
        db.session.add(log)

        job.status = "retrying" if job.attempts < job.max_attempts else "failed"
        job.last_error = str(exc)
        db.session.commit()
        raise