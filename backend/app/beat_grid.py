"""Beat/downbeat estimation with manual overrides and variable-tempo curves.

Commit 78: manual override recomputation.
Commit 169: ``(time, bpm)`` tempo curves for ramps and instantaneous shifts.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

import numpy as np

try:
    import librosa
except ImportError:
    librosa = None  # type: ignore

# Lower sample rate for beat tracking to reduce memory usage (~50% reduction)
# 22050Hz is sufficient for tempo/beat estimation without affecting accuracy
BEAT_TRACK_SR = 22050

DEFAULT_TIME_SIGNATURE = "4/4"
DEPENDENT_ARTIFACTS = ("chordTimeline", "SoloNotes", "Score.musicxml", "barTimestamps")

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

def _normalize_tempo_curve(
    duration_s: float,
    tempo_curve: Sequence[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Validate and normalize a ``(time, bpm)`` curve for grid generation.

    Duplicate timestamps are preserved (a zero-length segment) so the previous
    BPM holds until that instant and the next BPM applies afterwards — this
    models an instantaneous shift. The curve is extended to ``duration_s`` by
    holding the final BPM.
    """
    if len(tempo_curve) == 0:
        raise BeatGridComputationError("tempo_curve must contain at least one (time, bpm) pair.")

    points: list[tuple[float, float]] = []
    for index, item in enumerate(tempo_curve):
        try:
            time_s = float(item[0])
            bpm = float(item[1])
        except (TypeError, IndexError, ValueError) as exc:
            raise BeatGridComputationError(
                f"tempo_curve[{index}] must be a (time, bpm) pair."
            ) from exc
        if not math.isfinite(time_s) or time_s < 0.0:
            raise BeatGridComputationError("tempo_curve times must be finite and non-negative.")
        if not math.isfinite(bpm) or bpm <= 0.0:
            raise BeatGridComputationError("tempo_curve BPM values must be positive and finite.")
        points.append((time_s, bpm))

    points.sort(key=lambda point: point[0])

    if points[0][0] > 0.0:
        points.insert(0, (0.0, points[0][1]))

    trimmed: list[tuple[float, float]] = []
    for time_s, bpm in points:
        if time_s < duration_s:
            trimmed.append((time_s, bpm))
            continue
        if not trimmed:
            trimmed.append((duration_s, bpm))
            break
        previous_time, previous_bpm = trimmed[-1]
        if previous_time >= duration_s:
            trimmed.append((duration_s, bpm))
        else:
            fraction = (duration_s - previous_time) / (time_s - previous_time)
            trimmed.append((duration_s, previous_bpm + (bpm - previous_bpm) * fraction))
        break

    if trimmed[-1][0] < duration_s:
        trimmed.append((duration_s, trimmed[-1][1]))

    return trimmed


def _reference_bpm_from_curve(points: list[tuple[float, float]]) -> float:
    """Duration-weighted mean BPM of a normalized curve (base pulse tempo)."""
    total_duration = 0.0
    weighted_bpm = 0.0
    for (t0, b0), (t1, b1) in zip(points, points[1:]):
        segment_duration = t1 - t0
        if segment_duration <= 0.0:
            continue
        total_duration += segment_duration
        weighted_bpm += 0.5 * (b0 + b1) * segment_duration
    if total_duration <= 0.0:
        return points[0][1]
    return weighted_bpm / total_duration


