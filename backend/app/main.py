"""FastAPI application factory and lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import queue
from .config import settings
from .jobstore import store, utcnow
from .routers import capabilities, files, jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("inge_sound")

DESCRIPTION = """
API de separación de pistas basada en **Demucs** (Meta AI).

Expone todas las opciones del CLI de Demucs. `GET /api/capabilities` describe los
modelos y las opciones disponibles en este servidor: es la fuente de verdad para
construir un cliente.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Data dir: %s | queue: %s", settings.data_dir, settings.queue_backend)
    janitor = None
    if settings.cleanup_interval_minutes > 0:
        janitor = asyncio.create_task(_janitor())
    reconcile_orphans()
    try:
        yield
    finally:
        if janitor:
            janitor.cancel()
        terminate_running_jobs()
        queue.shutdown()


async def _janitor() -> None:
    """Delete jobs past their retention window, forever."""
    interval = settings.cleanup_interval_minutes * 60
    while True:
        try:
            removed = await asyncio.to_thread(store.purge_expired)
            if removed:
                log.info("Retención: %d trabajos eliminados", len(removed))
        except Exception:  # noqa: BLE001 - the janitor must never die
            log.exception("Fallo al limpiar trabajos vencidos")
        await asyncio.sleep(interval)


def terminate_running_jobs() -> int:
    """Stop the Demucs processes this server started, on the way down.

    ``start_new_session=True`` (needed to group-kill on cancel) also means the
    children survive uvicorn exiting, so outside a container they would keep
    burning cores or GPU with nothing tracking them. Only the in-process pool's
    children are ours to kill; Celery workers own theirs.
    """
    from .schemas import Job, JobStatus

    if settings.queue_backend != "thread":
        return 0

    stopped = 0
    for job in store.iter_jobs():
        if job.status is not JobStatus.running or not job.pid:
            continue
        try:
            os.killpg(os.getpgid(job.pid), signal.SIGTERM)
            stopped += 1
            log.info("Demucs del trabajo %s detenido (pid %s)", job.id, job.pid)
        except (ProcessLookupError, PermissionError, OSError):
            continue  # already gone, or not ours any more

        def mutate(current: Job) -> None:
            current.pid = None

        with contextlib.suppress(Exception):
            store.update(job.id, mutate)
    return stopped


def reconcile_orphans() -> int:
    """Fail jobs whose worker died, so the UI does not wait forever.

    Only safe with the in-process pool: there, a restart really did kill every
    separation. With Celery the workers outlive the API, so a restart would
    wrongly fail runs that are still going — those reconcile themselves when the
    worker writes its result. Returns how many jobs were marked failed.
    """
    from .schemas import Job, JobStatus

    if settings.queue_backend != "thread":
        return 0

    reconciled = 0
    for job in store.iter_jobs():
        if job.status is not JobStatus.running:
            continue

        def mutate(current: Job) -> None:
            current.status = JobStatus.failed
            current.error = "El servidor se reinició mientras el trabajo corría."
            current.pid = None
            current.finished_at = utcnow()
            current.progress.stage = "failed"

        try:
            store.update(job.id, mutate)
            reconciled += 1
            log.warning("Trabajo %s marcado como fallido tras reinicio", job.id)
        except Exception:  # noqa: BLE001 - one bad job must not block startup
            log.exception("No se pudo reconciliar el trabajo %s", job.id)
    return reconciled


def create_app() -> FastAPI:
    app = FastAPI(
        title="Inge Sound",
        description=DESCRIPTION,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "Content-Range", "Accept-Ranges"],
    )
    app.include_router(capabilities.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(files.router, prefix="/api")
    return app


app = create_app()
