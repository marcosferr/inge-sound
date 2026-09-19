"""Celery entrypoint, used when ``INGE_QUEUE_BACKEND=celery``.

Start a worker with::

    celery -A app.celery_app.celery worker --loglevel=info --concurrency=1
"""

from __future__ import annotations

from celery import Celery

from .config import settings
from .worker import execute_job

celery = Celery(
    "inge_sound",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=(settings.job_timeout_seconds or 0) + 300 or None,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)


@celery.task(name="inge_sound.separate")
def separate_task(job_id: str) -> str:
    """Run one separation. Progress and errors go through the job store."""
    job = execute_job(job_id)
    return job.status.value
