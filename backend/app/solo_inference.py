"""Basic Pitch Solo Inference with Grid Quantization (Commit 79).

Fixed for ML Inference Stability & Diagnostics (Commit 95):
  - Resolves AttributeError '_UserObject' by using basic-pitch's default model path
    instead of forcing the .onnx filename.
  - Adds graceful fallback chain: default → TF SavedModel → ONNX → empty.
  - Replaces print() with structured logging for diagnostics.
  - Logs which model format is in use on each inference call.

Commit 107: Amplitude-based beat-slot selection and improved duration filtering.
  - Groups raw notes by beat slot, keeping only highest amplitude per slot.
  - Filters sub-32nd note durations for cleaner notation.
"""

from __future__ import annotations

import bisect
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from app.schemas import BeatGrid, SoloNote, SoloNotes

logger = logging.getLogger("harmoniq.inference.solo")


@dataclass
class ActiveNote:
    """A note still ringing at a segment boundary (Commit 100 tie mechanism)."""
    start_time: float
    pitch: int
    velocity: float
    end_time: float


class TieRegistry:
    """Tracks active notes across segment boundaries and resolves ties.

    Inspired by MT3's tie section mechanism: notes not re-declared in the
    next segment are gracefully ended; matching notes are merged.
    """

    def __init__(
        self,
        bpm: float,
        tie_epsilon_s: float = 0.050,
        velocity_tolerance: float = 0.3,
        max_sustain_beats: int = 4,
    ):
        self.active_notes: list[ActiveNote] = []
        self.last_segment_end: float = 0.0
        self.beat_duration = 60.0 / bpm if bpm > 0 else 0.5
        self.tie_epsilon_s = tie_epsilon_s
        self.velocity_tolerance = velocity_tolerance
        self.max_sustain_beats = max_sustain_beats

    def register_segment_end(self, notes: list[SoloNote], segment_end: float):
        """Collect notes still ringing at the segment boundary."""
        self.active_notes = []
        for note in notes:
            note_end = note.start_time + note.duration
            if note_end > segment_end:
                self.active_notes.append(ActiveNote(
                    start_time=note.start_time,
                    pitch=note.pitch,
                    velocity=float(note.velocity),
                    end_time=note_end,
                ))
        self.last_segment_end = segment_end

    def resolve_segment_start(self, notes: list[SoloNote]) -> list[SoloNote]:
        """Merge tied notes, close truncated ones, keep new notes.

        Returns deduplicated note list with cross-boundary ties resolved.
        """
        output: list[SoloNote] = []
        matched_indices: set[int] = set()

        for active in self.active_notes:
            max_duration = self.max_sustain_beats * self.beat_duration
            if active.end_time - active.start_time > max_duration:
                active.end_time = active.start_time + max_duration

            match_idx = self._find_matching_note(notes, active)

            if match_idx is not None:
                matched_indices.add(match_idx)
                new_note = notes[match_idx]
                merged_duration = new_note.start_time + new_note.duration - active.start_time
                output.append(SoloNote(
                    start_time=round(active.start_time, 3),
                    duration=round(merged_duration, 3),
                    pitch=active.pitch,
                    velocity=int(max(active.velocity, new_note.velocity)),
                ))
            else:
                truncated_duration = min(self.last_segment_end, active.end_time) - active.start_time
                if truncated_duration > 0:
                    output.append(SoloNote(
                        start_time=round(active.start_time, 3),
                        duration=round(truncated_duration, 3),
                        pitch=active.pitch,
                        velocity=int(active.velocity),
                    ))

        for i, note in enumerate(notes):
            if i not in matched_indices:
                output.append(note)

        output.sort(key=lambda n: n.start_time)
        return output

    def _find_matching_note(
        self,
        notes: list[SoloNote],
        active: ActiveNote,
    ) -> int | None:
        """Find a note in the next segment that matches the active note.

        Criteria: same pitch (±1 semitone), onset within epsilon of boundary,
        velocity within tolerance.
        """
        for i, note in enumerate(notes):
            pitch_match = abs(note.pitch - active.pitch) <= 1
            onset_near_boundary = abs(note.start_time - self.last_segment_end) <= self.tie_epsilon_s
            if not (pitch_match and onset_near_boundary):
                continue

            if active.velocity > 0:
                vel_ratio = abs(note.velocity - active.velocity) / active.velocity
                velocity_match = vel_ratio <= self.velocity_tolerance
            else:
                velocity_match = True

            if velocity_match:
                return i

        return None


def _snap_to_grid(time_s: float, grid_beats: list[float]) -> float:
    """Finds the closest tick in the beat grid to the given time."""
    if not grid_beats:
        return time_s
    idx = bisect.bisect_left(grid_beats, time_s)
    if idx == 0:
        return grid_beats[0]
    if idx == len(grid_beats):
        return grid_beats[-1]
    before = grid_beats[idx - 1]
    after = grid_beats[idx]
    return before if abs(time_s - before) < abs(time_s - after) else after


