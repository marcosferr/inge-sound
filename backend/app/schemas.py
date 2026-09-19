"""Request and response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .catalog import ALL_STEMS, DEFAULT_MODEL, MODELS_BY_NAME


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


TERMINAL_STATUSES = {JobStatus.completed, JobStatus.failed, JobStatus.cancelled}


class SeparationOptions(BaseModel):
    """Every Demucs flag this wrapper exposes, validated.

    Field names mirror ``catalog.OPTIONS`` keys one for one.
    """

    model_config = ConfigDict(extra="forbid")

    model: str = DEFAULT_MODEL
    signature: str | None = None
    repo: str | None = None

    device: Literal["auto", "cuda", "mps", "cpu"] = "auto"
    shifts: int = Field(default=1, ge=0, le=20)
    overlap: float = Field(default=0.25, ge=0.0, lt=1.0)
    split: bool = True
    segment: int | None = Field(default=None, ge=1, le=3600)
    jobs: int = Field(default=1, ge=1, le=32)

    two_stems: str | None = None
    other_method: Literal["add", "minus", "none"] = "add"

    format: Literal["wav", "flac", "mp3"] = "wav"
    bit_depth: Literal["int16", "int24", "float32"] = "int16"
    mp3_bitrate: int = Field(default=320, ge=64, le=320)
    mp3_preset: int = Field(default=2, ge=2, le=7)
    clip_mode: Literal["rescale", "clamp", "none"] = "rescale"
    filename: str = "{track}/{stem}.{ext}"

    verbose: bool = False

    @model_validator(mode="after")
    def _check_consistency(self) -> SeparationOptions:
        if self.two_stems is not None:
            if self.two_stems not in ALL_STEMS:
                raise ValueError(
                    f"two_stems debe ser uno de {ALL_STEMS}, no {self.two_stems!r}"
                )
            available = MODELS_BY_NAME.get(self.model)
            if available and self.two_stems not in available.stems:
                raise ValueError(
                    f"El modelo {self.model} no produce la pista {self.two_stems!r}; "
                    f"produce {available.stems}."
                )
        if "{stem}" not in self.filename:
            raise ValueError("La plantilla de nombre debe incluir '{stem}'.")
        if any(part in self.filename for part in ("..", "\\")) or self.filename.startswith("/"):
            raise ValueError("La plantilla de nombre no puede salir del directorio de salida.")
        return self

    @property
    def effective_model(self) -> str:
        return self.signature or self.model


class StemFile(BaseModel):
    id: str
    track: str
    stem: str
    filename: str
    #: Path relative to the job's output directory.
    rel_path: str
    size_bytes: int
    format: str


class TrackInfo(BaseModel):
    name: str
    original_filename: str
    size_bytes: int
    duration_seconds: float | None = None


class JobProgress(BaseModel):
    percent: float = 0.0
    stage: str = "queued"
    current_track: str | None = None
    tracks_done: int = 0
    tracks_total: int = 0
    eta_seconds: float | None = None


class Job(BaseModel):
    id: str
    status: JobStatus = JobStatus.queued
    options: SeparationOptions
    tracks: list[TrackInfo] = []
    stems: list[StemFile] = []
    progress: JobProgress = JobProgress()
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    expires_at: datetime | None = None
    command: list[str] = []
    #: Set by the worker so cancellation can reach the right process.
    pid: int | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


class JobList(BaseModel):
    items: list[Job]
    total: int
    limit: int
    offset: int


class Capabilities(BaseModel):
    demucs_version: str | None
    torch_version: str | None
    models: list[dict[str, Any]]
    options: list[dict[str, Any]]
    option_groups: list[dict[str, Any]]
    presets: list[dict[str, Any]]
    devices: list[str]
    default_device: str
    gpu_name: str | None = None
    formats: list[str]
    allowed_extensions: list[str]
    max_upload_mb: int
    max_files_per_job: int
    retention_hours: int
    queue_backend: str
    ffmpeg_available: bool
