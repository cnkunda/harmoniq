"""HTTP tests for in-memory analyze API (PRIORITIES §3)."""

from __future__ import annotations

import math
import time
import wave
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.ingest import get_data_dir
from app.jobs import ANALYSIS_FAILED_USER_MESSAGE, YOUTUBE_URL_INVALID_USER_MESSAGE, jobs
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_jobs():
    jobs.clear()
    yield
    jobs.clear()


def _poll_until_not_processing(job_id: str, *, timeout_seconds: float = 20.0) -> dict:
    start = time.time()
    last: dict | None = None
    while True:
        assert time.time() - start < timeout_seconds, (
            f"Timed out waiting for job {job_id} to finish; last={last}"
        )
        r = client.get(f"/analyze/{job_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        last = body
        if body["status"] != "processing":
            return body
        time.sleep(0.1)


def test_post_analyze_returns_job_id():
    r = client.post("/analyze", json={"url": "force_error"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "job_id" in data
    UUID(data["job_id"])  # raises if invalid


def _write_test_wav(
    path,
    *,
    sample_rate: int,
    channels: int,
    duration_seconds: float = 0.25,
) -> None:
    """Write a small WAV for upload tests (no mp3 encoder required)."""
    frames = int(sample_rate * duration_seconds)
    frequency = 440.0

    import struct

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sample_rate)
        for i in range(frames):
            v = math.sin(2 * math.pi * frequency * (i / sample_rate))
            sample = int(v * 0.2 * 32767)
            for ch in range(channels):
                s = sample if ch % 2 == 0 else -sample
                wf.writeframes(struct.pack("<h", s))


def test_upload_audio_normalizes_to_44100_mono_wav(tmp_path):
    input_wav = tmp_path / "upload_input.wav"
    _write_test_wav(input_wav, sample_rate=48000, channels=2)

    wav_bytes = input_wav.read_bytes()
    r = client.post(
        "/analyze",
        files={"file": ("upload_input.wav", wav_bytes, "audio/wav")},
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    body = _poll_until_not_processing(job_id, timeout_seconds=20.0)
    assert body["status"] == "complete"
    assert body["error"] is None
    assert body["result"] is not None
    assert body["result"]["job_id"] == job_id

    wav_path = get_data_dir() / "jobs" / job_id / "song.wav"
    assert wav_path.exists(), f"Expected normalized wav at {wav_path}"

    with wave.open(str(wav_path), "rb") as wf:
        assert wf.getframerate() == 44100
        assert wf.getnchannels() == 1

    # PRIORITIES §6: Demucs htdemucs_6s integration (fast test mode may skip the
    # actual separation, but the API contract still requires six stem WAVs).
    stems = body["result"]["stems"]
    assert set(stems.keys()) == {"guitar", "bass", "drums", "vocals", "piano", "other"}

    backend_root = get_data_dir().parent
    for stem_name, rel_path_str in stems.items():
        expected = get_data_dir() / "jobs" / job_id / "stems" / f"{stem_name}.wav"
        assert expected.exists(), f"Expected stem wav at {expected}"
        assert expected.stat().st_size > 0, f"Expected non-empty stem wav at {expected}"

        # separate.py returns JSON paths relative to `backend/` with forward slashes.
        expected_rel = expected.relative_to(backend_root).as_posix()
        assert rel_path_str == expected_rel

        with wave.open(str(expected), "rb") as wf:
            assert wf.getframerate() == 44100
            assert wf.getnchannels() == 1

    # PRIORITIES §7: librosa key/tempo/beat grid + bar timestamps + sections wiring.
    result = body["result"]
    assert isinstance(result["beat_grid"], list)
    assert isinstance(result["bar_timestamps"], list)
    assert len(result["bar_timestamps"]) >= 1
    assert all(
        result["bar_timestamps"][i] <= result["bar_timestamps"][i + 1]
        for i in range(len(result["bar_timestamps"]) - 1)
    )
    assert isinstance(result["sections"], list)
    assert len(result["sections"]) >= 1


def test_worker_forced_exception_surfaces_as_failed_with_user_safe_message():
    job_id = client.post("/analyze", json={"url": "force_error"}).json()["job_id"]
    r = client.get(f"/analyze/{job_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "processing"

    body = _poll_until_not_processing(job_id)
    assert body["status"] == "failed"
    assert body["result"] is None
    assert body["error"] == ANALYSIS_FAILED_USER_MESSAGE


def test_invalid_youtube_url_fails_with_user_message():
    job_id = client.post("/analyze", json={"url": "not-a-youtube-url"}).json()["job_id"]
    body = _poll_until_not_processing(job_id)
    assert body["status"] == "failed"
    assert body["result"] is None
    assert body["error"] == YOUTUBE_URL_INVALID_USER_MESSAGE


def test_get_analyze_unknown_job_returns_404_json():
    missing = "00000000-0000-0000-0000-000000000000"
    r = client.get(f"/analyze/{missing}")
    assert r.status_code == 404, r.text
    err = r.json()
    assert "detail" in err
    assert missing in err["detail"]
