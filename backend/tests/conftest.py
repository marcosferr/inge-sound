from __future__ import annotations

import io
import struct
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Point the whole app at a throwaway data directory."""
    from app.config import get_settings, settings

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.jobs_dir.mkdir(parents=True, exist_ok=True)
    get_settings.cache_clear()

    from app import jobstore

    fresh = jobstore.JobStore(settings.jobs_dir)
    monkeypatch.setattr(jobstore, "store", fresh)
    for module in ("app.routers.jobs", "app.routers.files", "app.worker"):
        if module in sys.modules:
            monkeypatch.setattr(sys.modules[module], "store", fresh, raising=False)
    yield fresh


@pytest.fixture
def store(isolated_data_dir):
    return isolated_data_dir


@pytest.fixture
def client(monkeypatch):
    """Test client whose queue never actually launches Demucs."""
    from fastapi.testclient import TestClient

    from app import queue
    from app.main import create_app
    from app.routers import jobs as jobs_router

    submitted: list[str] = []
    monkeypatch.setattr(queue, "submit", submitted.append)
    monkeypatch.setattr(jobs_router.queue, "submit", submitted.append)

    with TestClient(create_app()) as test_client:
        test_client.submitted = submitted  # type: ignore[attr-defined]
        yield test_client


def make_wav(seconds: float = 0.2, sample_rate: int = 8000) -> bytes:
    """A tiny valid mono WAV, so uploads exercise the real code path."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = int(seconds * sample_rate)
        handle.writeframes(b"".join(struct.pack("<h", (i * 32) % 3000) for i in range(frames)))
    return buffer.getvalue()


@pytest.fixture
def wav_bytes() -> bytes:
    return make_wav()


# --- Demucs CLI surface ------------------------------------------------------
# The exposed flag set differs between releases, so tests state which surface
# they assume instead of depending on whatever Demucs the host happens to have.

LEGACY_FLAGS = frozenset([
    "-h", "--help", "-s", "--sig", "-n", "--name", "--repo", "-v", "--verbose",
    "-o", "--out", "--filename", "-d", "--device", "--shifts", "--overlap",
    "--no-split", "--segment", "--two-stems", "--int24", "--float32",
    "--clip-mode", "--flac", "--mp3", "--mp3-bitrate", "--mp3-preset", "-j", "--jobs",
])
MODERN_FLAGS = LEGACY_FLAGS | {"--other-method"}


def _patch_probe(monkeypatch, flags, choices):
    from app import probe

    monkeypatch.setattr(probe, "supported_flags", lambda: frozenset(flags))
    monkeypatch.setattr(probe, "flag_choices", lambda: dict(choices))


@pytest.fixture
def legacy_demucs(monkeypatch):
    """Demucs 4.0.1: no --other-method, --clip-mode without 'none'."""
    _patch_probe(monkeypatch, LEGACY_FLAGS, {"--clip-mode": ("rescale", "clamp")})


@pytest.fixture
def modern_demucs(monkeypatch):
    """Demucs main branch: every flag this wrapper knows about."""
    _patch_probe(
        monkeypatch, MODERN_FLAGS, {"--clip-mode": ("rescale", "clamp", "none")}
    )


@pytest.fixture
def unprobeable_demucs(monkeypatch):
    """`demucs --help` could not be run, so nothing is known."""
    _patch_probe(monkeypatch, frozenset(), {})


@pytest.fixture(autouse=True)
def _default_demucs_surface(request, monkeypatch):
    """Assume the released 4.0.1 surface unless a test says otherwise."""
    explicit = {"legacy_demucs", "modern_demucs", "unprobeable_demucs"}
    if explicit & set(request.fixturenames):
        return
    _patch_probe(monkeypatch, LEGACY_FLAGS, {"--clip-mode": ("rescale", "clamp")})
