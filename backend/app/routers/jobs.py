"""Job lifecycle: create, inspect, follow, cancel, retry, delete."""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from .. import catalog, probe, queue
from ..config import settings
from ..jobstore import JobNotFound, store
from ..schemas import Job, JobList, JobStatus, SeparationOptions, TrackInfo

router = APIRouter(prefix="/jobs", tags=["jobs"])

CHUNK = 1024 * 1024


def _get_job_or_404(job_id: str) -> Job:
    try:
        return store.get(job_id)
    except (JobNotFound, ValueError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trabajo no encontrado") from None


def safe_filename(name: str) -> str:
    """Strip anything that could escape the input directory or confuse Demucs."""
    name = Path(name or "audio").name
    normalized = unicodedata.normalize("NFKD", name)
    cleaned = re.sub(r"[^\w.\- ]+", "_", normalized).strip(" .")
    return cleaned or "audio"


def _parse_options(raw: str | None) -> SeparationOptions:
    if not raw:
        return SeparationOptions()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"'options' no es JSON válido: {exc}"
        ) from exc
    reasons = catalog.unsupported_reasons(payload if isinstance(payload, dict) else {})
    if reasons:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, reasons)
    try:
        return SeparationOptions.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, _validation_detail(exc)
        ) from exc


def _validation_detail(exc: ValidationError) -> list[dict[str, str]]:
    """Pydantic's raw errors carry exception objects; keep only JSON-safe fields."""
    return [
        {
            "field": ".".join(str(part) for part in error["loc"]) or "options",
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors(include_url=False)
    ]


@router.post("", response_model=Job, status_code=status.HTTP_201_CREATED)
async def create_job(
    files: list[UploadFile] = File(..., description="Archivos de audio o video"),
    options: str | None = Form(None, description="JSON con las opciones de separación"),
) -> Job:
    parsed = _parse_options(options)

    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No se recibió ningún archivo.")
    if len(files) > settings.max_files_per_job:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Máximo {settings.max_files_per_job} archivos por trabajo.",
        )

    allowed = {ext.lower() for ext in settings.allowed_extensions}
    job = store.create(parsed)
    input_dir = store.input_dir(job.id)
    tracks: list[TrackInfo] = []

    try:
        for index, upload in enumerate(files):
            name = safe_filename(upload.filename or f"track_{index + 1}")
            suffix = Path(name).suffix.lower()
            if suffix not in allowed:
                raise HTTPException(
                    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    f"Extensión no soportada: {suffix or '(ninguna)'}. "
                    f"Permitidas: {', '.join(sorted(allowed))}",
                )
            # Two files can share a name once sanitized; keep both.
            target = input_dir / name
            counter = 1
            while target.exists():
                target = input_dir / f"{Path(name).stem}_{counter}{suffix}"
                counter += 1

            written = await _stream_to_disk(upload, target)
            tracks.append(
                TrackInfo(
                    name=target.stem,
                    original_filename=upload.filename or name,
                    size_bytes=written,
                    # ffprobe can take seconds per file; on the event loop that
                    # would stall every SSE stream and the health check with it.
                    duration_seconds=await asyncio.to_thread(probe.probe_duration, target),
                )
            )
    except HTTPException:
        store.delete(job.id)
        raise
    except Exception:
        store.delete(job.id)
        raise

    job = store.update(job.id, lambda current: setattr(current, "tracks", tracks))
    queue.submit(job.id)
    return job


async def _stream_to_disk(upload: UploadFile, target: Path) -> int:
    """Write an upload to disk, aborting as soon as it exceeds the size limit."""
    written = 0
    with target.open("wb") as handle:
        while chunk := await upload.read(CHUNK):
            written += len(chunk)
            if written > settings.max_upload_bytes:
                handle.close()
                target.unlink(missing_ok=True)
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    f"'{upload.filename}' supera el límite de {settings.max_upload_mb} MB.",
                )
            await asyncio.to_thread(handle.write, chunk)
    if written == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"'{upload.filename}' está vacío."
        )
    return written


@router.get("", response_model=JobList)
def list_jobs(
    job_status: JobStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> JobList:
    jobs = store.list(job_status)
    return JobList(
        items=jobs[offset : offset + limit],
        total=len(jobs),
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    return _get_job_or_404(job_id)


@router.get("/{job_id}/log")
def get_log(
    job_id: str, tail_bytes: int | None = Query(None, ge=1, le=5_000_000)
) -> dict[str, str]:
    _get_job_or_404(job_id)
    return {"log": store.read_log(job_id, tail_bytes)}


@router.post("/{job_id}/cancel", response_model=Job)
def cancel_job(job_id: str) -> Job:
    job = _get_job_or_404(job_id)
    if job.is_terminal:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"El trabajo ya está en estado '{job.status.value}'."
        )
    store.request_cancel(job_id)
    return _get_job_or_404(job_id)


@router.post("/{job_id}/retry", response_model=Job, status_code=status.HTTP_201_CREATED)
def retry_job(job_id: str) -> Job:
    """Re-run a finished job's inputs, optionally with the same options.

    Creates a new job so the original stays browsable.
    """
    import shutil

    source = _get_job_or_404(job_id)
    if not source.is_terminal:
        raise HTTPException(status.HTTP_409_CONFLICT, "El trabajo todavía está en curso.")

    inputs = sorted(p for p in store.input_dir(job_id).iterdir() if p.is_file())
    if not inputs:
        raise HTTPException(
            status.HTTP_410_GONE, "Los archivos originales ya no están disponibles."
        )

    clone = store.create(source.options)
    for path in inputs:
        shutil.copy2(path, store.input_dir(clone.id) / path.name)
    clone = store.update(clone.id, lambda current: setattr(current, "tracks", source.tracks))
    queue.submit(clone.id)
    return clone


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str) -> None:
    job = _get_job_or_404(job_id)
    if not job.is_terminal:
        store.request_cancel(job_id)
    try:
        store.delete(job_id)
    except JobNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trabajo no encontrado") from None


@router.get("/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    """Server-sent events with the job's state until it reaches a terminal one."""
    _get_job_or_404(job_id)

    async def generator():
        last_payload: str | None = None
        idle_ticks = 0
        while True:
            job = store.try_get(job_id)
            if job is None:
                yield "event: deleted\ndata: {}\n\n"
                return
            payload = job.model_dump_json()
            if payload != last_payload:
                last_payload = payload
                idle_ticks = 0
                yield f"event: job\ndata: {payload}\n\n"
            else:
                idle_ticks += 1
                if idle_ticks % 15 == 0:
                    # Comment frame: keeps proxies from closing an idle stream.
                    yield ": keep-alive\n\n"
            if job.is_terminal:
                yield "event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(1.0)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
