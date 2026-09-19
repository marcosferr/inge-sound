from __future__ import annotations

import json

from app.schemas import JobStatus
from tests.conftest import make_wav


def upload(client, wav_bytes, **options):
    files = [("files", ("song.wav", wav_bytes, "audio/wav"))]
    data = {"options": json.dumps(options)} if options else {}
    return client.post("/api/jobs", files=files, data=data)


def test_capabilities_describes_the_whole_feature_set(client):
    body = client.get("/api/capabilities").json()
    assert body["models"] and body["options"] and body["presets"]
    assert "cpu" in body["devices"]
    assert set(body["formats"]) == {"wav", "flac", "mp3"}
    keys = {option["key"] for option in body["options"]}
    assert {"model", "shifts", "overlap", "two_stems", "segment", "mp3_bitrate"} <= keys


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_create_job_stores_the_upload_and_queues_it(client, wav_bytes):
    response = upload(client, wav_bytes, model="htdemucs_6s", shifts=3, format="mp3")
    assert response.status_code == 201, response.text

    job = response.json()
    assert job["status"] == "queued"
    assert job["options"]["model"] == "htdemucs_6s"
    assert job["options"]["shifts"] == 3
    assert job["tracks"][0]["original_filename"] == "song.wav"
    assert job["tracks"][0]["size_bytes"] == len(wav_bytes)
    assert client.submitted == [job["id"]]


def test_create_job_defaults_options_when_omitted(client, wav_bytes):
    job = upload(client, wav_bytes).json()
    assert job["options"]["model"] == "htdemucs"
    assert job["options"]["overlap"] == 0.25


def test_invalid_options_are_rejected_before_any_work(client, wav_bytes):
    assert upload(client, wav_bytes, shifts=99).status_code == 422
    assert upload(client, wav_bytes, model="htdemucs", two_stems="piano").status_code == 422
    assert client.submitted == []


def test_malformed_options_json(client, wav_bytes):
    response = client.post(
        "/api/jobs",
        files=[("files", ("song.wav", wav_bytes, "audio/wav"))],
        data={"options": "{no-json"},
    )
    assert response.status_code == 422


def test_unsupported_extension_is_refused_and_leaves_nothing_behind(client, store):
    response = client.post(
        "/api/jobs", files=[("files", ("notes.txt", b"hello", "text/plain"))]
    )
    assert response.status_code == 415
    assert list(store.iter_jobs()) == []


