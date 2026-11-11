"""POST /jam/backing — provider-chain plumbing and provenance (mocked at the seam)."""

import base64
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.music_generation import GeneratedBacking

client = TestClient(app)


def _result(
    wav: bytes,
    *,
    provider: str,
    used_fallback: bool = False,
    fallback_reason: str | None = None,
    duration_ms: int = 24000,
    prompt_used: str = "Instrumental guitar practice backing track, Key: A minor",
) -> GeneratedBacking:
    return GeneratedBacking(
        wav_bytes=wav,
        duration_ms=duration_ms,
        provider=provider,
        prompt_used=prompt_used,
        used_fallback=used_fallback,
        fallback_reason=fallback_reason,
        sample_rate=44100,
        attempts=[],
    )


def test_jam_backing_bundled_fallback_reports_provenance() -> None:
    with patch("app.main.generate_backing", new=AsyncMock()) as mock_generate:
        mock_generate.return_value = _result(
            b"\x10\x20\x30",
            provider="bundled",
            used_fallback=True,
            fallback_reason="ace_step_modal:unavailable;mrt2:unavailable",
            prompt_used="Instrumental bed, Key: A minor [fallback_track=a-minor-blues.mp3]",
        )
        res = client.post(
            "/jam/backing",
            json={"musical_key": "A minor", "bpm": 72, "weak_areas": ["timing"]},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["format"] == "wav"
    assert body["mime_type"] == "audio/wav"
    assert body["provider"] == "bundled"
    assert body["used_fallback"] is True
    assert body["fallback_reason"].startswith("ace_step_modal")
    assert "fallback_track=" in body["prompt_used"]
    assert base64.b64decode(body["audio_base64"]) == b"\x10\x20\x30"


def test_jam_backing_success_reports_provider() -> None:
    with patch("app.main.generate_backing", new=AsyncMock()) as mock_generate:
        mock_generate.return_value = _result(
            b"\x00\x01\x02\x03",
            provider="mrt2",
            duration_ms=5000,
            prompt_used="fingerpicking, Key: G major",
        )
        res = client.post(
            "/jam/backing",
            json={"musical_key": "G major", "bpm": 80, "style_hint": "fingerpicking"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["provider"] == "mrt2"
    assert body["used_fallback"] is False
    assert body["duration_ms"] == 5000
    assert "Key: G major" in body["prompt_used"]
    assert base64.b64decode(body["audio_base64"]) == b"\x00\x01\x02\x03"


def test_jam_backing_chain_failure_returns_503() -> None:
    with patch("app.main.generate_backing", new=AsyncMock()) as mock_generate:
        mock_generate.side_effect = RuntimeError("No backing provider succeeded: mrt2:timeout")
        res = client.post("/jam/backing", json={"musical_key": "E minor", "bpm": 90})
    assert res.status_code == 503
    assert "No backing provider succeeded" in res.json()["detail"]


def test_build_mrt2_prompt_includes_key_tempo_and_weak_areas() -> None:
    from app.jam_backing import build_mrt2_prompt

    prompt = build_mrt2_prompt(
        style_hint="blues shuffle",
        musical_key="A minor",
        bpm=70,
        weak_areas=["phrasing", "bends"],
        chord_progression=["A7", "D7", "E7"],
    )
    assert "blues shuffle" in prompt
    assert "Key: A minor" in prompt
    assert "70 BPM" in prompt
    assert "Focus areas: phrasing, bends" in prompt
    assert "Chord progression: A7, D7, E7" in prompt


def test_build_mrt2_prompt_no_bpm() -> None:
    from app.jam_backing import build_mrt2_prompt

    prompt = build_mrt2_prompt(style_hint="ambient drone", musical_key="A minor", bpm=None)
    assert "BPM" not in prompt
    assert "ambient drone" in prompt
