"""Job dispatch. Two interchangeable backends behind one ``submit`` call."""

from __future__ import annotations

import atexit
import logging
from concurrent.futures import ThreadPoolExecutor

from .config import settings
from .worker import execute_job

log = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None


def _thread_pool() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=max(1, settings.worker_concurrency),
            thread_name_prefix="separation",
        )
        atexit.register(lambda: _executor and _executor.shutdown(wait=False))
    return _executor


def submit(job_id: str) -> None:
    """Hand ``job_id`` to whichever backend is configured."""
    if settings.queue_backend == "celery":
        from .celery_app import separate_task

        separate_task.delay(job_id)
        return

    future = _thread_pool().submit(execute_job, job_id)
    future.add_done_callback(_log_failure)


def _log_failure(future) -> None:
    exc = future.exception()
    if exc is not None:  # pragma: no cover - execute_job records its own errors
        log.error("Separation task failed: %s", exc, exc_info=exc)


def shutdown() -> None:
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None
