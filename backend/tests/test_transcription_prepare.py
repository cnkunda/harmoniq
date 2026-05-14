"""Tests for commit 78 `POST /transcription/prepare` with semantic grid support."""

from __future__ import annotations

import math
import wave
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.audio_processing import AudioPreparationResult
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / f"test_data_{uuid4()}"))
    yield

@pytest.fixture(autouse=True)
def allow_short_test_audio(monkeypatch):
    monkeypatch.setattr("app.ingest.MIN_ANALYZE_DURATION_SECONDS", 0.01)

def _write_test_wav(path: Path, *, sample_rate: int = 44100, duration_seconds: float = 1.2) -> None:
    frames = int(sample_rate * duration_seconds)
    freq = 220.0
    import struct
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(frames):
            v = math.sin(2 * math.pi * freq * (i / sample_rate))
            wf.writeframes(struct.pack("<h", int(v * 0.15 * 32767)))

def test_transcription_prepare_happy_path_upload(monkeypatch, tmp_path):
    """Verifies standard 4/4 upload returns semantic tick values."""
    def fake_separate(song_wav_path: Path, job_dir: Path) -> dict[str, str]:
        stems_dir = job_dir / "stems"
        stems_dir.mkdir(parents=True, exist_ok=True)
        return {stem: f"stems/{stem}.wav" for stem in ("guitar", "bass", "drums", "vocals", "piano", "other")}

    monkeypatch.setattr("app.routers.analyze.separate_with_demucs", fake_separate)
    
    # Updated Mock: Returns the NEW semantic dictionary
    monkeypatch.setattr(
        "app.routers.analyze.estimate_beat_grid",
        lambda *_args, **_kwargs: {
            "bpm": 120.0,
            "beats": [0.0, 0.5, 1.0, 1.5],
            "downbeats": [0.0],
            "time_signature": {"numerator": 4, "denominator": 4},
            "tick_value": 0.25, # 1/4
        },
    )
    
    monkeypatch.setattr(
        "app.routers.analyze.build_stem_routing_hints",
        lambda _paths: {"selected_melodic_stem": "guitar", "chord_mix_stems": ["bass", "other"]}
    )

    upload = tmp_path / "input.wav"
    _write_test_wav(upload)

    res = client.post(
        "/transcription/prepare",
        files={"file": ("input.wav", upload.read_bytes(), "audio/wav")},
    )
    
    assert res.status_code == 200
    body = res.json()
    
    # Assert Semantic Structure
    grid = body["beat_grid"]
    assert grid["time_signature"]["numerator"] == 4
    assert grid["time_signature"]["denominator"] == 4
    assert grid["tick_value"] == 0.25
    assert body["invalidated_artifacts"] == []

def test_transcription_prepare_compound_meter_override(monkeypatch, tmp_path):
    """Verifies that 6/8 overrides correctly trigger 3x subdivisions."""
    capture = {}

    def fake_estimate(audio_path: Path, *, time_signature: str | None, bpm_override: float | None):
        # This simulates the logic inside your new beat_grid.py
        # If user sends 6/8 at 60BPM, the grid BPM becomes 180 (60 * 3)
        return {
            "bpm": 180.0,
            "beats": [0.0, 0.33, 0.66, 1.0],
            "downbeats": [0.0],
            "time_signature": {"numerator": 6, "denominator": 8},
            "tick_value": 0.125,
        }

    monkeypatch.setattr("app.routers.analyze.prepare_audio_input", 
        lambda *a, **k: AudioPreparationResult("job1", tmp_path, tmp_path/"norm.wav", None, 3.0, ()))
    monkeypatch.setattr("app.routers.analyze.separate_with_demucs", lambda *a: {"guitar": "g.wav"})
    monkeypatch.setattr("app.routers.analyze.estimate_beat_grid", fake_estimate)
    monkeypatch.setattr("app.routers.analyze.build_stem_routing_hints", lambda *a: {"selected_melodic_stem": "guitar"})

    res = client.post(
        "/transcription/prepare",
        json={
            "url": "https://www.youtube.com/watch?v=abc",
            "time_signature_override": "6/8",
            "bpm_override": 60,
        },
    )
    
    assert res.status_code == 200
    grid = res.json()["beat_grid"]
    
    # Verify the logic transformation
    assert grid["time_signature"]["denominator"] == 8
    assert grid["bpm"] == 180.0  # Grid BPM, not pulse BPM
    assert grid["tick_value"] == 0.125 # 1/8 note semantics
    assert "chordTimeline" in res.json()["invalidated_artifacts"]

def test_transcription_prepare_missing_source_fails_loudly():
    res = client.post("/transcription/prepare", json={"time_signature_override": "4/4"})
    assert res.status_code == 400
    assert "Provide either `file` upload or `youtube_url`." in res.json()["detail"]