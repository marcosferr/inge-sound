"""Runtime configuration, read from the environment (see ``.env.example``)."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- storage -----------------------------------------------------------
    data_dir: Path = Path("./data")
    max_upload_mb: int = 200
    max_files_per_job: int = 10
    retention_hours: int = 48
    #: How often the background janitor deletes expired jobs. 0 disables it.
    cleanup_interval_minutes: int = 30

    # --- execution ---------------------------------------------------------
    #: "thread" runs separations inside the API process; "celery" hands them to
    #: a Redis-backed worker pool.
    queue_backend: str = "thread"
    worker_concurrency: int = 1
    redis_url: str = "redis://localhost:6379/0"
    #: Hard ceiling per separation. 0 disables the timeout.
    job_timeout_seconds: int = 3 * 60 * 60
    demucs_python: str = Field(default_factory=lambda: sys.executable)
    #: Where Demucs caches downloaded checkpoints.
    torch_home: Path | None = None

    # --- api ---------------------------------------------------------------
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    allowed_extensions: list[str] = [
        ".mp3", ".wav", ".flac", ".ogg", ".oga", ".m4a", ".aac",
        ".wma", ".aiff", ".aif", ".opus", ".mp4", ".webm", ".mkv", ".avi", ".mov",
    ]

    @field_validator("cors_origins", "allowed_extensions", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept both a JSON list and a plain comma-separated env value."""
        if isinstance(value, str) and not value.strip().startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.jobs_dir.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
