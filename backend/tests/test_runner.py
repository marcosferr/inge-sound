from __future__ import annotations

import io
from pathlib import Path

from app.runner import (
    ProgressTracker,
    _iter_lines,
    build_argv,
    collect_stems,
)
from app.schemas import SeparationOptions


def argv_for(**options) -> list[str]:
    return build_argv(
        SeparationOptions(**options),
        [Path("/in/song.mp3")],
        Path("/out"),
        python_executable="python3",
    )


def test_defaults_produce_a_runnable_command():
    argv = argv_for()
    assert argv[:3] == ["python3", "-m", "demucs"]
    assert argv[-1] == "/in/song.mp3"
    assert "-n" in argv and argv[argv.index("-n") + 1] == "htdemucs"
    assert argv[argv.index("-o") + 1] == "/out"
    assert argv[argv.index("--shifts") + 1] == "1"
    assert argv[argv.index("--overlap") + 1] == "0.25"
    assert argv[argv.index("--clip-mode") + 1] == "rescale"
    # No device flag means "let Demucs pick".
    assert "-d" not in argv


def test_device_is_only_passed_when_not_auto():
    assert "-d" not in argv_for(device="auto")
    cuda = argv_for(device="cuda")
    assert cuda[cuda.index("-d") + 1] == "cuda"


def test_signature_replaces_the_model_name():
    argv = argv_for(signature="abcd1234", repo="/models")
    assert "--sig" in argv and argv[argv.index("--sig") + 1] == "abcd1234"
    assert "-n" not in argv
    assert argv[argv.index("--repo") + 1] == "/models"


def test_mp3_carries_bitrate_and_preset():
    argv = argv_for(format="mp3", mp3_bitrate=192, mp3_preset=5)
    assert "--mp3" in argv
    assert argv[argv.index("--mp3-bitrate") + 1] == "192"
    assert argv[argv.index("--mp3-preset") + 1] == "5"


def test_flac_and_wav_depth_flags_are_mutually_exclusive():
    assert "--flac" in argv_for(format="flac")
    assert "--int24" in argv_for(format="wav", bit_depth="int24")
    assert "--float32" in argv_for(format="wav", bit_depth="float32")
    # Bit depth is meaningless outside WAV, so it must not leak into the mp3 run.
    mp3 = argv_for(format="mp3", bit_depth="float32")
    assert "--float32" not in mp3 and "--int24" not in mp3


def test_segment_is_dropped_when_splitting_is_disabled():
    split_off = argv_for(split=False, segment=10)
    assert "--no-split" in split_off and "--segment" not in split_off
    split_on = argv_for(split=True, segment=10)
    assert "--no-split" not in split_on and split_on[split_on.index("--segment") + 1] == "10"


def test_two_stems_is_always_passed():
    argv = argv_for(two_stems="vocals")
    assert argv[argv.index("--two-stems") + 1] == "vocals"
    assert "--two-stems" not in argv_for()


def test_other_method_is_only_passed_when_demucs_knows_it(modern_demucs):
    """Demucs 4.0.1 has no --other-method; the dev branch does."""
    argv = argv_for(two_stems="vocals", other_method="minus")
    assert argv[argv.index("--other-method") + 1] == "minus"


def test_other_method_is_dropped_on_an_older_demucs(legacy_demucs):
    argv = argv_for(two_stems="vocals", other_method="minus")
    assert "--other-method" not in argv
    assert "--two-stems" in argv  # the rest of the run is unaffected


def test_clip_mode_value_is_dropped_when_unsupported(legacy_demucs):
    assert "--clip-mode" not in argv_for(clip_mode="none")
    assert argv_for(clip_mode="clamp")[-3:-1] == ["--clip-mode", "clamp"]


def test_unknown_demucs_means_pass_everything(unprobeable_demucs):
    """If --help cannot be read, never silently strip the user's options."""
    argv = argv_for(two_stems="vocals", other_method="minus", clip_mode="none")
    assert "--other-method" in argv and "--clip-mode" in argv


def test_verbose_and_jobs():
    assert "-v" in argv_for(verbose=True)
    assert "-v" not in argv_for()
    argv = argv_for(jobs=4)
    assert argv[argv.index("-j") + 1] == "4"


def test_all_inputs_are_appended():
    argv = build_argv(
        SeparationOptions(),
        [Path("/in/a.wav"), Path("/in/b.wav")],
        Path("/out"),
        python_executable="python3",
    )
    assert argv[-2:] == ["/in/a.wav", "/in/b.wav"]


# --- progress --------------------------------------------------------------


def test_progress_is_monotonic_across_one_track():
    tracker = ProgressTracker(tracks_total=1, sub_models=1)
    tracker.start_track("song.mp3")
    seen = []
    for percent in (5.0, 40.0, 40.0, 80.0):
        tracker.observe_percent(percent)
        seen.append(tracker.overall)
    assert seen == sorted(seen)
    assert seen[-1] < 100.0  # only `finish()` may claim 100%


