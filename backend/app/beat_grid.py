"""Beat/downbeat estimation with manual override recomputation (commit 78)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from app.pipeline_proof import TARGET_SR

try:
    import librosa
except ImportError:
    librosa = None  # type: ignore

# Lower sample rate for beat tracking to reduce memory usage (~50% reduction)
# 22050Hz is sufficient for tempo/beat estimation without affecting accuracy
BEAT_TRACK_SR = 22050

DEFAULT_TIME_SIGNATURE = "4/4"
DEPENDENT_ARTIFACTS = ("chordTimeline", "SoloNotes", "Score.musicxml")

class BeatGridComputationError(RuntimeError):
    """Raised when beat grid estimation or override parsing fails."""

def parse_time_signature(value: str | None) -> tuple[int, int]:
    raw = (value or DEFAULT_TIME_SIGNATURE).strip()
    if "/" not in raw:
        raise BeatGridComputationError("time_signature must be in 'numerator/denominator' format.")
    a, b = raw.split("/", 1)
    try:
        numerator = int(a)
        denominator = int(b)
    except ValueError as exc:
        raise BeatGridComputationError("time_signature must contain integers.") from exc
    if numerator <= 0 or denominator <= 0:
        raise BeatGridComputationError("time_signature values must be positive.")
    return numerator, denominator

def _duration_seconds(y: np.ndarray, sr: int) -> float:
    if sr <= 0:
        return 0.0
    return float(y.shape[0] / float(sr))

def _uniform_beat_grid(duration_s: float, bpm: float) -> list[float]:
    if not math.isfinite(duration_s) or duration_s <= 0.0:
        return [0.0]
    if bpm <= 0.0 or not math.isfinite(bpm):
        raise BeatGridComputationError("BPM must be a positive finite value.")
    step = 60.0 / bpm
    # Use deterministic calculation to avoid floating-point drift over long tracks
    num_beats = int(duration_s / step) + 1
    beats = [round(i * step, 6) for i in range(num_beats)]
    if not beats:
        beats = [0.0]
    return beats

def _subdivide_beats(pulse_beats: list[float], subdivisions: int) -> list[float]:
    """Interpolates micro-grid ticks between macro pulses."""
    if subdivisions <= 1 or len(pulse_beats) < 2:
        return pulse_beats
    
    ticks = []
    for i in range(len(pulse_beats) - 1):
        start = pulse_beats[i]
        end = pulse_beats[i + 1]
        step = (end - start) / subdivisions
        for j in range(subdivisions):
            ticks.append(round(start + j * step, 6))
    # Ensure the final pulse is included
    ticks.append(pulse_beats[-1])
    return ticks

def _downbeats_from_beats(beats: list[float], beats_per_bar: int) -> list[float]:
    """Extract downbeat timestamps from beat grid.

    Assumes the first element of beats is the start of Bar 1.
    If implementing pickup notes (anacrusis) or offset features,
    this logic will need adjustment to handle non-zero starting beats.
    """
    if beats_per_bar <= 0:
        return [0.0]
    out = [float(beats[i]) for i in range(0, len(beats), beats_per_bar)]
    if not out:
        return [0.0]
    if out[0] != 0.0:
        out.insert(0, 0.0)
    return out

def estimate_beat_grid(
    audio_path: Path,
    *,
    time_signature: str | None = None,
    bpm_override: float | None = None,
) -> dict[str, object]:
    """Estimate beat/downbeat grid from audio and apply manual overrides when provided."""
    if not audio_path.is_file():
        raise BeatGridComputationError(f"Audio file missing: {audio_path}")

    beats_per_bar, denominator = parse_time_signature(time_signature)
    tick_value = 1.0 / denominator

    # Determine if this is a compound meter requiring subdivision
    is_compound = denominator == 8 and beats_per_bar in (6, 9, 12)
    subdivisions = 3 if is_compound else 1

    if librosa is None:
        raise BeatGridComputationError("librosa is required for beat grid estimation.")

    try:
        # Use lower sample rate for beat tracking to reduce memory usage
        y, sr = librosa.load(str(audio_path), sr=BEAT_TRACK_SR, mono=True)
    except Exception as exc:
        raise BeatGridComputationError(f"Could not load audio for beat tracking: {exc}") from exc

    duration_s = _duration_seconds(y, int(sr))
    if duration_s <= 0.0:
        raise BeatGridComputationError("Audio duration is zero; cannot compute beat grid.")

    if bpm_override is not None:
        pulse_bpm = float(bpm_override)
        if pulse_bpm < 20.0 or pulse_bpm > 300.0:
            raise BeatGridComputationError("bpm_override must be between 20 and 300.")
        pulse_beats = _uniform_beat_grid(duration_s, pulse_bpm)
    else:
        hop_length = 512
        onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
        tempo_est, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env,
            sr=sr,
            hop_length=hop_length,
        )
        tempo_arr = np.atleast_1d(tempo_est).astype(float)
        pulse_bpm = float(tempo_arr[0]) if tempo_arr.size else 120.0
        beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)
        pulse_beats = sorted(float(t) for t in beat_times if float(t) >= 0.0)
        
        if not pulse_beats:
            pulse_beats = _uniform_beat_grid(duration_s, pulse_bpm)
        if pulse_beats and pulse_beats[0] > 0.05:
            pulse_beats.insert(0, 0.0)
        elif pulse_beats:
            pulse_beats[0] = 0.0

    # Apply subdivisions to convert pulses into the actual quantization grid
    grid_bpm = pulse_bpm * subdivisions
    beats = _subdivide_beats(pulse_beats, subdivisions)
    downbeats = _downbeats_from_beats(beats, beats_per_bar)

    return {
        "bpm": round(float(grid_bpm), 3),
        "pulse_bpm": round(float(pulse_bpm), 3),  # Original pulse tempo (e.g., dotted quarter for 6/8)
        "beats": beats,
        "downbeats": downbeats,
        "time_signature": {
            "numerator": beats_per_bar,
            "denominator": denominator
        },
        "tick_value": tick_value,
    }

def dependent_artifacts_for_grid_override() -> list[str]:
    """Artifacts that must be refreshed when BPM/time-signature overrides change."""
    return list(DEPENDENT_ARTIFACTS)