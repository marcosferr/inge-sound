"""End-to-end worker tests with a stub Demucs, so no model is downloaded."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from app.schemas import JobStatus, SeparationOptions
from app.worker import execute_job


@pytest.fixture
def fake_demucs(tmp_path, monkeypatch):
    """Install a stub that mimics Demucs' CLI: progress bar, output layout, exit code."""
    script = tmp_path / "fake_demucs.py"
    script.write_text(
        textwrap.dedent(
            '''
            import argparse, os, sys, time

            parser = argparse.ArgumentParser()
            parser.add_argument("-n", "--name", default="htdemucs")
            parser.add_argument("--sig")
            parser.add_argument("--repo")
            parser.add_argument("-o", "--out", required=True)
            parser.add_argument("--filename", default="{track}/{stem}.{ext}")
            parser.add_argument("-d", "--device")
            parser.add_argument("--shifts", type=int, default=1)
            parser.add_argument("--overlap", type=float, default=0.25)
            parser.add_argument("--segment", type=int)
            parser.add_argument("--no-split", action="store_true")
            parser.add_argument("--two-stems")
            parser.add_argument("--other-method", default="add")
            parser.add_argument("--clip-mode", default="rescale")
            parser.add_argument("--mp3", action="store_true")
            parser.add_argument("--flac", action="store_true")
            parser.add_argument("--int24", action="store_true")
            parser.add_argument("--float32", action="store_true")
            parser.add_argument("--mp3-bitrate", type=int, default=320)
            parser.add_argument("--mp3-preset", type=int, default=2)
            parser.add_argument("-j", "--jobs", type=int, default=1)
            parser.add_argument("-v", "--verbose", action="store_true")
            parser.add_argument("tracks", nargs="+")
            args = parser.parse_args()

            if os.environ.get("FAKE_DEMUCS_FAIL"):
                print("error: no pude cargar el modelo", file=sys.stderr)
                sys.exit(2)

            ext = "mp3" if args.mp3 else ("flac" if args.flac else "wav")
            stems = [args.two_stems, "no_" + args.two_stems] if args.two_stems else \\
                    ["drums", "bass", "other", "vocals"]

            for path in args.tracks:
                name = os.path.splitext(os.path.basename(path))[0]
                print("Separating track " + path)
                for pct in (10, 50, 100):
                    sys.stdout.write(" %d%%|####| seconds\\r" % pct)
                    sys.stdout.flush()
                    time.sleep(float(os.environ.get("FAKE_DEMUCS_DELAY", "0")))
                print()
                for stem in stems:
                    rel = args.filename.format(track=name, trackext=os.path.basename(path),
                                               stem=stem, ext=ext)
                    target = os.path.join(args.out, args.sig or args.name, rel)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, "wb") as handle:
                        handle.write(b"AUDIO" * 20)
            sys.exit(0)
            '''
        ),
        encoding="utf-8",
    )

    from app import runner, worker

    def build_argv(options, inputs, output_dir, python_executable=None):
        argv = runner.build_argv(options, inputs, output_dir, python_executable=sys.executable)
        # Swap `-m demucs` for the stub, keeping every other flag intact.
        return [argv[0], str(script), *argv[3:]]

    monkeypatch.setattr(worker, "build_argv", build_argv)
    return script


def prepare_job(store, wav_bytes, **options):
    job = store.create(SeparationOptions(**options))
    (store.input_dir(job.id) / "song.wav").write_bytes(wav_bytes)
    return job


def test_successful_run_records_stems_and_progress(store, wav_bytes, fake_demucs):
    job = prepare_job(store, wav_bytes)
    result = execute_job(job.id, store=store)

    assert result.status is JobStatus.completed
    assert result.error is None
    assert [s.stem for s in result.stems] == ["vocals", "drums", "bass", "other"]
    assert all(s.track == "song" for s in result.stems)
    assert result.progress.percent == 100.0
    assert result.started_at and result.finished_at
    assert result.pid is None
    assert "fake_demucs.py" in " ".join(result.command)

    log = store.read_log(job.id)
    assert "Separating track" in log and "100%" in log


def test_options_reach_the_process(store, wav_bytes, fake_demucs):
    job = prepare_job(store, wav_bytes, two_stems="vocals", other_method="minus", format="mp3")
    result = execute_job(job.id, store=store)

    assert result.status is JobStatus.completed
    assert sorted(s.stem for s in result.stems) == ["no_vocals", "vocals"]
    assert all(s.format == "mp3" for s in result.stems)


def test_custom_filename_template(store, wav_bytes, fake_demucs):
    job = prepare_job(store, wav_bytes, filename="{track}-{stem}.{ext}")
    result = execute_job(job.id, store=store)

    assert result.status is JobStatus.completed
    assert {Path(s.rel_path).name for s in result.stems} == {
        "song-vocals.wav", "song-drums.wav", "song-bass.wav", "song-other.wav",
    }


def test_failure_is_reported_not_raised(store, wav_bytes, fake_demucs, monkeypatch):
    monkeypatch.setenv("FAKE_DEMUCS_FAIL", "1")
    job = prepare_job(store, wav_bytes)
    result = execute_job(job.id, store=store)

    assert result.status is JobStatus.failed
    assert "código 2" in result.error
    assert "no pude cargar el modelo" in store.read_log(job.id)


def test_cancellation_before_start(store, wav_bytes, fake_demucs):
    job = prepare_job(store, wav_bytes)
    store.request_cancel(job.id)
    result = execute_job(job.id, store=store)
    assert result.status is JobStatus.cancelled


def test_cancellation_mid_run_kills_the_process(store, wav_bytes, fake_demucs, monkeypatch):
    import threading

    monkeypatch.setenv("FAKE_DEMUCS_DELAY", "1.0")
    job = prepare_job(store, wav_bytes)
    threading.Timer(0.6, lambda: store.request_cancel(job.id)).start()

    result = execute_job(job.id, store=store)

    assert result.status is JobStatus.cancelled
    assert result.pid is None
    assert not store.cancel_requested(job.id)


def test_job_without_inputs_fails_cleanly(store, wav_bytes, fake_demucs):
    job = store.create(SeparationOptions())
    result = execute_job(job.id, store=store)
    assert result.status is JobStatus.failed
    assert "archivos de entrada" in result.error


def test_timeout_stops_the_run(store, wav_bytes, fake_demucs, monkeypatch):
    from app.config import settings

    monkeypatch.setenv("FAKE_DEMUCS_DELAY", "2.0")
    monkeypatch.setattr(settings, "job_timeout_seconds", 1)
    job = prepare_job(store, wav_bytes)

    result = execute_job(job.id, store=store)

    assert result.status is JobStatus.failed
    assert "tiempo máximo" in result.error
