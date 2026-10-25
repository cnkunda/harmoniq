"""Tests for Commit 171: fingerprint cache lookup and quality gate wiring."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
import soundfile as sf

from app.audio_processing import AudioPreparationResult
from app.audio_quality import AUDIO_QUALITY_LOW_USER_MESSAGE, AudioQualityTooLowError
from app.cache import (
    CacheLookupResult,
    cache_key_for_wav_and_profile,
    invalidate_cache_for_wav,
    lookup_cached_lesson,
    save_cached_lesson_for_wav,
)
from app.schemas import AudioQuality, LessonJSON, PlayerProfile


def _write_wav_stub(path: Path, payload: bytes = b"RIFFstub-audio") -> None:
    path.write_bytes(payload)


def _fake_fingerprint():
    from app.audio_fingerprint import AudioFingerprint

    return AudioFingerprint(
        hashes=np.asarray([11, 22, 33], dtype=np.uint32),
        times=np.asarray([0, 1, 2], dtype=np.uint32),
    )


def _write_melody(path: Path, *, duration_seconds: float = 12.0) -> None:
    sample_rate = 22050
    t = np.arange(int(sample_rate * duration_seconds)) / sample_rate
    notes = (220.0, 246.94, 261.63, 329.63, 293.66, 349.23)
    samples = np.zeros_like(t)
    note_seconds = 0.75
    for index in range(int(duration_seconds / note_seconds)):
        start = int(index * note_seconds * sample_rate)
        end = int(min((index + 1) * note_seconds, duration_seconds) * sample_rate)
        frequency = notes[index % len(notes)]
        local = t[start:end] - t[start]
        envelope = np.minimum(1.0, np.minimum(local / 0.02, (local[-1] - local) / 0.05))
        samples[start:end] = envelope * (
            0.5 * np.sin(2 * np.pi * frequency * local)
            + 0.3 * np.sin(2 * np.pi * 2 * frequency * local)
            + 0.15 * np.sin(2 * np.pi * 3 * frequency * local)
        )
    samples += 1e-4 * np.random.default_rng(0).standard_normal(samples.size)
    sf.write(str(path), samples.astype(np.float32), sample_rate, subtype="PCM_16")


def _rejected_quality() -> AudioQuality:
    return AudioQuality(
        snr_db=0.0,
        clipping_ratio=0.25,
        silence_ratio=0.0,
        peak_dbfs=0.0,
        score=0.1,
        flags=["clipping", "low_snr"],
        acceptable=False,
    )


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    resolved = tmp_path / f".tmp_test_data_{uuid4()}"
    resolved.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(resolved))
    return resolved


def test_sha_hit_does_not_compute_fingerprint(data_dir, monkeypatch):
    wav_path = data_dir / "song.wav"
    _write_wav_stub(wav_path)
    lesson = LessonJSON(job_id="sha", style_label="general")
    save_cached_lesson_for_wav(wav_path, lesson)

    def _boom(_path):
        raise AssertionError("fingerprint must not run on a SHA hit")

    monkeypatch.setattr("app.audio_fingerprint.compute_fingerprint", _boom)

    result = lookup_cached_lesson(wav_path)

    assert result.kind == "sha_hit"
    assert result.lesson is not None
    assert result.lesson.job_id == "sha"
    assert result.fingerprint is None


def test_fingerprint_hit_reuses_cached_lesson(data_dir, monkeypatch):
    source = data_dir / "source.wav"
    query = data_dir / "query.wav"
    _write_wav_stub(source, b"RIFFsource")
    _write_wav_stub(query, b"RIFFdifferent-encoding")
    lesson = LessonJSON(job_id="fingerprint", style_label="general")
    fingerprint = _fake_fingerprint()
    save_cached_lesson_for_wav(source, lesson, fingerprint=fingerprint)

    monkeypatch.setattr("app.audio_fingerprint.compute_fingerprint", lambda _path: fingerprint)
    monkeypatch.setattr(
        "app.audio_fingerprint.compare_fingerprints",
        lambda _query, _candidate: (0.9, 100),
    )

    result = lookup_cached_lesson(query)

    assert result.kind == "fingerprint_hit"
    assert result.lesson is not None
    assert result.lesson.job_id == "fingerprint"
    assert result.similarity == pytest.approx(0.9)
    assert result.matched_hashes == 100


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not available")
def test_real_fingerprint_cache_hit_across_encodings(data_dir):
    from app.audio_fingerprint import compute_fingerprint

    wav_path = data_dir / "song.wav"
    mp3_path = data_dir / "song.mp3"
    _write_melody(wav_path)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(wav_path),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(mp3_path),
        ],
        check=True,
    )
    lesson = LessonJSON(job_id="real-fingerprint", style_label="general")
    save_cached_lesson_for_wav(
        wav_path,
        lesson,
        fingerprint=compute_fingerprint(wav_path),
    )

    result = lookup_cached_lesson(mp3_path)

    assert result.kind == "fingerprint_hit"
    assert result.lesson is not None
    assert result.lesson.job_id == "real-fingerprint"


def test_fingerprint_lookup_is_profile_scoped(data_dir, monkeypatch):
    source = data_dir / "source.wav"
    query = data_dir / "query.wav"
    _write_wav_stub(source, b"RIFFsource")
    _write_wav_stub(query, b"RIFFdifferent-encoding")
    fingerprint = _fake_fingerprint()
    save_cached_lesson_for_wav(
        source,
        LessonJSON(job_id="profile-a", style_label="general"),
        player_profile=PlayerProfile(weak_areas=["bending"]),
        fingerprint=fingerprint,
    )

    monkeypatch.setattr("app.audio_fingerprint.compute_fingerprint", lambda _path: fingerprint)
    monkeypatch.setattr(
        "app.audio_fingerprint.compare_fingerprints",
        lambda _query, _candidate: (0.99, 100),
    )

    result = lookup_cached_lesson(
        query,
        player_profile=PlayerProfile(weak_areas=["timing"]),
    )

    assert result.kind == "miss"
    assert result.lesson is None


def test_fingerprint_failure_falls_back_to_miss(data_dir, monkeypatch):
    wav_path = data_dir / "song.wav"
    _write_wav_stub(wav_path)

    def _boom(_path):
        raise RuntimeError("forced fingerprint failure")

    monkeypatch.setattr("app.audio_fingerprint.compute_fingerprint", _boom)

    result = lookup_cached_lesson(wav_path)

    assert result.kind == "miss"
    assert result.lesson is None
    assert result.fingerprint is None


def test_invalidation_removes_fingerprint_sidecar(data_dir):
    wav_path = data_dir / "song.wav"
    _write_wav_stub(wav_path)
    save_cached_lesson_for_wav(
        wav_path, LessonJSON(job_id="sidecar", style_label="general"), fingerprint=_fake_fingerprint()
    )
    key = cache_key_for_wav_and_profile(wav_path, None)
    sidecar = Path(str(data_dir / "cache" / "analysis")) / (
        key.translate(str.maketrans({":": "__", "|": "__"})) + ".fingerprint.json"
    )
    assert sidecar.exists()

    assert invalidate_cache_for_wav(wav_path) is True
    assert not sidecar.exists()


def test_cache_lookup_metric_is_incremented(data_dir):
    prometheus_client = pytest.importorskip("prometheus_client")
    wav_path = data_dir / "song.wav"
    _write_wav_stub(wav_path)
    save_cached_lesson_for_wav(wav_path, LessonJSON(job_id="metric", style_label="general"))

    before = (
        prometheus_client.REGISTRY.get_sample_value(
            "harmoniq_analysis_cache_lookups_total", {"result": "sha_hit"}
        )
        or 0.0
    )
    lookup_cached_lesson(wav_path)
    after = (
        prometheus_client.REGISTRY.get_sample_value(
            "harmoniq_analysis_cache_lookups_total", {"result": "sha_hit"}
        )
        or 0.0
    )

    assert after == before + 1


def test_prepare_pipeline_gates_before_demucs(data_dir, monkeypatch):
    from app.routers import analyze as analyze_router

    prepared = AudioPreparationResult(
        job_id="prepare-gate",
        job_dir=data_dir,
        normalized_wav_path=data_dir / "song.wav",
        source_metadata=None,
        duration_seconds=10.0,
        quality=_rejected_quality(),
    )
    separate_calls = {"count": 0}

    def _fake_separate(*_args, **_kwargs):
        separate_calls["count"] += 1
        return {}

    monkeypatch.setattr(analyze_router, "prepare_audio_input", lambda *_a, **_k: prepared)
    monkeypatch.setattr(analyze_router, "separate_with_demucs", _fake_separate)

    with pytest.raises(AudioQualityTooLowError):
        analyze_router._run_transcription_prepare_pipeline(
            job_id="prepare-gate",
            youtube_url=None,
            upload_path=str(data_dir / "input.wav"),
            time_signature_override=None,
            bpm_override=None,
        )

    assert separate_calls["count"] == 0


def test_worker_rejects_low_quality_after_cache_miss(data_dir, monkeypatch):
    from app import jobs as jobs_mod

    wav_path = data_dir / "song.wav"
    _write_wav_stub(wav_path)
    prepared = AudioPreparationResult(
        job_id="quality-gate",
        job_dir=data_dir,
        normalized_wav_path=wav_path,
        source_metadata=None,
        duration_seconds=10.0,
        quality=_rejected_quality(),
    )
    separate_calls = {"count": 0}

    def _fake_separate(*_args, **_kwargs):
        separate_calls["count"] += 1
        return {}

    monkeypatch.setattr(jobs_mod, "prepare_audio_input", lambda *_a, **_k: prepared)
    monkeypatch.setattr(
        jobs_mod,
        "lookup_cached_lesson",
        lambda *_a, **_k: CacheLookupResult(None, "miss", 0.0, 0, None, None),
    )
    monkeypatch.setattr(jobs_mod, "separate_song_to_stems", _fake_separate)
    monkeypatch.setattr(jobs_mod, "PROCESSING_SLEEP_SECONDS", 0.0)
    jobs_mod.jobs.clear()

    jobs_mod._process_analyze_job("quality-gate", youtube_url=None, upload_path=str(wav_path))

    status = jobs_mod.jobs["quality-gate"]
    assert status.status == "failed"
    assert status.error_code == "audio_quality_low"
    assert status.error == AUDIO_QUALITY_LOW_USER_MESSAGE
    assert separate_calls["count"] == 0
    jobs_mod.jobs.clear()
