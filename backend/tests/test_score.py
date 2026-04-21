from __future__ import annotations

import base64
import io
import time
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import ScoreRequest

pytest.importorskip("librosa")

from app.score import score_recording

client = TestClient(app)

def _wav_b64_from_signal(y: np.ndarray, sr: int = 22050) -> str:
    pcm16 = np.clip(y.astype(np.float32), -1.0, 1.0)
    pcm16 = (pcm16 * 32767.0).astype(np.int16)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())
    return base64.b64encode(bio.getvalue()).decode("ascii")


def test_known_good_tonal_scores_higher_than_noise() -> None:
    sr = 22050
    t = np.linspace(0.0, 3.0, int(sr * 3.0), endpoint=False)

    # Known-good fixture: A minor-ish phrase with stable fundamentals and light envelope.
    phrase = (
        0.45 * np.sin(2 * np.pi * 220.0 * t)
        + 0.25 * np.sin(2 * np.pi * 261.63 * t)
        + 0.20 * np.sin(2 * np.pi * 329.63 * t)
    )
    env = np.clip(np.sin(2 * np.pi * 1.0 * t) * 0.5 + 0.6, 0.0, 1.0)
    good = phrase * env

    rng = np.random.default_rng(7)
    noise = rng.normal(0.0, 0.4, size=t.shape).astype(np.float32)

    base_section = {
        "tempo": 90.0,
        "key": "A minor",
        "mode": "minor",
        "beat_grid": [0.0, 0.6667, 1.3333, 2.0, 2.6667],
    }
    good_req = ScoreRequest(
        recording_wav_base64=_wav_b64_from_signal(good, sr),
        recording_mime_type="audio/wav",
        section=base_section,
        skill_nodes=["pitch_accuracy", "phrasing", "timing"],
    )
    noise_req = ScoreRequest(
        recording_wav_base64=_wav_b64_from_signal(noise, sr),
        recording_mime_type="audio/wav",
        section=base_section,
        skill_nodes=["pitch_accuracy", "phrasing", "timing"],
    )

    good_score = score_recording(good_req)
    noise_score = score_recording(noise_req)

    assert good_score.pitch_accuracy > noise_score.pitch_accuracy
    assert good_score.phrasing_score >= 0.0
    assert noise_score.rushing_score >= 0.0


def test_score_response_shape_is_render_safe() -> None:
    sr = 22050
    t = np.linspace(0.0, 1.5, int(sr * 1.5), endpoint=False)
    tone = 0.3 * np.sin(2 * np.pi * 196.0 * t)
    req = ScoreRequest(
        recording_wav_base64=_wav_b64_from_signal(tone, sr),
        recording_mime_type="audio/wav",
        section={"tempo": 80.0, "key": "G major", "beat_grid": [0.0, 0.75, 1.5]},
        skill_nodes=["pitch_accuracy", "phrasing", "timing"],
    )
    res = score_recording(req)
    assert 0.0 <= res.pitch_accuracy <= 1.0
    assert 0.0 <= res.phrasing_score <= 1.0
    assert 0.0 <= res.rushing_score <= 1.0
    assert isinstance(res.note_duration_deltas, list)
    assert isinstance(res.node_scores, dict)
    assert isinstance(res.waveform_comparison.user_wav_base64, str)
    assert isinstance(res.coach_paragraph, str)
    assert res.coach_paragraph.strip() != ""
    assert res.reliability.score_contract_version == "v2"
    assert 0.0 <= res.reliability.signal_quality <= 1.0
    assert isinstance(res.diagnostics.reliability_flags, list)


def test_score_http_contract_and_latency_under_ten_seconds() -> None:
    sr = 22050
    t = np.linspace(0.0, 2.0, int(sr * 2.0), endpoint=False)
    tone = (0.35 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    payload = {
        "recording_wav_base64": _wav_b64_from_signal(tone, sr),
        "recording_mime_type": "audio/wav",
        "section": {
            "tempo": 90.0,
            "key": "A minor",
            "mode": "minor",
            "beat_grid": [0.0, 0.6667, 1.3333],
        },
        "skill_nodes": ["pitch_accuracy", "phrasing", "timing"],
    }
    start = time.perf_counter()
    r = client.post("/score", json=payload)
    elapsed = time.perf_counter() - start
    assert r.status_code == 200, r.text
    body = r.json()
    assert "pitch_accuracy" in body
    assert "phrasing_score" in body
    assert "rushing_score" in body
    assert "node_scores" in body and isinstance(body["node_scores"], dict)
    assert "waveform_comparison" in body and "user_wav_base64" in body["waveform_comparison"]
    assert "reliability" in body and body["reliability"]["score_contract_version"] == "v2"
    assert isinstance(body.get("coach_paragraph"), str)
    assert str(body.get("coach_paragraph", "")).strip() != ""
    assert elapsed < 10.0


def test_score_low_signal_sets_reliability_flags() -> None:
    sr = 22050
    quiet = np.full(int(sr * 2.0), 1e-6, dtype=np.float32)
    req = ScoreRequest(
        recording_wav_base64=_wav_b64_from_signal(quiet, sr),
        recording_mime_type="audio/wav",
        section={"tempo": 80.0, "key": "A minor"},
        skill_nodes=["pitch_accuracy"],
    )
    res = score_recording(req)
    assert "signal_low" in res.reliability.reliability_flags or "signal_near_silence" in res.reliability.reliability_flags