def _beat_slot_index(start_s: float, beat_times: list[float], bpm: float) -> int:
    """Map wall-clock seconds to a beat slot index.

    When beat_times has at least two samples, assign each note to the
    beat interval containing it. Otherwise fall back to uniform quarter spacing.
    """
    s = float(start_s)
    if not beat_times or len(beat_times) < 2:
        spq = 60.0 / max(bpm, 1.0)
        return max(0, int(s / spq))
    if s <= beat_times[0]:
        return 0
    for i in range(len(beat_times) - 1):
        if beat_times[i] <= s < beat_times[i + 1]:
            return i
    span = max(beat_times[-1] - beat_times[-2], 1e-3)
    extra = max(0, int((s - beat_times[-1]) / span))
    return len(beat_times) - 1 + extra


def _detect_model_type(model_path: Path) -> str:
    """Return a human-readable label for the model format."""
    if not model_path.exists():
        return "missing"
    if model_path.is_dir():
        return "tf_saved_model"
    suffix = model_path.suffix.lower()
    return {".tflite": "tflite", ".onnx": "onnx", ".mlpackage": "coreml"}.get(suffix, suffix)


def _try_inference(audio_path: Path, model_path: Path | None, beat_grid: BeatGrid) -> list | None:
    """Attempt inference with a specific model path. Returns raw notes or None on failure."""
    try:
        from basic_pitch.inference import predict

        _, _, raw_note_events = predict(
            str(audio_path),
            model_or_model_path=str(model_path) if model_path else None,
            onset_threshold=0.6,
            frame_threshold=0.4,
            minimum_note_length=0.0,
        )
        return raw_note_events
    except AttributeError as exc:
        logger.warning("Model format error with %s: %s", model_path, exc)
        return None
    except ImportError as exc:
        logger.warning("basic-pitch dependency missing: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Inference failed with %s: %s", type(exc).__name__, exc)
        return None


