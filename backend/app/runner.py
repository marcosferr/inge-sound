"""Build and execute the Demucs command line, tracking progress.

The wrapper shells out to ``python -m demucs`` instead of importing the library:
it keeps every CLI flag available for free, and a segfault or an out-of-memory
kill takes down the child process instead of the API.
"""

from __future__ import annotations

import contextlib
import os
import re
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from . import probe
from .config import settings
from .schemas import SeparationOptions, StemFile

#: Demucs renders a tqdm bar (``ss 42%|####   | 2.4/5.8``). Requiring the bar
#: delimiter keeps plain prose like "CPU at 87% load" out of the progress math.
PERCENT_RE = re.compile(rb"(\d{1,3}(?:\.\d+)?)%\|")
#: Emitted once per input file.
SEPARATING_RE = re.compile(rb"Separating track (.+)")

AUDIO_SUFFIXES = {".wav", ".mp3", ".flac"}


class DemucsError(RuntimeError):
    """Demucs exited with a non-zero status."""


@dataclass
class ProgressUpdate:
    percent: float
    stage: str
    current_track: str | None
    tracks_done: int
    tracks_total: int
    eta_seconds: float | None


ProgressCallback = Callable[[ProgressUpdate], None]
LogCallback = Callable[[str], None]


def build_argv(
    options: SeparationOptions,
    inputs: Iterable[Path],
    output_dir: Path,
    python_executable: str | None = None,
) -> list[str]:
    """Translate validated options into a ``python -m demucs`` argument list.

    Flags the installed Demucs does not know are left out rather than passed and
    rejected; ``catalog.unsupported_reasons`` is what tells the user about it.
    """
    argv: list[str] = [python_executable or settings.demucs_python, "-m", "demucs"]

    if options.signature:
        argv += ["--sig", options.signature]
    else:
        argv += ["-n", options.model]
    if options.repo:
        argv += ["--repo", options.repo]

    argv += ["-o", str(output_dir)]
    if probe.flag_supported("--filename"):
        argv += ["--filename", options.filename]

    if options.device != "auto":
        argv += ["-d", options.device]

    argv += ["--shifts", str(options.shifts)]
    argv += ["--overlap", str(options.overlap)]
    argv += ["-j", str(options.jobs)]

    if not options.split:
        argv.append("--no-split")
    elif options.segment is not None:
        argv += ["--segment", str(options.segment)]

    if options.two_stems:
        argv += ["--two-stems", options.two_stems]
        if probe.flag_supported("--other-method"):
            argv += ["--other-method", options.other_method]

    if options.format == "mp3":
        argv += [
            "--mp3",
            "--mp3-bitrate",
            str(options.mp3_bitrate),
            "--mp3-preset",
            str(options.mp3_preset),
        ]
    elif options.format == "flac":
        argv.append("--flac")
    elif options.bit_depth == "int24":
        argv.append("--int24")
    elif options.bit_depth == "float32":
        argv.append("--float32")

    # choice_supported() alone is not enough: it answers "yes" for a flag that
    # is not in --help at all, which is exactly the case to skip.
    if probe.flag_supported("--clip-mode") and probe.choice_supported(
        "--clip-mode", options.clip_mode
    ):
        argv += ["--clip-mode", options.clip_mode]

    if options.verbose:
        argv.append("-v")

    argv += [str(path) for path in inputs]
    return argv


