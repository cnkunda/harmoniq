"""HTTP tests for in-memory analyze API (PRIORITIES §3)."""

from __future__ import annotations

import math
import time
import wave
from uuid import UUID, uuid4

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


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    _ = tmp_path
    monkeypatch.setenv("DATA_DIR", f"./.tmp_test_data_{uuid4()}")
    yield


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


def test_upload_audio_normalizes_to_44100_mono_wav(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    input_wav = tmp_path / "upload_input.wav"
    _write_test_wav(input_wav, sample_rate=48000, channels=2)

    wav_bytes = input_wav.read_bytes()
    r = client.post(
        "/analyze",
        files={"file": ("upload_input.wav", wav_bytes, "audio/wav")},
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    body = _poll_until_not_processing(job_id, timeout_seconds=45.0)
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

    # PRIORITIES §9: tab generation (full + skeleton) with confidence-based gating.
    sec0 = result["sections"][0]
    if "tab_full_gp5_base64" not in sec0:
        pytest.skip("tab artifacts absent (librosa/tab pipeline unavailable in this environment)")
    assert "tab_full_gp5_base64" in sec0
    assert isinstance(sec0["tab_full_gp5_base64"], str)
    assert sec0["tab_full_gp5_base64"]

    assert "tab_skeleton_gp5_base64" in sec0
    assert isinstance(sec0["tab_skeleton_gp5_base64"], str)
    assert sec0["tab_skeleton_gp5_base64"]

    # In pytest mode, transcription confidence is low (see transcribe.py guard),
    # so alternate GP5 should be omitted.
    assert "tab_alt_position_gp5_base64" not in sec0
    assert sec0["confidence"] < 0.7
    assert isinstance(sec0.get("coach_note"), str)
    assert sec0["coach_note"].strip()
    assert isinstance(sec0.get("coach_explanation"), str)
    assert sec0["coach_explanation"].strip()


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


def test_analysis_cache_hit_skips_expensive_steps(monkeypatch, tmp_path):
    from app import jobs as jobs_mod

    call_counts = {"separate": 0, "analyze": 0}

    def fake_separate(song_wav_path, job_dir):
        call_counts["separate"] += 1
        stems_dir = job_dir / "stems"
        stems_dir.mkdir(parents=True, exist_ok=True)
        stem_names = ("guitar", "bass", "drums", "vocals", "piano", "other")
        out: dict[str, str] = {}
        for name in stem_names:
            p = stems_dir / f"{name}.wav"
            p.write_bytes(b"RIFF")
            out[name] = p.relative_to(get_data_dir().parent).as_posix()
        return out

    def fake_analyze(
        job_id,
        *,
        guitar_stem_path,
        vocals_stem_path,
        stems,
        wav_path,
        source_url=None,
        player_profile=None,
        source_metadata=None,
    ):
        call_counts["analyze"] += 1
        from app.schemas import LessonJSON, LessonSectionStub

        return LessonJSON(
            job_id=job_id,
            song_title="Cached Test",
            artist="Test",
            key="C major",
            key_confidence=0.9,
            tempo=120.0,
            tempo_confidence=0.9,
            transcription_confidence=0.8,
            beat_grid=[0.0],
            bar_timestamps=[0.0],
            stems=stems,
            lyrics_aligned=[],
            sections=[LessonSectionStub(label="Intro", confidence=0.8)],
            wav_path=wav_path,
        )

    monkeypatch.setattr(jobs_mod, "separate_song_to_stems", fake_separate)
    monkeypatch.setattr(jobs_mod, "build_lesson_json_from_librosa", fake_analyze)

    input_wav = tmp_path / "repeat.wav"
    _write_test_wav(input_wav, sample_rate=44100, channels=1)
    wav_bytes = input_wav.read_bytes()

    r1 = client.post("/analyze", files={"file": ("repeat.wav", wav_bytes, "audio/wav")})
    body1 = _poll_until_not_processing(r1.json()["job_id"])
    assert body1["status"] == "complete"

    r2 = client.post("/analyze", files={"file": ("repeat.wav", wav_bytes, "audio/wav")})
    body2 = _poll_until_not_processing(r2.json()["job_id"])
    assert body2["status"] == "complete"

    assert call_counts["separate"] == 1
    assert call_counts["analyze"] == 1
    assert body1["result"]["job_id"] != body2["result"]["job_id"]


def test_pipeline_version_bump_forces_recompute(monkeypatch, tmp_path):
    from app import cache as cache_mod
    from app import jobs as jobs_mod

    call_counts = {"separate": 0, "analyze": 0}

    def fake_separate(song_wav_path, job_dir):
        call_counts["separate"] += 1
        stems_dir = job_dir / "stems"
        stems_dir.mkdir(parents=True, exist_ok=True)
        stem_names = ("guitar", "bass", "drums", "vocals", "piano", "other")
        out: dict[str, str] = {}
        for name in stem_names:
            p = stems_dir / f"{name}.wav"
            p.write_bytes(b"RIFF")
            out[name] = p.relative_to(get_data_dir().parent).as_posix()
        return out

    def fake_analyze(
        job_id,
        *,
        guitar_stem_path,
        vocals_stem_path,
        stems,
        wav_path,
        source_url=None,
        player_profile=None,
        source_metadata=None,
    ):
        call_counts["analyze"] += 1
        from app.schemas import LessonJSON, LessonSectionStub

        return LessonJSON(
            job_id=job_id,
            song_title="Version Test",
            artist="Test",
            key="C major",
            key_confidence=0.9,
            tempo=120.0,
            tempo_confidence=0.9,
            transcription_confidence=0.8,
            beat_grid=[0.0],
            bar_timestamps=[0.0],
            stems=stems,
            lyrics_aligned=[],
            sections=[LessonSectionStub(label="Intro", confidence=0.8)],
            wav_path=wav_path,
        )

    monkeypatch.setattr(jobs_mod, "separate_song_to_stems", fake_separate)
    monkeypatch.setattr(jobs_mod, "build_lesson_json_from_librosa", fake_analyze)

    input_wav = tmp_path / "version.wav"
    _write_test_wav(input_wav, sample_rate=44100, channels=1)
    wav_bytes = input_wav.read_bytes()

    r1 = client.post("/analyze", files={"file": ("version.wav", wav_bytes, "audio/wav")})
    body1 = _poll_until_not_processing(r1.json()["job_id"])
    assert body1["status"] == "complete"

    monkeypatch.setattr(cache_mod, "PIPELINE_VERSION", "2")

    r2 = client.post("/analyze", files={"file": ("version.wav", wav_bytes, "audio/wav")})
    body2 = _poll_until_not_processing(r2.json()["job_id"])
    assert body2["status"] == "complete"

    assert call_counts["separate"] == 2
    assert call_counts["analyze"] == 2


def test_missing_cached_artifact_forces_recompute(monkeypatch, tmp_path):
    from app import jobs as jobs_mod

    call_counts = {"separate": 0, "analyze": 0}

    def fake_separate(song_wav_path, job_dir):
        call_counts["separate"] += 1
        stems_dir = job_dir / "stems"
        stems_dir.mkdir(parents=True, exist_ok=True)
        stem_names = ("guitar", "bass", "drums", "vocals", "piano", "other")
        out: dict[str, str] = {}
        for name in stem_names:
            p = stems_dir / f"{name}.wav"
            p.write_bytes(b"RIFF")
            out[name] = p.relative_to(get_data_dir().parent).as_posix()
        return out

    def fake_analyze(
        job_id,
        *,
        guitar_stem_path,
        vocals_stem_path,
        stems,
        wav_path,
        source_url=None,
        player_profile=None,
        source_metadata=None,
    ):
        call_counts["analyze"] += 1
        from app.schemas import LessonJSON, LessonSectionStub

        return LessonJSON(
            job_id=job_id,
            song_title="Missing Artifact Test",
            artist="Test",
            key="C major",
            key_confidence=0.9,
            tempo=120.0,
            tempo_confidence=0.9,
            transcription_confidence=0.8,
            beat_grid=[0.0],
            bar_timestamps=[0.0],
            stems=stems,
            lyrics_aligned=[],
            sections=[LessonSectionStub(label="Intro", confidence=0.8)],
            wav_path=wav_path,
        )

    monkeypatch.setattr(jobs_mod, "separate_song_to_stems", fake_separate)
    monkeypatch.setattr(jobs_mod, "build_lesson_json_from_librosa", fake_analyze)

    input_wav = tmp_path / "missing-artifact.wav"
    _write_test_wav(input_wav, sample_rate=44100, channels=1)
    wav_bytes = input_wav.read_bytes()

    r1 = client.post("/analyze", files={"file": ("missing-artifact.wav", wav_bytes, "audio/wav")})
    body1 = _poll_until_not_processing(r1.json()["job_id"])
    assert body1["status"] == "complete"

    # Simulate drift on disk: cached lesson exists, but one referenced artifact was removed.
    backend_root = get_data_dir().parent
    missing_guitar_stem = backend_root / body1["result"]["stems"]["guitar"]
    missing_guitar_stem.unlink()
    assert not missing_guitar_stem.exists()

    r2 = client.post("/analyze", files={"file": ("missing-artifact.wav", wav_bytes, "audio/wav")})
    body2 = _poll_until_not_processing(r2.json()["job_id"])
    assert body2["status"] == "complete"
    assert body2["error"] is None
    assert body2["result"] is not None
    assert body2["result"]["job_id"] != body1["result"]["job_id"]

    # Regression guard: cache-hit fallback must recompute, not fail and not return stale result.
    assert call_counts["separate"] == 2
    assert call_counts["analyze"] == 2

    for stem_name in ("guitar", "bass", "drums", "vocals", "piano", "other"):
        recomputed_stem = backend_root / body2["result"]["stems"][stem_name]
        assert recomputed_stem.exists(), f"Expected recomputed stem {stem_name} at {recomputed_stem}"