def infer_solo(melodic_stem_path: Path, beat_grid: BeatGrid) -> SoloNotes:
    try:
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import predict
    except ImportError:
        logger.warning("basic-pitch not installed. Returning empty solo notes.")
        return SoloNotes(notes=[])

    # Build fallback chain of model paths to try
    default_model = ICASSP_2022_MODEL_PATH
    model_candidates: list[Path | None] = [default_model]

    # If the default is a TF SavedModel dir, also try ONNX
    if default_model.is_dir():
        onnx_path = default_model.with_name("nmp.onnx")
        if onnx_path.exists():
            model_candidates.append(onnx_path)
    # If the default is ONNX, also try the TF SavedModel
    elif default_model.suffix == ".onnx":
        tf_path = default_model.with_name("nmp")
        if tf_path.is_dir():
            model_candidates.append(tf_path)

    raw_note_events = None
    model_used: Path | None = None
    model_label = "none"

    for candidate in model_candidates:
        if candidate is None or (not candidate.exists() and not candidate.is_dir()):
            continue
        model_label = _detect_model_type(candidate)
        logger.info("Trying solo model: %s (%s)", candidate.name, model_label)
        raw_note_events = _try_inference(melodic_stem_path, candidate, beat_grid)
        if raw_note_events is not None:
            model_used = candidate
            logger.info("Solo inference succeeded with %s (%s)", candidate.name, model_label)
            break
        logger.warning("Solo model %s failed, trying next fallback", candidate.name)

    if raw_note_events is None:
        logger.error("All solo model formats failed — returning empty solo notes. (model=%s)", model_label)
        return SoloNotes(notes=[])

    # Minimum duration threshold: keep grace notes that resolve to a single
    # tick after quantization. The 0.1 multiplier lets through notes as
    # short as ~6ms at 120 BPM; the quantization step assigns them a
    # one-tick duration rather than dropping them outright.
    seconds_per_32nd = (60.0 / beat_grid.bpm) / 8.0
    min_duration_s = max(0.005, seconds_per_32nd * 0.1)

    MIN_MIDI_VELOCITY = 40
    MAX_MIDI_VELOCITY = 120

    raw_notes: list[tuple[float, float, float, float]] = []
    for note in raw_note_events:
        start_time, end_time, pitch, velocity, _ = note
        duration = end_time - start_time
        if duration < min_duration_s:
            continue
        raw_notes.append((start_time, end_time, pitch, velocity))

    if not raw_notes:
        logger.info("No solo notes after duration filtering (min_duration=%.3fs)", min_duration_s)
        return SoloNotes(notes=[])

    # Amplitude-based beat-slot selection: keep only highest amplitude note per slot
    # This enforces monophony and removes polyphonic overlap (mirrors build_gp5_from_note_events)
    grid_beats = beat_grid.beats
    by_slot: dict[int, list[tuple[float, float, float, float]]] = defaultdict(list)
    for start_time, end_time, pitch, velocity in raw_notes:
        # Use the quantized start time so grace notes that snap to a different
        # grid point than the surrounding long note land in their own slot.
        q_start = _snap_to_grid(start_time, grid_beats)
        slot = _beat_slot_index(q_start, grid_beats, beat_grid.bpm)
        by_slot[slot].append((start_time, end_time, pitch, velocity))

    selected_notes: list[tuple[float, float, float, float]] = []
    for slot in sorted(by_slot.keys()):
        candidates = by_slot[slot]
        best = max(candidates, key=lambda n: (n[3], n[2]))  # amplitude, then pitch
        selected_notes.append(best)

    if len(selected_notes) < len(raw_notes):
        logger.info(
            "Beat-slot selection: %d notes → %d notes (%d removed as non-dominant)",
            len(raw_notes), len(selected_notes), len(raw_notes) - len(selected_notes),
        )

    max_input_velocity = max(n[3] for n in selected_notes)
    if max_input_velocity < 0.01:
        max_input_velocity = 0.5

    velocity_range = MAX_MIDI_VELOCITY - MIN_MIDI_VELOCITY
    cleaned_notes: list[SoloNote] = []
    LEGATO_OVERLAP_S = 0.010

    for start_time, end_time, pitch, velocity in selected_notes:
        duration = end_time - start_time
        q_start = _snap_to_grid(start_time, grid_beats)
        q_end = _snap_to_grid(end_time, grid_beats)
        q_duration = q_end - q_start
        if q_duration <= 0:
            q_duration = (60.0 / beat_grid.bpm) * beat_grid.tick_value
        if cleaned_notes and q_start < (cleaned_notes[-1].start_time + cleaned_notes[-1].duration):
            prev_note = cleaned_notes[-1]
            prev_note.duration = q_start - prev_note.start_time + LEGATO_OVERLAP_S
            if prev_note.duration <= 0:
                cleaned_notes.pop()
        normalized_velocity = (velocity / max_input_velocity) * velocity_range + MIN_MIDI_VELOCITY
        midi_velocity = int(max(MIN_MIDI_VELOCITY, min(MAX_MIDI_VELOCITY, normalized_velocity)))
        cleaned_notes.append(SoloNote(
            start_time=round(q_start, 3),
            duration=round(q_duration, 3),
            pitch=int(pitch),
            velocity=midi_velocity,
        ))

    cleaned_notes = _merge_boundary_notes(cleaned_notes, beat_grid.bpm)

    logger.info("Solo inference complete: %d notes (model=%s)", len(cleaned_notes), model_label)
    return SoloNotes(notes=cleaned_notes)


def _merge_boundary_notes(
    notes: list[SoloNote],
    bpm: float,
    window_sec: float = 12.8,
) -> list[SoloNote]:
    """Post-inference merge pass: resolve ties at chord window boundaries.

    Applies the TieRegistry mechanism to notes that span virtual segment
    boundaries (every 128 chord frames = 12.8s at _HOP_SEC=0.1).

    Args:
        notes: Quantized solo notes from Basic Pitch.
        bpm: Tempo for sustain timeout calculation.
        window_sec: Duration of one non-overlapping chord window.

    Returns:
        Deduplicated note list with cross-boundary ties merged.
    """
    if not notes:
        return []

    registry = TieRegistry(bpm=bpm)
    all_notes = list(notes)
    result: list[SoloNote] = []

    boundaries = []
    b = window_sec
    max_time = max(n.start_time + n.duration for n in all_notes)
    while b < max_time:
        boundaries.append(b)
        b += window_sec

    segment_start = 0.0
    pending_notes: list[SoloNote] = []

    for boundary in boundaries:
        segment_notes = [n for n in all_notes if n.start_time < boundary]
        remaining = [n for n in all_notes if n.start_time >= boundary]

        if not segment_notes:
            segment_start = boundary
            continue

        registry.register_segment_end(segment_notes, boundary)
        resolved = registry.resolve_segment_start(remaining)

        closed_notes = [n for n in segment_notes if n.start_time + n.duration <= boundary]
        result.extend(closed_notes)

        all_notes = remaining
        segment_start = boundary

    result.extend(all_notes)
    result.sort(key=lambda n: (n.start_time, n.pitch))

    if len(result) < len(notes):
        logger.info(
            "Boundary tie merge: %d notes → %d notes (%d merged)",
            len(notes), len(result), len(notes) - len(result),
        )

    return result