class ProgressTracker:
    """Turns Demucs' tqdm output into one monotonic percentage for the job.

    Bag models (``htdemucs_ft``, ``mdx``…) restart the bar once per network, so a
    drop in the reported percentage means "next network", not "went backwards".
    """

    def __init__(self, tracks_total: int, sub_models: int) -> None:
        self.tracks_total = max(tracks_total, 1)
        self.sub_models = max(sub_models, 1)
        self.tracks_done = 0
        self.current_track: str | None = None
        self.sub_model_index = 0
        self.last_percent = 0.0
        self.overall = 0.0
        self.started = time.monotonic()

    def start_track(self, name: str) -> None:
        if self.current_track is not None:
            self.tracks_done += 1
        self.current_track = name
        self.sub_model_index = 0
        self.last_percent = 0.0

    def observe_percent(self, percent: float) -> None:
        """Fold one bar reading into the overall percentage.

        Readings before the first ``Separating track`` belong to the checkpoint
        download, whose bar also reaches 100%. Counting those would pin the job
        at 99% for its entire run, since ``overall`` never goes back down.
        """
        if self.current_track is None:
            return
        # A meaningful drop means the bar restarted for the next sub-model.
        if percent + 5.0 < self.last_percent:
            self.sub_model_index = min(self.sub_model_index + 1, self.sub_models - 1)
        self.last_percent = percent
        within_track = (self.sub_model_index + percent / 100.0) / self.sub_models
        candidate = (self.tracks_done + min(within_track, 1.0)) / self.tracks_total * 100.0
        self.overall = max(self.overall, min(candidate, 99.0))

    def finish(self) -> None:
        self.tracks_done = self.tracks_total
        self.overall = 100.0

    @property
    def eta_seconds(self) -> float | None:
        if self.overall <= 1.0:
            return None
        elapsed = time.monotonic() - self.started
        return max(0.0, elapsed * (100.0 - self.overall) / self.overall)

    def snapshot(self, stage: str) -> ProgressUpdate:
        return ProgressUpdate(
            percent=round(self.overall, 2),
            stage=stage,
            current_track=self.current_track,
            tracks_done=self.tracks_done,
            tracks_total=self.tracks_total,
            eta_seconds=self.eta_seconds,
        )


