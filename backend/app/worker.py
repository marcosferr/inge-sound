"""Executes a queued job end to end.

Shared verbatim by both queue backends: the thread pool calls ``execute_job``
directly, the Celery task calls it from a worker process.
"""

from __future__ import annotations

import logging
import traceback

from .catalog import model_sub_models
from .config import settings
from .jobstore import JobNotFound, JobStore, utcnow
from .jobstore import store as default_store
from .runner import ProgressUpdate, build_argv, collect_stems, run_demucs
from .schemas import Job, JobProgress, JobStatus

log = logging.getLogger(__name__)


def execute_job(job_id: str, store: JobStore | None = None) -> Job:
    """Run the separation for ``job_id`` and record the outcome.

    Never raises for a failed separation: the failure is written to the job so
    the UI can show it. Only a missing job propagates.
    """
    store = store or default_store
    job = store.get(job_id)

    if store.cancel_requested(job_id):
        return _finish(
            store, job_id, JobStatus.cancelled, error="Cancelado antes de empezar."
        )

    inputs = sorted(p for p in store.input_dir(job_id).iterdir() if p.is_file())
    if not inputs:
        return _finish(
            store, job_id, JobStatus.failed, error="El trabajo no tiene archivos de entrada."
        )

    output_dir = store.output_dir(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    argv = build_argv(job.options, inputs, output_dir)

    def mark_running(current: Job) -> None:
        current.status = JobStatus.running
        current.started_at = utcnow()
        current.command = argv
        current.progress = JobProgress(
            percent=0.0, stage="starting", tracks_total=len(inputs)
        )

    store.update(job_id, mark_running)
    store.append_log(job_id, f"$ {' '.join(argv)}\n\n")

    def on_progress(update: ProgressUpdate) -> None:
        store.update(
            job_id,
            lambda current: setattr(
                current, "progress", JobProgress(**update.__dict__)
            ),
        )

    def on_start(pid: int) -> None:
        store.update(job_id, lambda current: setattr(current, "pid", pid))

    try:
        code = run_demucs(
            argv,
            tracks_total=len(inputs),
            sub_models=model_sub_models(job.options.effective_model),
            on_progress=on_progress,
            on_log=lambda text: store.append_log(job_id, text + "\n"),
            on_start=on_start,
            should_cancel=lambda: store.cancel_requested(job_id),
            timeout=settings.job_timeout_seconds or None,
        )
    except TimeoutError as exc:
        store.append_log(job_id, f"\n[timeout] {exc}\n")
        return _finish(store, job_id, JobStatus.failed, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
        log.exception("Job %s crashed", job_id)
        store.append_log(job_id, "\n" + traceback.format_exc())
        return _finish(store, job_id, JobStatus.failed, error=f"Error inesperado: {exc}")

    if store.cancel_requested(job_id):
        store.clear_cancel(job_id)
        return _finish(
            store, job_id, JobStatus.cancelled, error="Cancelado por el usuario."
        )

    if code != 0:
        tail = store.read_log(job_id, tail_bytes=4000).strip().splitlines()
        detail = tail[-1] if tail else ""
        return _finish(
            store,
            job_id,
            JobStatus.failed,
            error=f"Demucs terminó con código {code}. {detail}".strip(),
        )

    stems = collect_stems(output_dir, job.options)
    if not stems:
        return _finish(
            store,
            job_id,
            JobStatus.failed,
            error="Demucs terminó sin errores pero no generó pistas de salida.",
        )

    def mark_done(current: Job) -> None:
        current.status = JobStatus.completed
        current.stems = stems
        current.finished_at = utcnow()
        current.pid = None
        current.progress = JobProgress(
            percent=100.0,
            stage="finished",
            tracks_done=len(current.tracks) or current.progress.tracks_total,
            tracks_total=current.progress.tracks_total,
        )

    return store.update(job_id, mark_done)


def _finish(store: JobStore, job_id: str, status: JobStatus, error: str | None = None) -> Job:
    def mutate(current: Job) -> None:
        current.status = status
        current.error = error
        current.finished_at = utcnow()
        current.pid = None
        if status is JobStatus.completed:
            current.progress.percent = 100.0
        current.progress.stage = status.value

    try:
        return store.update(job_id, mutate)
    except JobNotFound:  # pragma: no cover - job deleted mid-run
        raise
