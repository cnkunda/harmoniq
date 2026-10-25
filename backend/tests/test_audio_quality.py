"""Tests for Commit 171: ingest-time audio quality scoring."""

from __future__ import annotations

import shutil

import numpy as np
import pytest
import soundfile as sf

from app.audio_quality import (
    CLIP_RATIO_REJECT,
    AudioQualityTooLowError,
    analyze_audio_quality,
    require_acceptable_quality,
)

SR = 22050


def _write_signal(path, samples: np.ndarray, *, sr: int = SR) -> None:
    sf.write(str(path), samples.astype(np.float32), sr, subtype="PCM_16")


def _tone(duration_seconds: float = 4.0, amplitude: float = 0.25) -> np.ndarray:
    t = np.arange(int(SR * duration_seconds)) / SR
    # A realistic note-like swell keeps the percentile SNR proxy meaningful;
    # a mathematically constant tone has no dynamic range to estimate from.
    envelope = 0.15 + 0.85 * np.abs(np.sin(2 * np.pi * 0.7 * t)) ** 2
    return envelope * (
        amplitude * np.sin(2 * np.pi * 220.0 * t)
        + 0.5 * amplitude * np.sin(2 * np.pi * 440.0 * t)
        + 0.25 * amplitude * np.sin(2 * np.pi * 660.0 * t)
    )


def test_clean_audio_is_accepted(tmp_path):
    path = tmp_path / "clean.wav"
    _write_signal(path, _tone())

    quality = analyze_audio_quality(path)

    assert quality.acceptable is True
    assert quality.clipping_ratio < CLIP_RATIO_REJECT
    assert quality.silence_ratio < 0.5
    assert quality.score >= 0.35


def test_clipped_audio_is_rejected(tmp_path):
    path = tmp_path / "clipped.wav"
    _write_signal(path, np.clip(2.0 * _tone(amplitude=1.0), -1.0, 1.0))

    quality = analyze_audio_quality(path)

    assert quality.acceptable is False
    assert "clipping" in quality.flags
    assert quality.clipping_ratio > CLIP_RATIO_REJECT


def test_near_silent_audio_is_rejected(tmp_path):
    path = tmp_path / "silent.wav"
    rng = np.random.default_rng(0)
    _write_signal(path, 1e-6 * rng.standard_normal(int(SR * 4)))

    quality = analyze_audio_quality(path)

    assert quality.acceptable is False
    assert quality.silence_ratio > 0.9


def test_require_acceptable_quality_raises_for_rejected_snapshot(tmp_path):
    path = tmp_path / "clipped.wav"
    _write_signal(path, np.clip(2.0 * _tone(amplitude=1.0), -1.0, 1.0))
    quality = analyze_audio_quality(path)

    with pytest.raises(AudioQualityTooLowError):
        require_acceptable_quality(quality)


def test_quality_gate_can_be_skipped(tmp_path, monkeypatch):
    path = tmp_path / "clipped.wav"
    _write_signal(path, np.clip(2.0 * _tone(amplitude=1.0), -1.0, 1.0))
    quality = analyze_audio_quality(path)
    monkeypatch.setenv("HARMONIQ_SKIP_AUDIO_QUALITY_GATE", "1")

    require_acceptable_quality(quality)


def test_ingest_returns_quality_snapshot(tmp_path, monkeypatch):
    from app.ingest import ingest_youtube_or_upload_to_wav

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setattr("app.ingest.MIN_ANALYZE_DURATION_SECONDS", 0.01)
    upload = data_dir / "input.wav"
    _write_signal(upload, _tone())

    wav_path, metadata, quality = ingest_youtube_or_upload_to_wav(
        "quality-ingest",
        youtube_url=None,
        upload_path=str(upload),
    )

    assert wav_path.exists()
    assert wav_path.name == "song.wav"
    assert metadata is None
    assert quality.acceptable is True
    assert quality.score > 0.0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not available")
def test_ffmpeg_fallback_decodes_when_soundfile_fails(tmp_path, monkeypatch):
    path = tmp_path / "clean.wav"
    _write_signal(path, _tone())

    def _boom(_path):
        raise RuntimeError("forced soundfile failure")

    monkeypatch.setattr("app.audio_quality._analyze_with_soundfile", _boom)
    quality = analyze_audio_quality(path)

    assert quality.acceptable is True
    assert quality.score > 0.0