def test_upload_over_the_size_limit(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_mb", 0)
    response = client.post(
        "/api/jobs", files=[("files", ("song.wav", make_wav(1.0), "audio/wav"))]
    )
    assert response.status_code == 413


def test_too_many_files(client, monkeypatch, wav_bytes):
    from app.config import settings

    monkeypatch.setattr(settings, "max_files_per_job", 1)
    response = client.post(
        "/api/jobs",
        files=[
            ("files", ("a.wav", wav_bytes, "audio/wav")),
            ("files", ("b.wav", wav_bytes, "audio/wav")),
        ],
    )
    assert response.status_code == 422


def test_batch_upload_keeps_colliding_names_apart(client, store, wav_bytes):
    response = client.post(
        "/api/jobs",
        files=[
            ("files", ("../../song.wav", wav_bytes, "audio/wav")),
            ("files", ("song.wav", wav_bytes, "audio/wav")),
        ],
    )
    assert response.status_code == 201
    job_id = response.json()["id"]
    names = sorted(p.name for p in store.input_dir(job_id).iterdir())
    assert names == ["song.wav", "song_1.wav"]  # traversal stripped, both kept


def test_list_and_filter_jobs(client, store, wav_bytes):
    first = upload(client, wav_bytes).json()["id"]
    upload(client, wav_bytes)

    listing = client.get("/api/jobs").json()
    assert listing["total"] == 2
    assert len(listing["items"]) == 2

    store.update(first, lambda job: setattr(job, "status", JobStatus.completed))
    filtered = client.get("/api/jobs", params={"status": "completed"}).json()
    assert [item["id"] for item in filtered["items"]] == [first]

    page = client.get("/api/jobs", params={"limit": 1, "offset": 1}).json()
    assert len(page["items"]) == 1 and page["total"] == 2


def test_get_missing_job_is_404(client):
    assert client.get("/api/jobs/deadbeef").status_code == 404
    assert client.get("/api/jobs/..%2Fetc").status_code == 404


def test_cancel_marks_the_job_and_then_conflicts(client, store, wav_bytes):
    job_id = upload(client, wav_bytes).json()["id"]
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
    assert store.cancel_requested(job_id)

    store.update(job_id, lambda job: setattr(job, "status", JobStatus.completed))
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 409


def test_delete_removes_everything(client, store, wav_bytes):
    job_id = upload(client, wav_bytes).json()["id"]
    assert client.delete(f"/api/jobs/{job_id}").status_code == 204
    assert not store.job_dir(job_id).exists()
    assert client.delete(f"/api/jobs/{job_id}").status_code == 404


def test_retry_clones_the_inputs_into_a_new_job(client, store, wav_bytes):
    job_id = upload(client, wav_bytes, shifts=2).json()["id"]
    assert client.post(f"/api/jobs/{job_id}/retry").status_code == 409  # still queued

    store.update(job_id, lambda job: setattr(job, "status", JobStatus.failed))
    clone = client.post(f"/api/jobs/{job_id}/retry").json()

    assert clone["id"] != job_id
    assert clone["options"]["shifts"] == 2
    assert len(list(store.input_dir(clone["id"]).iterdir())) == 1
    assert client.submitted[-1] == clone["id"]


def test_log_endpoint(client, store, wav_bytes):
    job_id = upload(client, wav_bytes).json()["id"]
    store.append_log(job_id, "primera linea\nsegunda linea\n")
    assert "segunda" in client.get(f"/api/jobs/{job_id}/log").json()["log"]
    tail = client.get(f"/api/jobs/{job_id}/log", params={"tail_bytes": 8}).json()["log"]
    assert len(tail) <= 8


# --- file serving ----------------------------------------------------------


def completed_job_with_stems(client, store, wav_bytes, payload=b"0123456789" * 10):
    job_id = upload(client, wav_bytes).json()["id"]
    track_dir = store.output_dir(job_id) / "htdemucs" / "song"
    track_dir.mkdir(parents=True)
    for stem in ("vocals", "drums"):
        (track_dir / f"{stem}.wav").write_bytes(payload)

    from app.runner import collect_stems
    from app.schemas import SeparationOptions

    stems = collect_stems(store.output_dir(job_id), SeparationOptions())

    def finish(job):
        job.status = JobStatus.completed
        job.stems = stems

    store.update(job_id, finish)
    return job_id, stems


def test_stream_stem_supports_range_requests(client, store, wav_bytes):
    """The multitrack player seeks, so partial content has to work."""
    job_id, stems = completed_job_with_stems(client, store, wav_bytes)
    url = f"/api/jobs/{job_id}/stems/{stems[0].id}"

    full = client.get(url)
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"
    assert len(full.content) == 100

    partial = client.get(url, headers={"Range": "bytes=10-19"})
    assert partial.status_code == 206
    assert partial.content == b"0123456789"
    assert partial.headers["content-range"] == "bytes 10-19/100"

    suffix = client.get(url, headers={"Range": "bytes=-5"})
    assert suffix.status_code == 206 and suffix.content == b"56789"

    open_ended = client.get(url, headers={"Range": "bytes=95-"})
    assert open_ended.status_code == 206 and len(open_ended.content) == 5

    assert client.get(url, headers={"Range": "bytes=500-600"}).status_code == 416


def test_download_stem_is_an_attachment(client, store, wav_bytes):
    job_id, stems = completed_job_with_stems(client, store, wav_bytes)
    response = client.get(f"/api/jobs/{job_id}/stems/{stems[0].id}/download")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert "song-vocals.wav" in response.headers["content-disposition"]


def test_missing_stem_is_404(client, store, wav_bytes):
    job_id, _ = completed_job_with_stems(client, store, wav_bytes)
    assert client.get(f"/api/jobs/{job_id}/stems/nope").status_code == 404


def test_zip_download_contains_every_stem(client, store, wav_bytes):
    import io
    import zipfile

    job_id, stems = completed_job_with_stems(client, store, wav_bytes)
    response = client.get(f"/api/jobs/{job_id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = sorted(archive.namelist())
        assert names == sorted(stem.rel_path for stem in stems)
        assert archive.read(names[0]) == b"0123456789" * 10


def test_zip_download_refuses_an_unfinished_job(client, wav_bytes):
    job_id = upload(client, wav_bytes).json()["id"]
    assert client.get(f"/api/jobs/{job_id}/download").status_code == 409


# --- adapting to the installed Demucs --------------------------------------


def test_capabilities_reports_unsupported_options(client, legacy_demucs):
    body = client.get("/api/capabilities").json()
    options = {option["key"]: option for option in body["options"]}
    assert options["other_method"]["supported"] is False
    assert [c["value"] for c in options["clip_mode"]["choices"] if not c["supported"]] == ["none"]


def test_options_the_host_cannot_run_are_refused_with_a_reason(client, wav_bytes, legacy_demucs):
    response = upload(client, wav_bytes, two_stems="vocals", other_method="minus")
    assert response.status_code == 422
    assert "--other-method" in str(response.json()["detail"])
    assert client.submitted == []


def test_the_same_options_are_accepted_on_a_newer_demucs(client, wav_bytes, modern_demucs):
    response = upload(client, wav_bytes, two_stems="vocals", other_method="minus")
    assert response.status_code == 201
