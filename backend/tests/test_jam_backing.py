"""POST /jam/backing — Gemini/Lyria wiring + fallback (mocked)."""

import base64
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_jam_backing_missing_key_uses_fallback() -> None:
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False),
        patch("app.main.load_bundled_track_wav") as mock_fallback,
    ):
        mock_fallback.return_value = (b"\x10\x20\x30", 24000)
        res = client.post(
            "/jam/backing",
            json={"musical_key": "A minor", "bpm": 72, "weak_areas": ["timing"]},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["format"] == "wav"
    assert body["mime_type"] == "audio/wav"
    assert "fallback_track=" in body["prompt_used"]
    assert base64.b64decode(body["audio_base64"]) == b"\x10\x20\x30"


def test_jam_backing_success_mocked() -> None:
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False),
        patch("app.main.call_gemini_lyria_instrumental", new_callable=AsyncMock) as mock_lyria,
    ):
        mock_lyria.return_value = (b"\x00\x01\x02", 5000)
        res = client.post(
            "/jam/backing",
            json={"musical_key": "G major", "bpm": 80, "weak_areas": ["pitch"]},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["format"] == "wav"
    assert body["mime_type"] == "audio/wav"
    assert body["duration_ms"] == 5000
    assert "instrumental guitar practice backing track" in body["prompt_used"].lower()
    decoded = base64.b64decode(body["audio_base64"])
    assert decoded == b"\x00\x01\x02"


def test_jam_backing_provider_error_falls_back() -> None:
    from app.jam_backing import LyriaProviderError

    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False),
        patch("app.main.call_gemini_lyria_instrumental", new_callable=AsyncMock) as mock_lyria,
        patch("app.main.load_bundled_track_wav") as mock_fallback,
    ):
        mock_lyria.side_effect = LyriaProviderError("rate_limit", "rate limited")
        mock_fallback.return_value = (b"\xaa\xbb", 12000)
        res = client.post(
            "/jam/backing",
            json={"musical_key": "E minor", "bpm": 90, "weak_areas": ["phrasing"]},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["duration_ms"] == 12000
    assert "fallback_track=" in body["prompt_used"]
    assert base64.b64decode(body["audio_base64"]) == b"\xaa\xbb"


def test_parse_lyria_generated_music_payload() -> None:
    from app.jam_backing import _parse_lyria_audio

    raw, ms = _parse_lyria_audio(
        {
            "generatedMusic": {
                "audioBytes": "QUJD",
                "durationMs": 99,
            }
        }
    )
    assert raw == b"ABC"
    assert ms == 99


def test_parse_lyria_missing_audio_raises() -> None:
    from app.jam_backing import LyriaProviderError, _parse_lyria_audio

    with pytest.raises(LyriaProviderError, match="did not include audio"):
        _parse_lyria_audio({"candidates": []})
