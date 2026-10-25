"""Ingest-time audio quality assessment (Commit 171).

Computes a lightweight, reference-free quality snapshot before normalization:
signal-to-noise proxy, clipping ratio, silence ratio, and a 0-1 score.

Metrics are intentionally heuristic. They are used to reject clearly unusable
uploads early; they are not calibrated probabilities.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from app.pipeline_proof import TARGET_SR
from app.schemas import AudioQuality

logger = logging.getLogger("harmoniq.audio_quality")

# Must match `README_ERROR_COPY.audioQualityLow` on the client.
AUDIO_QUALITY_LOW_USER_MESSAGE = (
    "That recording is too noisy or distorted to transcribe reliably. "
    "Try a cleaner take or a studio recording."
)

# Conservative gate thresholds. These pass the repo's real smoke mixes
# (SNR proxy 4.8-14.2 dB, clipping ~0, silence <= 0.01).
CLIP_SAMPLE_THRESHOLD = 0.999
CLIP_RUN_MIN = 3
CLIP_RATIO_REJECT = 0.01
SILENCE_RMS_THRESHOLD = 1e-4
SILENCE_RATIO_REJECT = 0.90
SNR_DB_REJECT = 3.0
QUALITY_SCORE_REJECT = 0.35

_RMS_EPS = 1e-6
_RMS_FRAME_SECONDS = 0.05
_QUALITY_BLOCK_FRAMES = 65536


class AudioQualityAnalysisError(RuntimeError):
    """Raised when source audio cannot be decoded for quality assessment."""


class AudioQualityTooLowError(RuntimeError):
    """Raised when a source fails the ingest quality gate."""


def _run_lengths(mask: np.ndarray) -> np.ndarray:
    """Return lengths of consecutive True runs in a 1-D boolean array."""
    if mask.size == 0:
        return np.empty(0, dtype=np.int64)
    padded = np.concatenate(([False], mask, [False]))
    changes = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)
    return ends - starts


class _QualityAccumulator:
    """Streaming quality accumulator; avoids loading long sources into memory."""

    def __init__(self, sample_rate: int) -> None:
        if sample_rate <= 0:
            raise AudioQualityAnalysisError("Invalid sample rate for quality analysis")
        self.sample_rate = sample_rate
        self.frame_size = max(1, int(sample_rate * _RMS_FRAME_SECONDS))
        self._tail = np.empty(0, dtype=np.float32)
        self._clip_run_carry = np.zeros(0, dtype=np.int64)
        self._rms_frames: list[np.ndarray] = []
        self._clipped_samples = 0
        self._total_samples = 0
        self._peak = 0.0
        self._long_clip = False

    def add_block(self, block: np.ndarray) -> None:
        if block.ndim == 1:
            block = block[:, None]
        if block.size == 0:
            return
        block = np.asarray(block, dtype=np.float32)
        if not np.all(np.isfinite(block)):
            logger.warning("non-finite audio samples during quality analysis; sanitizing")
            block = np.nan_to_num(block, nan=0.0, posinf=1.0, neginf=-1.0)
        channels = block.shape[1]
        if self._clip_run_carry.size != channels:
            self._clip_run_carry = np.zeros(channels, dtype=np.int64)

        abs_block = np.abs(block)
        block_peak = float(abs_block.max()) if abs_block.size else 0.0
        if block_peak > self._peak:
            self._peak = block_peak

        self._total_samples += int(block.size)
        self._clipped_samples += int(np.count_nonzero(abs_block >= CLIP_SAMPLE_THRESHOLD))

        for ch in range(channels):
            mask = abs_block[:, ch] >= CLIP_SAMPLE_THRESHOLD
            runs = _run_lengths(mask)
            if runs.size == 0:
                self._clip_run_carry[ch] = 0
                continue
            if mask[0] and self._clip_run_carry[ch] > 0:
                runs = runs.copy()
                runs[0] += int(self._clip_run_carry[ch])
            if int(runs.max()) >= CLIP_RUN_MIN:
                self._long_clip = True
            self._clip_run_carry[ch] = int(runs[-1]) if mask[-1] else 0

        mono = block.mean(axis=1) if channels > 1 else block[:, 0]
        buf = np.concatenate((self._tail, mono)) if self._tail.size else mono
        full_frames = buf.size // self.frame_size
        if full_frames:
            frames = buf[: full_frames * self.frame_size].reshape(full_frames, self.frame_size)
            self._rms_frames.append(np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1)))
            self._tail = buf[full_frames * self.frame_size :].copy()
        else:
            self._tail = buf.copy()

    def finish(self) -> AudioQuality:
        if self._tail.size:
            self._rms_frames.append(
                np.array([float(np.sqrt(np.mean(self._tail.astype(np.float64) ** 2)))])
            )
        rms = np.concatenate(self._rms_frames) if self._rms_frames else np.empty(0)

        clipping_ratio = (
            float(self._clipped_samples) / float(self._total_samples)
            if self._total_samples > 0
            else 1.0
        )
        silence_ratio = (
            float(np.mean(rms < SILENCE_RMS_THRESHOLD)) if rms.size else 1.0
        )

        snr_db = 0.0
        if rms.size >= 3:
            non_silent = rms[rms > _RMS_EPS]
            if non_silent.size >= 3:
                noise_floor = float(np.percentile(non_silent, 10))
                signal_level = float(np.percentile(rms, 90))
                if noise_floor > 0 and signal_level > 0:
                    snr_db = 20.0 * float(np.log10(signal_level / noise_floor))
        snr_db = float(np.clip(snr_db, -20.0, 80.0))

        peak_dbfs = 20.0 * float(np.log10(max(self._peak, 1e-12)))
        peak_dbfs = float(np.clip(peak_dbfs, -120.0, 20.0))

        snr_component = float(np.clip(snr_db / 20.0, 0.0, 1.0))
        clip_component = 1.0 - float(np.clip(clipping_ratio / 0.05, 0.0, 1.0))
        silence_component = 1.0 - float(np.clip(silence_ratio, 0.0, 1.0))
        score = float(np.clip(0.5 * snr_component + 0.3 * clip_component + 0.2 * silence_component, 0.0, 1.0))

        flags: list[str] = []
        if clipping_ratio > CLIP_RATIO_REJECT:
            flags.append("clipping")
        elif self._long_clip:
            flags.append("clipped_runs")
        if snr_db < SNR_DB_REJECT:
            flags.append("low_snr")
        if silence_ratio > SILENCE_RATIO_REJECT:
            flags.append("mostly_silent")

        acceptable = (
            score >= QUALITY_SCORE_REJECT
            and clipping_ratio <= CLIP_RATIO_REJECT
            and silence_ratio <= SILENCE_RATIO_REJECT
            and snr_db >= SNR_DB_REJECT
        )

        return AudioQuality(
            snr_db=snr_db,
            clipping_ratio=clipping_ratio,
            silence_ratio=silence_ratio,
            peak_dbfs=peak_dbfs,
            score=score,
            flags=flags,
            acceptable=acceptable,
        )


def _analyze_with_soundfile(path: Path) -> AudioQuality:
    with sf.SoundFile(str(path)) as handle:
        if handle.frames <= 0:
            raise AudioQualityAnalysisError(f"Audio has no frames: {path}")
        accumulator = _QualityAccumulator(handle.samplerate)
        for block in handle.blocks(
            blocksize=_QUALITY_BLOCK_FRAMES,
            dtype="float32",
            always_2d=True,
        ):
            accumulator.add_block(block)
    return accumulator.finish()


def _analyze_with_ffmpeg(path: Path) -> AudioQuality:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-f",
        "f32le",
        "-ac",
        "1",
        "-ar",
        str(TARGET_SR),
        "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if proc.stdout is None:
        raise AudioQualityAnalysisError(f"Could not open ffmpeg output for {path}")
    accumulator = _QualityAccumulator(TARGET_SR)
    try:
        while True:
            raw = proc.stdout.read(_QUALITY_BLOCK_FRAMES * 4)
            if not raw:
                break
            samples = np.frombuffer(raw, dtype="<f4")
            if samples.size:
                accumulator.add_block(samples.reshape(-1, 1))
        exit_code = proc.wait()
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    if exit_code != 0:
        raise AudioQualityAnalysisError(f"ffmpeg decode failed (exit {exit_code}) for {path}")
    return accumulator.finish()


def analyze_audio_quality(path: Path) -> AudioQuality:
    """Decode ``path`` and return a reference-free quality snapshot.

    Uses ``soundfile`` for fast native decoding and falls back to an ffmpeg
    float32 stream for formats such as m4a/webm.
    """
    try:
        return _analyze_with_soundfile(path)
    except AudioQualityAnalysisError:
        raise
    except Exception as soundfile_exc:
        logger.warning(
            "soundfile quality decode failed path=%s err=%s; trying ffmpeg",
            path,
            soundfile_exc,
        )
    try:
        return _analyze_with_ffmpeg(path)
    except Exception as ffmpeg_exc:
        raise AudioQualityAnalysisError(
            f"Could not decode audio for quality assessment: {path}"
        ) from ffmpeg_exc


def require_acceptable_quality(quality: AudioQuality | None) -> None:
    """Raise when a computed quality snapshot fails the ingest gate."""
    if quality is None:
        return
    if os.getenv("HARMONIQ_SKIP_AUDIO_QUALITY_GATE", "").strip() == "1":
        logger.info("audio_quality_gate skipped via HARMONIQ_SKIP_AUDIO_QUALITY_GATE=1")
        return
    if not quality.acceptable:
        raise AudioQualityTooLowError(AUDIO_QUALITY_LOW_USER_MESSAGE)
