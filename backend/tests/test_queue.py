"""Dispatch tests: the same job runs through either backend."""

from __future__ import annotations

from app import queue
from app.schemas import SeparationOptions


def test_thread_backend_runs_the_job(store, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "queue_backend", "thread")
    job = store.create(SeparationOptions())

    ran: list[str] = []
    monkeypatch.setattr(queue, "execute_job", ran.append)

    queue.submit(job.id)
    queue.shutdown()

    # shutdown() waits for nothing, so give the pool a moment to pick it up.
    import time

    for _ in range(50):
        if ran:
            break
        time.sleep(0.02)
    assert ran == [job.id]


def test_celery_backend_enqueues_instead_of_running(store, monkeypatch):
    """With Celery configured, the API must not block on the separation."""
    import sys
    import types

    from app.config import settings

    monkeypatch.setattr(settings, "queue_backend", "celery")

    enqueued: list[str] = []
    fake_module = types.ModuleType("app.celery_app")
    fake_module.separate_task = types.SimpleNamespace(delay=enqueued.append)
    monkeypatch.setitem(sys.modules, "app.celery_app", fake_module)

    job = store.create(SeparationOptions())
    queue.submit(job.id)

    assert enqueued == [job.id]