def test_bar_restart_advances_to_the_next_sub_model():
    """htdemucs_ft runs four networks and restarts its bar for each one."""
    tracker = ProgressTracker(tracks_total=1, sub_models=4)
    tracker.start_track("song.mp3")
    tracker.observe_percent(100.0)
    after_first = tracker.overall
    tracker.observe_percent(1.0)
    assert tracker.sub_model_index == 1
    assert tracker.overall >= after_first  # never goes backwards
    assert 20.0 <= after_first <= 30.0  # one of four networks done


def test_progress_spans_multiple_tracks():
    tracker = ProgressTracker(tracks_total=2, sub_models=1)
    tracker.start_track("a.wav")
    tracker.observe_percent(100.0)
    tracker.start_track("b.wav")
    tracker.observe_percent(50.0)
    assert 70.0 <= tracker.overall <= 80.0
    assert tracker.tracks_done == 1
    tracker.finish()
    assert tracker.overall == 100.0
    assert tracker.snapshot("finished").tracks_done == 2


def test_iter_lines_splits_on_carriage_returns():
    """tqdm redraws with \\r; splitting on newlines alone would buffer the bar."""
    stream = io.BytesIO(b"Separating track a.wav\n 10%|#  \r 55%|#####  \rdone\n")
    chunks = [chunk.decode() for chunk in _iter_lines(stream)]
    assert chunks[0] == "Separating track a.wav"
    assert "10%" in chunks[1]
    assert "55%" in chunks[2]
    assert chunks[-1] == "done"


# --- output discovery ------------------------------------------------------


def test_collect_stems_finds_and_orders_the_output(tmp_path):
    out = tmp_path / "output"
    track_dir = out / "htdemucs" / "song"
    track_dir.mkdir(parents=True)
    for stem in ("other", "vocals", "bass", "drums"):
        (track_dir / f"{stem}.wav").write_bytes(b"RIFF" + b"\0" * 100)
    (track_dir / "notes.txt").write_text("ignorame")

    stems = collect_stems(out, SeparationOptions())

    assert [s.stem for s in stems] == ["vocals", "drums", "bass", "other"]
    assert all(s.track == "song" for s in stems)
    assert all(s.format == "wav" and s.size_bytes > 0 for s in stems)
    assert len({s.id for s in stems}) == 4


def test_collect_stems_handles_a_flat_filename_template(tmp_path):
    out = tmp_path / "output"
    model_dir = out / "htdemucs"
    model_dir.mkdir(parents=True)
    (model_dir / "vocals.mp3").write_bytes(b"\xff\xfb" + b"\0" * 50)

    stems = collect_stems(out, SeparationOptions(filename="{stem}.{ext}", format="mp3"))

    assert len(stems) == 1
    assert stems[0].track == ""  # the model folder is not a track name
    assert stems[0].format == "mp3"


def test_collect_stems_on_a_missing_directory(tmp_path):
    assert collect_stems(tmp_path / "nope", SeparationOptions()) == []


# --- progress against real Demucs output -----------------------------------

# Verbatim from a real run's job.log: Demucs downloads the checkpoint before it
# says anything about the track, and that download has its own tqdm bar.
DOWNLOAD_OUTPUT = [
    b'Downloading: "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8.th"',
    b"  0%|          | 0.00/80.2M [00:00<?, ?B/s]",
    b" 44%|****      | 35.6M/80.2M [00:00<00:00, 136MB/s]",
    b"100%|**********| 80.2M/80.2M [00:00<00:00, 141MB/s]",
]


def feed(tracker, lines):
    from app.runner import PERCENT_RE, SEPARATING_RE

    for line in lines:
        match = SEPARATING_RE.search(line)
        if match:
            tracker.start_track(match.group(1).decode().strip())
        found = PERCENT_RE.findall(line)
        if found:
            tracker.observe_percent(float(found[-1]))


def test_checkpoint_download_does_not_move_the_progress_bar():
    """Otherwise the job reads 99% from the first second of a fresh install."""
    tracker = ProgressTracker(tracks_total=1, sub_models=1)
    feed(tracker, DOWNLOAD_OUTPUT)

    assert tracker.overall == 0.0
    assert tracker.current_track is None

    feed(tracker, [b"Separating track /in/song.wav", b" 20%|##   | 1.2/5.8 [00:01<00:04]"])
    assert 15.0 <= tracker.overall <= 25.0


def test_prose_percentages_are_not_progress():
    tracker = ProgressTracker(tracks_total=1, sub_models=1)
    feed(tracker, [b"Separating track /in/song.wav", b"warning: CPU at 87% load"])
    assert tracker.overall == 0.0


def test_percent_regex_requires_the_bar_delimiter():
    from app.runner import PERCENT_RE

    assert PERCENT_RE.findall(b" 42%|####  | 2.4/5.8") == [b"42"]
    assert PERCENT_RE.findall(b"CPU at 87% load") == []