def run_demucs(
    argv: list[str],
    tracks_total: int,
    sub_models: int,
    on_progress: ProgressCallback | None = None,
    on_log: LogCallback | None = None,
    on_start: Callable[[int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
) -> int:
    """Run Demucs, streaming progress until it exits.

    Returns the exit code. Raises :class:`TimeoutError` when the run exceeds
    ``timeout``; the child is always terminated before returning.
    """
    child_env = os.environ.copy()
    if settings.torch_home:
        child_env["TORCH_HOME"] = str(settings.torch_home)
    # Unbuffered output, otherwise the progress bar only arrives at the end.
    child_env["PYTHONUNBUFFERED"] = "1"
    if env:
        child_env.update(env)

    process = subprocess.Popen(  # noqa: S603 - argv is built from validated options
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=child_env,
        start_new_session=True,
    )
    if on_start:
        on_start(process.pid)

    tracker = ProgressTracker(tracks_total, sub_models)
    last_emit = 0.0
    last_bar_log = 0.0

    # Cancellation and the timeout run on their own thread: Demucs is silent for
    # minutes while it imports torch and downloads a checkpoint, so checks driven
    # by its output would not fire during exactly the wait a user wants to abort.
    watchdog = _Watchdog(process, should_cancel, timeout)
    watchdog.start()

    try:
        assert process.stdout is not None
        for chunk in _iter_lines(process.stdout):
            # tqdm redraws ~10x/s; logging every redraw makes a long job's log
            # tens of MB of progress bar. The finished bar is always kept.
            is_bar = b"%|" in chunk
            now = time.monotonic()
            if is_bar and b"100%|" not in chunk and now - last_bar_log <= 1.0:
                keep = False
            else:
                keep = True
                if is_bar:
                    last_bar_log = now
            if on_log and keep:
                on_log(chunk.decode("utf-8", errors="replace"))

            match = SEPARATING_RE.search(chunk)
            if match:
                name = match.group(1).decode("utf-8", errors="replace").strip()
                tracker.start_track(Path(name).name)

            percents = PERCENT_RE.findall(chunk)
            if percents:
                with contextlib.suppress(ValueError):
                    tracker.observe_percent(float(percents[-1]))

            if on_progress and (now - last_emit > 0.5 or match):
                last_emit = now
                stage = "separating" if tracker.current_track else "loading"
                on_progress(tracker.snapshot(stage))

        code = _wait(process)
    finally:
        watchdog.stop()
        if process.poll() is None:  # pragma: no cover - only on unexpected exits
            _terminate(process)

    if watchdog.timed_out:
        raise TimeoutError(f"Demucs superó el tiempo máximo de {timeout}s y fue detenido.")
    if watchdog.cancelled:
        return -signal.SIGTERM

    if code == 0 and on_progress:
        tracker.finish()
        on_progress(tracker.snapshot("finished"))
    return code


class _Watchdog:
    """Terminates the child on cancellation or timeout, independently of output."""

    INTERVAL = 0.25

    def __init__(
        self,
        process: subprocess.Popen,
        should_cancel: Callable[[], bool] | None,
        timeout: int | None,
    ) -> None:
        self._process = process
        self._should_cancel = should_cancel
        self._deadline = time.monotonic() + timeout if timeout else None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="demucs-watchdog")
        self.cancelled = False
        self.timed_out = False

    def start(self) -> None:
        if self._should_cancel or self._deadline:
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.wait(self.INTERVAL):
            if self._process.poll() is not None:
                return
            if self._should_cancel and self._should_cancel():
                self.cancelled = True
            elif self._deadline and time.monotonic() > self._deadline:
                self.timed_out = True
            else:
                continue
            _terminate(self._process)
            return


def _wait(process: subprocess.Popen, timeout: float = 60.0) -> int:
    """Reap the child after its output closed, without hanging forever."""
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:  # pragma: no cover - child ignored EOF
        _terminate(process)
        return process.returncode if process.returncode is not None else -signal.SIGKILL


def _iter_lines(stream) -> Iterable[bytes]:
    """Yield output chunks split on newline *and* carriage return.

    tqdm redraws its bar with ``\\r``, so reading by line alone would buffer the
    whole progress bar into a single chunk that only arrives at the end.
    """
    buffer = b""
    while True:
        byte = stream.read(1)
        if not byte:
            break
        if byte in (b"\n", b"\r"):
            if buffer:
                yield buffer
                buffer = b""
        else:
            buffer += byte
    if buffer:
        yield buffer


def _terminate(process: subprocess.Popen) -> None:
    """Stop the child and everything it spawned (Demucs forks worker processes)."""
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:  # pragma: no cover - stubborn child
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            process.kill()
        process.wait(timeout=10)


def collect_stems(output_dir: Path, options: SeparationOptions) -> list[StemFile]:
    """Discover what Demucs actually wrote.

    The layout follows ``--filename`` under ``<out>/<model>/``, and a custom
    template can move things around, so the files are found by walking the tree
    rather than by reconstructing the expected paths.
    """
    stems: list[StemFile] = []
    if not output_dir.exists():
        return stems

    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        rel = path.relative_to(output_dir)
        parts = rel.parts
        # <model>/<track>/<stem>.<ext> by default; fall back gracefully.
        stem_name = path.stem
        track = parts[-2] if len(parts) >= 2 else ""
        if track == options.effective_model:
            track = ""
        stems.append(
            StemFile(
                id=_stem_id(rel),
                track=track,
                stem=stem_name,
                filename=path.name,
                rel_path=rel.as_posix(),
                size_bytes=path.stat().st_size,
                format=path.suffix.lstrip(".").lower(),
            )
        )
    stems.sort(key=lambda s: (s.track, _stem_order(s.stem), s.stem))
    return stems


#: Musical order beats alphabetical order in the player.
_STEM_ORDER = ["vocals", "drums", "bass", "guitar", "piano", "other"]


def _stem_order(stem: str) -> int:
    base = stem[3:] if stem.startswith("no_") else stem
    try:
        return _STEM_ORDER.index(base)
    except ValueError:
        return len(_STEM_ORDER)


def _stem_id(rel: Path) -> str:
    import hashlib

    return hashlib.sha1(rel.as_posix().encode("utf-8")).hexdigest()[:16]
