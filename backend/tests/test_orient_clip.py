"""Tests for J8: orient clips use the backing provider chain."""
from __future__ import annotations

import pytest

from app import lyria_clip
from app.music_generation.types import GeneratedBacking


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HARMONIQ_SKIP_LYRIA_CLIP", raising=False)
    return tmp_path


def _result(provider: str = "ace_step_modal", used_fallback: bool = False) -> GeneratedBacking:
    return GeneratedBacking(
        wav_bytes=b"RIFFfake",
        duration_ms=8000,
        provider=provider,
        prompt_used="p",
        used_fallback=used_fallback,
        sample_rate=48000,
    )


@pytest.mark.asyncio
async def test_orient_clip_uses_generated_audio(monkeypatch, tmp_path):
    async def fake_generate(_req):
        return _result()

    monkeypatch.setattr("app.music_generation.generate_backing", fake_generate)
    result = await lyria_clip.generate_orient_clip(
        style_label="blues", technique="bends", key="A minor", bpm=70, job_id="job-1"
    )
    assert result["provider"] == "ace_step_modal"
    assert result["used_placeholder"] is False
    assert result["duration"] == 8.0
    assert result["wav_path"] == "data/orient_clips/job-1/orient_clip.wav"
    assert (tmp_path / "orient_clips" / "job-1" / "orient_clip.wav").read_bytes() == b"RIFFfake"


@pytest.mark.asyncio
async def test_orient_clip_marks_bundled_fallback(monkeypatch):
    async def fake_generate(_req):
        return _result(provider="bundled", used_fallback=True)

    monkeypatch.setattr("app.music_generation.generate_backing", fake_generate)
    result = await lyria_clip.generate_orient_clip(
        style_label=None, technique=None, key="G major", bpm=90, job_id="job-2"
    )
    assert result["used_placeholder"] is True
    assert result["placeholder_reason"] == "provider_fallback:bundled"


@pytest.mark.asyncio
async def test_orient_clip_falls_back_to_placeholder_on_failure(monkeypatch):
    async def fake_generate(_req):
        raise RuntimeError("chain down")

    monkeypatch.setattr("app.music_generation.generate_backing", fake_generate)
    result = await lyria_clip.generate_orient_clip(
        style_label=None, technique=None, key="A minor", bpm=70, job_id="job-3"
    )
    assert result["used_placeholder"] is True
    assert result["placeholder_reason"].startswith("generation_failed:")
    assert result["duration"] == 30


@pytest.mark.asyncio
async def test_orient_clip_skip_env_still_uses_placeholder(monkeypatch):
    monkeypatch.setenv("HARMONIQ_SKIP_LYRIA_CLIP", "1")
    result = await lyria_clip.generate_orient_clip(
        style_label=None, technique=None, key=None, bpm=None, job_id="job-4"
    )
    assert result["used_placeholder"] is True
    assert result["placeholder_reason"] == "HARMONIQ_SKIP_LYRIA_CLIP=1"
