"""Compact landmark audio fingerprinting for near-duplicate cache lookup.

Implements the dejavu/audfprint idea without a new system dependency:
spectrogram peaks -> paired hashes -> time-offset voting. Hashes are robust
to lossy re-encoding and trimmed copies of the same recording.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy.ndimage import maximum_filter
from scipy.signal import resample_poly, stft

logger = logging.getLogger("harmoniq.audio_fingerprint")

FINGERPRINT_VERSION = 1

# Must match the cache/sidecar algorithm version; bump when tuning changes.
FP_SAMPLE_RATE = 11025
FP_N_FFT = 512
FP_HOP_LENGTH = 256
FP_PEAK_DB = -55.0
FP_PEAK_NEIGHBORHOOD = 5
FP_PEAKS_PER_FRAME = 5
FP_FANOUT = 3
FP_MAX_DELTA_FRAMES = 8
FP_MAX_DELTA_BINS = 64
FP_HASH_BITS = 10

FINGERPRINT_SIMILARITY_THRESHOLD = 0.30
FINGERPRINT_MIN_MATCHED_HASHES = 20


@dataclass(frozen=True)
class AudioFingerprint:
    """Compact landmark fingerprint: paired hashes plus their first-peak time."""

    hashes: np.ndarray
    times: np.ndarray
    version: int = FINGERPRINT_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": int(self.version),
            "hashes": [int(value) for value in self.hashes],
            "times": [int(value) for value in self.times],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> AudioFingerprint:
        version = int(payload.get("version", 0))
        hashes = np.asarray(payload.get("hashes") or [], dtype=np.uint32)
        times = np.asarray(payload.get("times") or [], dtype=np.uint32)
        if hashes.shape != times.shape:
            raise ValueError("Fingerprint hash/time length mismatch")
        return cls(hashes=hashes, times=times, version=version)


def _select_peaks(spectrogram_db: np.ndarray) -> list[tuple[int, int]]:
    neighborhood_max = maximum_filter(
        spectrogram_db,
        size=(FP_PEAK_NEIGHBORHOOD, FP_PEAK_NEIGHBORHOOD),
        mode="constant",
        cval=-np.inf,
    )
    mask = (spectrogram_db == neighborhood_max) & (spectrogram_db > FP_PEAK_DB)

    rows, cols = np.nonzero(mask)
    by_frame: dict[int, list[int]] = {}
    for row, col in zip(rows.tolist(), cols.tolist()):
        by_frame.setdefault(int(col), []).append(int(row))

    peaks: list[tuple[int, int]] = []
    for frame, bins in by_frame.items():
        if len(bins) > FP_PEAKS_PER_FRAME:
            bins = sorted(
                bins,
                key=lambda bin_index: float(spectrogram_db[bin_index, frame]),
                reverse=True,
            )[:FP_PEAKS_PER_FRAME]
        peaks.extend((frame, bin_index) for bin_index in bins)
    peaks.sort()
    return peaks


def _pair_hashes(peaks: list[tuple[int, int]]) -> tuple[np.ndarray, np.ndarray]:
    hashes: list[int] = []
    times: list[int] = []
    mask = (1 << FP_HASH_BITS) - 1

    for index, (frame, bin_index) in enumerate(peaks):
        fanout = 0
        later_index = index + 1
        while later_index < len(peaks):
            later_frame, later_bin = peaks[later_index]
            later_index += 1
            delta_frames = later_frame - frame
            if delta_frames > FP_MAX_DELTA_FRAMES:
                break
            if delta_frames < 1:
                continue
            if abs(later_bin - bin_index) > FP_MAX_DELTA_BINS:
                continue
            packed = (
                ((bin_index & mask) << 22)
                | ((later_bin & mask) << 12)
                | (delta_frames & 0x1F)
            )
            hashes.append(packed)
            times.append(frame)
            fanout += 1
            if fanout >= FP_FANOUT:
                break

    if not hashes:
        return np.empty(0, dtype=np.uint32), np.empty(0, dtype=np.uint32)
    return (
        np.asarray(hashes, dtype=np.uint32),
        np.asarray(times, dtype=np.uint32),
    )


def compute_fingerprint(path: Path) -> AudioFingerprint:
    """Compute a landmark fingerprint for a normalized WAV file."""
    # Read with soundfile and resample explicitly: ``librosa.load``'s default
    # resampler can trigger a one-time numba JIT cost (~20s) in a fresh worker.
    samples, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
    if samples.size == 0:
        logger.warning("fingerprint skipped: empty audio path=%s", path)
        return AudioFingerprint(
            hashes=np.empty(0, dtype=np.uint32),
            times=np.empty(0, dtype=np.uint32),
        )
    samples = samples.mean(axis=1)
    if sample_rate != FP_SAMPLE_RATE:
        divisor = math.gcd(int(sample_rate), FP_SAMPLE_RATE)
        samples = resample_poly(
            samples,
            FP_SAMPLE_RATE // divisor,
            int(sample_rate) // divisor,
        ).astype(np.float32, copy=False)

    # scipy's STFT avoids librosa's numba JIT warm-up (~15s in a fresh worker).
    _, _, spectrum = stft(
        samples,
        fs=FP_SAMPLE_RATE,
        window="hann",
        nperseg=FP_N_FFT,
        noverlap=FP_N_FFT - FP_HOP_LENGTH,
        nfft=FP_N_FFT,
        boundary=None,
        padded=False,
    )
    magnitude = np.abs(spectrum)
    if magnitude.size == 0:
        return AudioFingerprint(
            hashes=np.empty(0, dtype=np.uint32),
            times=np.empty(0, dtype=np.uint32),
        )

    reference = float(magnitude.max())
    if reference <= 0.0:
        return AudioFingerprint(
            hashes=np.empty(0, dtype=np.uint32),
            times=np.empty(0, dtype=np.uint32),
        )
    spectrogram_db = 20.0 * np.log10(
        np.maximum(magnitude, reference * 1e-10) / reference
    )
    peaks = _select_peaks(spectrogram_db)
    hashes, times = _pair_hashes(peaks)
    return AudioFingerprint(hashes=hashes, times=times)


def compare_fingerprints(
    query: AudioFingerprint,
    candidate: AudioFingerprint,
) -> tuple[float, int]:
    """Return ``(similarity, matched_hashes)`` using time-offset voting."""
    if query.hashes.size == 0 or candidate.hashes.size == 0:
        return 0.0, 0

    candidate_index: dict[int, list[int]] = {}
    for hash_value, time_value in zip(
        candidate.hashes.tolist(), candidate.times.tolist()
    ):
        candidate_index.setdefault(int(hash_value), []).append(int(time_value))

    delta_counts: dict[int, int] = {}
    for hash_value, time_value in zip(query.hashes.tolist(), query.times.tolist()):
        for candidate_time in candidate_index.get(int(hash_value), ()):
            delta = candidate_time - int(time_value)
            delta_counts[delta] = delta_counts.get(delta, 0) + 1

    if not delta_counts:
        return 0.0, 0

    matched = max(delta_counts.values())
    denominator = min(int(query.hashes.size), int(candidate.hashes.size))
    similarity = float(matched) / float(denominator) if denominator else 0.0
    return similarity, int(matched)
