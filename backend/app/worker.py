import subprocess

from celery import Celery

from app.config import get_settings

settings = get_settings()
celery_app = Celery(
    "suni",
    broker=settings.redis_url.get_secret_value(),
    backend=settings.redis_url.get_secret_value(),
)
celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    task_track_started=True,
    task_time_limit=60,
    task_soft_time_limit=50,
    result_expires=300,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_default_queue="suni",
    imports=("app.media_tasks",),
    broker_connection_timeout=2,
    broker_transport_options={
        "visibility_timeout": 1800,
        "socket_timeout": 2,
        "socket_connect_timeout": 2,
        "max_retries": 0,
    },
    beat_schedule={"media-maintenance": {"task": "suni.media_maintenance", "schedule": 30.0}},
)


@celery_app.task(name="suni.probe")
def worker_probe():
    """Internal integration probe; never exposed as a public API endpoint."""
    result = subprocess.run(
        ["ffmpeg", "-version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {"status": "ok", "ffmpeg": result.stdout.splitlines()[0]}
