"""Runtime introspection: what this particular server can actually do.

Everything here is best-effort and cached — the UI uses it to hide options the
host cannot honour (no CUDA, no ffmpeg), not to gate correctness.
"""

from __future__ import annotations

import shutil
from functools import lru_cache
from importlib import metadata


@lru_cache
def demucs_version() -> str | None:
    try:
        return metadata.version("demucs")
    except metadata.PackageNotFoundError:
        return None


@lru_cache
def torch_version() -> str | None:
    try:
        import torch
    except ImportError:
        return None
    return torch.__version__


@lru_cache
def devices() -> tuple[list[str], str, str | None]:
    """Return ``(available, default, gpu_name)``."""
    available = ["cpu"]
    default = "cpu"
    gpu_name: str | None = None
    try:
        import torch
    except ImportError:
        return available, default, gpu_name

    if torch.cuda.is_available():
        available.insert(0, "cuda")
        default = "cuda"
        try:
            gpu_name = torch.cuda.get_device_name(0)
        except Exception:  # noqa: BLE001 - driver quirks shouldn't break /capabilities
            gpu_name = "CUDA"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        available.insert(0, "mps")
        if default == "cpu":
            default = "mps"
            gpu_name = "Apple Silicon (MPS)"
    return available, default, gpu_name


@lru_cache
def ffmpeg_available() -> bool:
    """ffmpeg widens the accepted input formats (m4a, video containers…)."""
    return shutil.which("ffmpeg") is not None


def probe_duration(path) -> float | None:
    """Duration in seconds, or ``None`` when it cannot be determined cheaply."""
    try:
        import soundfile

        with soundfile.SoundFile(str(path)) as handle:
            if handle.samplerate:
                return len(handle) / float(handle.samplerate)
    except Exception:  # noqa: BLE001 - mp3/m4a often need ffmpeg instead
        pass

    if not ffmpeg_available():
        return None
    import json
    import subprocess

    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, path is a local file
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "json", str(path),
            ],
            capture_output=True,
            timeout=20,
            check=False,
        )
        if result.returncode == 0:
            return float(json.loads(result.stdout)["format"]["duration"])
    except Exception:  # noqa: BLE001
        return None
    return None


# --------------------------------------------------------------------------- #
# Which Demucs flags this install actually accepts
# --------------------------------------------------------------------------- #
#
# The CLI surface moves between releases: 4.0.1 has no ``--other-method`` and
# its ``--clip-mode`` has no ``none``, while the development branch has both.
# Parsing ``--help`` once lets the wrapper offer exactly what the host supports
# instead of building a command Demucs will reject.

FLAG_RE = __import__("re").compile(r"(?<![\w-])(--?[a-zA-Z][\w-]*)")
CHOICES_RE = __import__("re").compile(r"(--[\w-]+)\s+\{([^}]+)\}")


@lru_cache
def demucs_help() -> str:
    """``demucs --help`` output, or an empty string if it cannot be run."""
    import subprocess

    from .config import settings

    try:
        result = subprocess.run(  # noqa: S603 - fixed argv
            [settings.demucs_python, "-m", "demucs", "--help"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception:  # noqa: BLE001 - demucs may not be installed at all
        return ""
    return result.stdout if result.returncode == 0 else ""


@lru_cache
def supported_flags() -> frozenset[str]:
    """Every flag named in ``--help``.

    An empty set means the probe failed; callers must then assume everything is
    supported rather than silently dropping options.
    """
    help_text = demucs_help()
    if not help_text:
        return frozenset()
    return frozenset(FLAG_RE.findall(help_text))


@lru_cache
def flag_choices() -> dict[str, tuple[str, ...]]:
    """Accepted values for the flags that declare a ``{a,b}`` choice set."""
    help_text = demucs_help()
    if not help_text:
        return {}
    return {
        flag: tuple(value.strip() for value in values.split(","))
        for flag, values in CHOICES_RE.findall(help_text)
    }


def flag_supported(flag: str) -> bool:
    known = supported_flags()
    return not known or flag in known


def choice_supported(flag: str, value: str) -> bool:
    choices = flag_choices().get(flag)
    return choices is None or value in choices
