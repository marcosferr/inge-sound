"""FastAPI application factory and lifecycle."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import queue
from .config import settings
from .jobstore import store
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
    _requeue_orphans()
    try:
        yield
    finally:
        if janitor:
            janitor.cancel()
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


def _requeue_orphans() -> None:
    """Mark jobs left 'running' by a crash, so the UI doesn't wait forever."""
    from .schemas import Job, JobStatus

    for job in store.iter_jobs():
        if job.status is JobStatus.running:
            def mutate(current: Job) -> None:
                current.status = JobStatus.failed
                current.error = "El servidor se reinició mientras el trabajo corría."
                current.pid = None

            try:
                store.update(job.id, mutate)
                log.warning("Trabajo %s marcado como fallido tras reinicio", job.id)
            except Exception:  # noqa: BLE001
                log.exception("No se pudo reconciliar el trabajo %s", job.id)


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
