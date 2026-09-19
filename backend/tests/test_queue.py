"""Dispatch tests: the same job runs through either backend."""

from __future__ import annotations

from app import queue
from app.schemas import SeparationOptions


def test_thread_backend_runs_the_job(store, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "queue_backend", "thread")
    job = store.create(SeparationOptions())

    import threading

    ran: list[str] = []
    done = threading.Event()

    def record(job_id: str) -> None:
        ran.append(job_id)
        done.set()

    monkeypatch.setattr(queue, "execute_job", record)

    queue.submit(job.id)
    try:
        # shutdown() cancels pending futures, so wait for the run before it.
        assert done.wait(timeout=10), "el pool nunca ejecutó el trabajo"
    finally:
        queue.shutdown()
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
