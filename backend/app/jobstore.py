"""Filesystem-backed job store.

One directory per job keeps the API process and the worker (thread or Celery, in
this container or another) in sync without a database:

``<data>/jobs/<id>/job.json``   the serialized :class:`~app.schemas.Job`
``<data>/jobs/<id>/input/``     the uploaded files
``<data>/jobs/<id>/output/``    whatever Demucs wrote
``<data>/jobs/<id>/job.log``    merged stdout/stderr of the Demucs process
``<data>/jobs/<id>/cancel``     a marker the worker polls
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from filelock import FileLock, Timeout

from .config import settings
from .schemas import Job, JobStatus, SeparationOptions

LOCK_TIMEOUT = 15.0


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_job_id() -> str:
    return uuid.uuid4().hex


class JobNotFound(LookupError):
    pass


class JobStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.jobs_dir
        self.root.mkdir(parents=True, exist_ok=True)

    # --- paths -------------------------------------------------------------

    def job_dir(self, job_id: str) -> Path:
        safe = _safe_id(job_id)
        return self.root / safe

    def input_dir(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "input"

    def output_dir(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "output"

    def log_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.log"

    def cancel_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "cancel"

    def _json_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def _lock(self, job_id: str) -> FileLock:
        return FileLock(str(self.job_dir(job_id) / "job.lock"), timeout=LOCK_TIMEOUT)

    # --- crud --------------------------------------------------------------

    def create(self, options: SeparationOptions) -> Job:
        job_id = new_job_id()
        created = utcnow()
        job = Job(
            id=job_id,
            options=options,
            created_at=created,
            expires_at=created + timedelta(hours=settings.retention_hours),
        )
        for directory in (self.input_dir(job_id), self.output_dir(job_id)):
            directory.mkdir(parents=True, exist_ok=True)
        self._write(job)
        return job

    def get(self, job_id: str) -> Job:
        path = self._json_path(job_id)
        if not path.exists():
            raise JobNotFound(job_id)
        return Job.model_validate_json(path.read_text(encoding="utf-8"))

    def try_get(self, job_id: str) -> Job | None:
        try:
            return self.get(job_id)
        except (JobNotFound, ValueError):
            return None

    def save(self, job: Job) -> Job:
        self._write(job)
        return job

    def update(self, job_id: str, mutate: Callable[[Job], None]) -> Job:
        """Read-modify-write a job under an inter-process lock.

        The worker writes progress while the API may be cancelling, so every
        partial update goes through here rather than through ``save``.
        """
        try:
            with self._lock(job_id):
                job = self.get(job_id)
                mutate(job)
                self._write(job)
                return job
        except Timeout:  # pragma: no cover - only under pathological contention
            job = self.get(job_id)
            mutate(job)
            self._write(job)
            return job

    def delete(self, job_id: str) -> None:
        import shutil

        directory = self.job_dir(job_id)
        if not directory.exists():
            raise JobNotFound(job_id)
        shutil.rmtree(directory, ignore_errors=True)

    def list(self, status: JobStatus | None = None) -> list[Job]:
        jobs = [job for job in self.iter_jobs() if status is None or job.status == status]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs

    def iter_jobs(self) -> Iterator[Job]:
        if not self.root.exists():
            return
        for directory in self.root.iterdir():
            if not directory.is_dir():
                continue
            job = self.try_get(directory.name)
            if job is not None:
                yield job

    # --- cancellation ------------------------------------------------------

    def request_cancel(self, job_id: str) -> None:
        self.cancel_path(job_id).write_text(utcnow().isoformat(), encoding="utf-8")

    def cancel_requested(self, job_id: str) -> bool:
        return self.cancel_path(job_id).exists()

    def clear_cancel(self, job_id: str) -> None:
        self.cancel_path(job_id).unlink(missing_ok=True)

    # --- logging -----------------------------------------------------------

    def append_log(self, job_id: str, text: str) -> None:
        with self.log_path(job_id).open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(text)

    def read_log(self, job_id: str, tail_bytes: int | None = None) -> str:
        path = self.log_path(job_id)
        if not path.exists():
            return ""
        if tail_bytes is None:
            return path.read_text(encoding="utf-8", errors="replace")
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - tail_bytes))
            return handle.read().decode("utf-8", errors="replace")

    # --- maintenance -------------------------------------------------------

    def purge_expired(self, now: datetime | None = None) -> list[str]:
        """Delete jobs past their retention window. Returns the deleted ids."""
        now = now or utcnow()
        removed: list[str] = []
        for job in list(self.iter_jobs()):
            if job.expires_at and job.expires_at <= now:
                try:
                    self.delete(job.id)
                    removed.append(job.id)
                except JobNotFound:  # pragma: no cover - concurrent purge
                    pass
        return removed

    # --- internals ---------------------------------------------------------

    def _write(self, job: Job) -> None:
        directory = self.job_dir(job.id)
        directory.mkdir(parents=True, exist_ok=True)
        payload = job.model_dump(mode="json")
        # Atomic replace so a reader never sees a half-written document.
        fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, self._json_path(job.id))


def _safe_id(job_id: str) -> str:
    if not job_id or not all(c.isalnum() or c in "-_" for c in job_id):
        raise JobNotFound(job_id)
    return job_id


store = JobStore()
