"""POST /jam/backing — MRT2 generation + bundled fallback (mocked)."""

import base64
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_jam_backing_mrt2_unavailable_uses_fallback() -> None:
    with patch("app.main.Mrt2BackingGenerator") as mock_cls:
        mock_instance = mock_cls.return_value
        mock_instance.generate.return_value = None
        with patch("app.main.load_bundled_track_wav") as mock_fallback:
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
    mock_wav = b"\x00\x01\x02\x03"
    with patch("app.main.Mrt2BackingGenerator") as mock_cls:
        mock_instance = mock_cls.return_value
        mock_instance.generate.return_value = (mock_wav, 5000)
        res = client.post(
            "/jam/backing",
            json={"musical_key": "G major", "bpm": 80, "style_hint": "fingerpicking"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["format"] == "wav"
    assert body["mime_type"] == "audio/wav"
    assert body["duration_ms"] == 5000
    assert "Key: G major" in body["prompt_used"]
    decoded = base64.b64decode(body["audio_base64"])
    assert decoded == mock_wav


def test_jam_backing_mrt2_error_falls_back() -> None:
    with patch("app.main.Mrt2BackingGenerator") as mock_cls:
        mock_instance = mock_cls.return_value
        mock_instance.generate.return_value = None
        with patch("app.main.load_bundled_track_wav") as mock_fallback:
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


def test_build_mrt2_prompt_includes_key_and_tempo() -> None:
    from app.jam_backing import build_mrt2_prompt

    prompt = build_mrt2_prompt(style_hint="blues shuffle", musical_key="A minor", bpm=70)
    assert "blues shuffle" in prompt
    assert "Key: A minor" in prompt
    assert "70 BPM" in prompt


def test_build_mrt2_prompt_no_bpm() -> None:
    from app.jam_backing import build_mrt2_prompt

    prompt = build_mrt2_prompt(style_hint="ambient drone", musical_key="A minor", bpm=None)
    assert "BPM" not in prompt
    assert "ambient drone" in prompt
