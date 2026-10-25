"""Tests for Commit 171: landmark audio fingerprinting."""

from __future__ import annotations

import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf

from app.audio_fingerprint import (
    FINGERPRINT_MIN_MATCHED_HASHES,
    FINGERPRINT_SIMILARITY_THRESHOLD,
    AudioFingerprint,
    compare_fingerprints,
    compute_fingerprint,
)

SR = 22050
HOP = 256


def _melody(
    duration_seconds: float = 12.0,
    notes: tuple[float, ...] = (220.0, 246.94, 261.63, 329.63, 293.66, 349.23),
) -> np.ndarray:
    t = np.arange(int(SR * duration_seconds)) / SR
    samples = np.zeros_like(t)
    note_seconds = 0.75
    note_count = int(duration_seconds / note_seconds)
    for index in range(note_count):
        start = int(index * note_seconds * SR)
        end = int(min((index + 1) * note_seconds, duration_seconds) * SR)
        frequency = notes[index % len(notes)]
        local = t[start:end] - t[start]
        envelope = np.minimum(
            1.0,
            np.minimum(
                local / 0.02,
                (local[-1] - local) / 0.05 if local.size > 1 else np.ones_like(local),
            ),
        )
        samples[start:end] = envelope * (
            0.5 * np.sin(2 * np.pi * frequency * local)
            + 0.3 * np.sin(2 * np.pi * 2 * frequency * local)
            + 0.15 * np.sin(2 * np.pi * 3 * frequency * local)
        )
    samples += 1e-4 * np.random.default_rng(0).standard_normal(samples.size)
    return samples


def _write(path, samples: np.ndarray) -> None:
    sf.write(str(path), samples.astype(np.float32), SR, subtype="PCM_16")


def _encode_mp3(wav_path, mp3_path) -> None:
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


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not available")
def test_reencoded_copy_matches(tmp_path):
    wav_path = tmp_path / "song.wav"
    mp3_path = tmp_path / "song.mp3"
    _write(wav_path, _melody())
    _encode_mp3(wav_path, mp3_path)

    similarity, matched = compare_fingerprints(
        compute_fingerprint(wav_path),
        compute_fingerprint(mp3_path),
    )

    assert matched >= FINGERPRINT_MIN_MATCHED_HASHES
    assert similarity >= FINGERPRINT_SIMILARITY_THRESHOLD


def test_hop_aligned_trim_matches(tmp_path):
    samples = _melody()
    full_path = tmp_path / "full.wav"
    trim_path = tmp_path / "trim.wav"
    _write(full_path, samples)

    start = int(2 * SR / HOP) * HOP
    end = int(10 * SR / HOP) * HOP
    _write(trim_path, samples[start:end])

    similarity, matched = compare_fingerprints(
        compute_fingerprint(full_path),
        compute_fingerprint(trim_path),
    )

    assert matched >= FINGERPRINT_MIN_MATCHED_HASHES
    assert similarity >= 0.5


def test_different_melody_does_not_match(tmp_path):
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    _write(first, _melody())
    _write(
        second,
        _melody(notes=(392.0, 440.0, 493.88, 523.25, 587.33, 659.25)),
    )

    similarity, matched = compare_fingerprints(
        compute_fingerprint(first),
        compute_fingerprint(second),
    )

    assert matched < FINGERPRINT_MIN_MATCHED_HASHES
    assert similarity < FINGERPRINT_SIMILARITY_THRESHOLD


def test_empty_audio_has_no_hashes(tmp_path):
    path = tmp_path / "silence.wav"
    _write(path, np.zeros(int(SR * 2), dtype=np.float32))

    fingerprint = compute_fingerprint(path)

    assert fingerprint.hashes.size == 0
    assert fingerprint.times.size == 0


def test_payload_round_trip():
    fingerprint = AudioFingerprint(
        hashes=np.asarray([1, 2, 3], dtype=np.uint32),
        times=np.asarray([4, 5, 6], dtype=np.uint32),
    )

    restored = AudioFingerprint.from_payload(fingerprint.to_payload())

    assert np.array_equal(restored.hashes, fingerprint.hashes)
    assert np.array_equal(restored.times, fingerprint.times)
    assert restored.version == fingerprint.version
