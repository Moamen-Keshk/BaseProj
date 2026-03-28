import os
from dotenv import load_dotenv
from celery import Celery, Task

from app import create_app

basedir = os.path.abspath(os.path.dirname(__file__))
dotenv_path = os.path.join(basedir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


def make_celery() -> Celery:
    config_name = os.getenv("FLASK_CONFIG") or "default"
    flask_app = create_app(config_name)

    class FlaskTask(Task):
        abstract = True

        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return super().__call__(*args, **kwargs)

    celery_app = Celery(
        flask_app.import_name,
        broker=flask_app.config.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        backend=flask_app.config.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
        task_cls=FlaskTask,
    )

    celery_app.conf.update(
        broker_url=flask_app.config.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        result_backend=flask_app.config.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        beat_schedule={
            "dispatch-channel-jobs-every-30-seconds": {
                "task": "app.api.channel_manager.tasks.dispatch_jobs.dispatch_pending_channel_jobs",
                "schedule": 30.0,
            },
            "schedule-reservation-pulls-every-60-seconds": {
                "task": "app.api.channel_manager.tasks.schedule_pulls.schedule_reservation_pull_jobs",
                "schedule": 60.0,
            },
        },
        imports=(
            "app.api.channel_manager.tasks.push_ari",
            "app.api.channel_manager.tasks.pull_reservations",
            "app.api.channel_manager.tasks.ack_reservations",
            "app.api.channel_manager.tasks.dispatch_jobs",
            "app.api.channel_manager.tasks.schedule_pulls",
            "app.api.channel_manager.tasks.retry_jobs",
        ),
    )

    return celery_app


celery = make_celery()