def _beat_times_from_tempo_curve(
    duration_s: float,
    points: list[tuple[float, float]],
) -> list[float]:
    """Generate pulse beat times by integrating a piecewise-linear tempo curve.

    Each segment linearly ramps from its start BPM to its end BPM, so both
    gradual rubato and abrupt shifts (adjacent points) are supported. Beat
    ``n`` lands where the integrated beat phase crosses ``n``.
    """
    if duration_s <= 0.0:
        return [0.0]

    cumulative_beats: list[float] = [0.0]
    phase = 0.0
    for (t0, b0), (t1, b1) in zip(points, points[1:]):
        segment_duration = t1 - t0
        if segment_duration <= 0.0:
            cumulative_beats.append(phase)
            continue
        phase += 0.5 * (b0 + b1) / 60.0 * segment_duration
        cumulative_beats.append(phase)

    total_beats = cumulative_beats[-1]
    beats = [0.0]
    segment_index = 0
    last_beat = int(math.floor(total_beats + 1e-9))

    for beat_index in range(1, last_beat + 1):
        while (
            segment_index < len(points) - 2
            and cumulative_beats[segment_index + 1] < beat_index - 1e-12
        ):
            segment_index += 1

        t0, b0 = points[segment_index]
        t1, b1 = points[segment_index + 1]
        segment_duration = t1 - t0
        beats_into_segment = beat_index - cumulative_beats[segment_index]
        if beats_into_segment <= 1e-12:
            offset = 0.0
        elif abs(b1 - b0) < 1e-12:
            offset = beats_into_segment * 60.0 / b0
        else:
            # Solve a*tau^2 + b*tau - k = 0 with the cancellation-safe root.
            a = (b1 - b0) / (120.0 * segment_duration)
            b = b0 / 60.0
            discriminant = max(b * b + 4.0 * a * beats_into_segment, 0.0)
            offset = (2.0 * beats_into_segment) / (b + math.sqrt(discriminant))

        offset = min(max(offset, 0.0), segment_duration)
        beat_time = round(t0 + offset, 6)
        if beat_time > duration_s:
            continue
        beats.append(beat_time)

    return beats


def _beat_grid_from_tempo_curve(
    duration_s: float,
    tempo_curve: Sequence[tuple[float, float]],
) -> list[float]:
    """Generate a pulse beat grid from a ``(time, bpm)`` tempo curve."""
    if not math.isfinite(duration_s) or duration_s <= 0.0:
        return [0.0]
    points = _normalize_tempo_curve(duration_s, tempo_curve)
    return _beat_times_from_tempo_curve(duration_s, points)


def _uniform_beat_grid(duration_s: float, bpm: float) -> list[float]:
    if not math.isfinite(duration_s) or duration_s <= 0.0:
        return [0.0]
    if bpm <= 0.0 or not math.isfinite(bpm):
        raise BeatGridComputationError("BPM must be a positive finite value.")
    return _beat_grid_from_tempo_curve(duration_s, [(0.0, bpm)])

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

def _tempo_changes_from_points(
    points: list[tuple[float, float]],
    duration_s: float,
) -> list[dict[str, float]]:
    """Serialize curve points as tempo events, dropping the synthetic hold sentinel."""
    events: list[dict[str, float]] = []
    for index, (time_s, bpm) in enumerate(points):
        if time_s > duration_s + 1e-9:
            continue
        is_synthetic_sentinel = (
            index == len(points) - 1
            and index > 0
            and abs(time_s - duration_s) <= 1e-9
            and points[index - 1][1] == bpm
        )
        if is_synthetic_sentinel:
            continue
        events.append({"time": round(time_s, 6), "bpm": round(bpm, 3)})
    return events


def estimate_beat_grid(
    audio_path: Path,
    *,
    time_signature: str | None = None,
    bpm_override: float | None = None,
    tempo_curve: Sequence[tuple[float, float]] | None = None,
) -> dict[str, object]:
    """Estimate beat/downbeat grid from audio and apply manual overrides when provided.

    ``tempo_curve`` accepts ``(time_seconds, bpm)`` pairs. Points are joined by
    linear ramps; two points sharing a timestamp model an instantaneous shift.
    ``bpm_override`` and ``tempo_curve`` are mutually exclusive.
    """
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

    tempo_changes: list[dict[str, float]] = []

    if tempo_curve is not None and bpm_override is not None:
        raise BeatGridComputationError(
            "Provide either bpm_override or tempo_curve, not both."
        )

    if tempo_curve is not None:
        if len(tempo_curve) == 0:
            raise BeatGridComputationError("tempo_curve must contain at least one (time, bpm) pair.")
        points = _normalize_tempo_curve(duration_s, tempo_curve)
        for _, curve_bpm in points:
            if curve_bpm < 20.0 or curve_bpm > 300.0:
                raise BeatGridComputationError("tempo_curve BPM must be between 20 and 300.")
        pulse_bpm = _reference_bpm_from_curve(points)
        pulse_beats = _beat_times_from_tempo_curve(duration_s, points)
        tempo_changes = _tempo_changes_from_points(points, duration_s)
    elif bpm_override is not None:
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
        "tempo_changes": tempo_changes,
    }

def dependent_artifacts_for_grid_override() -> list[str]:
    """Artifacts that must be refreshed when BPM/time-signature overrides change."""
    return list(DEPENDENT_ARTIFACTS)