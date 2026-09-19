"""Serving the separated audio: streaming for the player, ZIP for downloads."""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from ..jobstore import JobNotFound, store
from ..schemas import Job, JobStatus, StemFile

router = APIRouter(prefix="/jobs", tags=["files"])

CHUNK = 256 * 1024
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")

MEDIA_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
}


def _job(job_id: str) -> Job:
    try:
        return store.get(job_id)
    except (JobNotFound, ValueError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trabajo no encontrado") from None


def _stem_path(job: Job, stem_id: str) -> tuple[StemFile, Path]:
    stem = next((s for s in job.stems if s.id == stem_id), None)
    if stem is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pista no encontrada")
    output_dir = store.output_dir(job.id).resolve()
    path = (output_dir / stem.rel_path).resolve()
    # rel_path comes from our own walk of output_dir, but re-check before opening.
    if not path.is_file() or output_dir not in path.parents:
        raise HTTPException(status.HTTP_410_GONE, "El archivo de la pista ya no existe")
    return stem, path


@router.get("/{job_id}/stems/{stem_id}")
def stream_stem(job_id: str, stem_id: str, request: Request) -> Response:
    """Serve a stem with byte-range support, as the audio player needs."""
    stem, path = _stem_path(_job(job_id), stem_id)
    return _ranged_file_response(
        path,
        media_type=MEDIA_TYPES.get(stem.format, "application/octet-stream"),
        range_header=request.headers.get("range"),
    )


@router.get("/{job_id}/stems/{stem_id}/download")
def download_stem(job_id: str, stem_id: str) -> Response:
    job = _job(job_id)
    stem, path = _stem_path(job, stem_id)
    prefix = f"{stem.track}-" if stem.track else ""
    filename = f"{prefix}{stem.filename}"
    return _ranged_file_response(
        path,
        media_type=MEDIA_TYPES.get(stem.format, "application/octet-stream"),
        range_header=None,
        attachment_name=filename,
    )


@router.get("/{job_id}/download")
def download_zip(job_id: str) -> StreamingResponse:
    """Stream every stem of a completed job as one ZIP, built on the fly."""
    job = _job(job_id)
    if job.status is not JobStatus.completed or not job.stems:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El trabajo no tiene pistas listas para descargar."
        )

    output_dir = store.output_dir(job.id)
    label = job.tracks[0].name if len(job.tracks) == 1 else f"inge-sound-{job.id[:8]}"
    archive_name = f"{label}-{job.options.effective_model}.zip"

    def generate() -> Iterator[bytes]:
        buffer = _StreamBuffer()
        # ZIP_STORED: the payload is already compressed audio, and deflating it
        # would burn CPU for nothing.
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
            for stem in job.stems:
                path = output_dir / stem.rel_path
                if not path.is_file():
                    continue
                with archive.open(stem.rel_path, "w") as entry, path.open("rb") as source:
                    while chunk := source.read(CHUNK):
                        entry.write(chunk)
                        yield from buffer.drain()
                yield from buffer.drain()
        yield from buffer.drain()

    return StreamingResponse(
        generate(),
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(archive_name)},
    )


class _StreamBuffer(io.RawIOBase):
    """A write-only file object that hands its bytes back to the generator."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = []

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:  # type: ignore[override]
        payload = bytes(data)
        self._chunks.append(payload)
        return len(payload)

    def drain(self) -> Iterator[bytes]:
        chunks, self._chunks = self._chunks, []
        yield from chunks


def _ranged_file_response(
    path: Path,
    media_type: str,
    range_header: str | None,
    attachment_name: str | None = None,
) -> Response:
    size = path.stat().st_size
    start, end = 0, size - 1
    partial = False

    if range_header:
        match = RANGE_RE.fullmatch(range_header.strip())
        # "bytes=-" names no range at all; serve the whole body with a 200.
        if match and (match.group(1) or match.group(2)):
            raw_start, raw_end = match.groups()
            if raw_start:
                start = int(raw_start)
                if raw_end:
                    end = min(int(raw_end), size - 1)
            elif raw_end:
                # Suffix range: the last N bytes.
                start = max(0, size - int(raw_end))
            if start > end or start >= size:
                return Response(
                    status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                    headers={"Content-Range": f"bytes */{size}"},
                )
            partial = True

    length = end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    if attachment_name:
        headers["Content-Disposition"] = _content_disposition(attachment_name)

    def iter_file() -> Iterator[bytes]:
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iter_file(),
        status_code=status.HTTP_206_PARTIAL_CONTENT if partial else status.HTTP_200_OK,
        media_type=media_type,
        headers=headers,
    )


def _content_disposition(filename: str) -> str:
    """RFC 6266 header that survives non-ASCII names."""
    from urllib.parse import quote

    ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "download"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
