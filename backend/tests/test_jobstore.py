from __future__ import annotations

from datetime import timedelta

import pytest

from app.jobstore import JobNotFound, utcnow
from app.schemas import JobStatus, SeparationOptions


def test_create_lays_out_the_job_directory(store):
    job = store.create(SeparationOptions())
    assert store.input_dir(job.id).is_dir()
    assert store.output_dir(job.id).is_dir()
    assert store.get(job.id).id == job.id


def test_update_is_read_modify_write(store):
    job = store.create(SeparationOptions())
    store.update(job.id, lambda current: setattr(current, "status", JobStatus.running))
    store.update(job.id, lambda current: setattr(current, "error", "boom"))
    reloaded = store.get(job.id)
    assert reloaded.status is JobStatus.running and reloaded.error == "boom"


def test_missing_and_malformed_ids_raise(store):
    with pytest.raises(JobNotFound):
        store.get("no-existe")
    with pytest.raises(JobNotFound):
        store.get("../etc/passwd")
    assert store.try_get("no-existe") is None


def test_cancel_marker_roundtrip(store):
    job = store.create(SeparationOptions())
    assert not store.cancel_requested(job.id)
    store.request_cancel(job.id)
    assert store.cancel_requested(job.id)
    store.clear_cancel(job.id)
    assert not store.cancel_requested(job.id)


def test_purge_expired_only_removes_stale_jobs(store):
    fresh = store.create(SeparationOptions())
    stale = store.create(SeparationOptions())
    store.update(
        stale.id, lambda job: setattr(job, "expires_at", utcnow() - timedelta(hours=1))
    )

    removed = store.purge_expired()

    assert removed == [stale.id]
    assert store.try_get(fresh.id) is not None
    assert store.try_get(stale.id) is None


def test_listing_is_newest_first_and_filterable(store):
    older = store.create(SeparationOptions())
    newer = store.create(SeparationOptions())
    store.update(newer.id, lambda job: setattr(job, "created_at", utcnow()))
    store.update(older.id, lambda job: setattr(job, "created_at", utcnow() - timedelta(minutes=5)))
    store.update(older.id, lambda job: setattr(job, "status", JobStatus.completed))

    assert [job.id for job in store.list()] == [newer.id, older.id]
    assert [job.id for job in store.list(JobStatus.completed)] == [older.id]


def test_log_append_and_tail(store):
    job = store.create(SeparationOptions())
    assert store.read_log(job.id) == ""
    store.append_log(job.id, "hola\n")
    store.append_log(job.id, "mundo\n")
    assert store.read_log(job.id) == "hola\nmundo\n"
    assert store.read_log(job.id, tail_bytes=6) == "mundo\n"
