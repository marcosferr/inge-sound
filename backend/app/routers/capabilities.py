"""Everything the client needs to build its UI, in one call."""

from __future__ import annotations

from fastapi import APIRouter

from .. import catalog, probe
from ..config import settings
from ..schemas import Capabilities

router = APIRouter(tags=["capabilities"])


@router.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "demucs": probe.demucs_version(),
        "queue_backend": settings.queue_backend,
    }


@router.get("/capabilities", response_model=Capabilities)
def capabilities() -> Capabilities:
    available, default, gpu_name = probe.devices()
    return Capabilities(
        demucs_version=probe.demucs_version(),
        torch_version=probe.torch_version(),
        models=catalog.serialize_models(),
        options=catalog.serialize_options(),
        option_groups=catalog.OPTION_GROUPS,
        presets=catalog.serialize_presets(),
        devices=available,
        default_device=default,
        gpu_name=gpu_name,
        formats=["wav", "flac", "mp3"],
        allowed_extensions=settings.allowed_extensions,
        max_upload_mb=settings.max_upload_mb,
        max_files_per_job=settings.max_files_per_job,
        retention_hours=settings.retention_hours,
        queue_backend=settings.queue_backend,
        ffmpeg_available=probe.ffmpeg_available(),
    )
