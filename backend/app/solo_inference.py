"""Basic Pitch Solo Inference with Grid Quantization (Commit 79).

Fixed for ML Inference Stability & Diagnostics (Commit 95):
  - Resolves AttributeError '_UserObject' by using basic-pitch's default model path
    instead of forcing the .onnx filename.
  - Adds graceful fallback chain: default → TF SavedModel → ONNX → empty.
  - Replaces print() with structured logging for diagnostics.
  - Logs which model format is in use on each inference call.
"""

from __future__ import annotations

import bisect
import logging
from pathlib import Path

from app.schemas import BeatGrid, SoloNote, SoloNotes

logger = logging.getLogger("harmoniq.inference.solo")


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

    # Minimum duration threshold
    min_duration_s = (60.0 / beat_grid.bpm) * (beat_grid.tick_value * 0.5)

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

    max_input_velocity = max(n[3] for n in raw_notes)
    if max_input_velocity < 0.01:
        max_input_velocity = 0.5

    velocity_range = MAX_MIDI_VELOCITY - MIN_MIDI_VELOCITY
    cleaned_notes: list[SoloNote] = []
    grid_beats = beat_grid.beats
    LEGATO_OVERLAP_S = 0.010

    for start_time, end_time, pitch, velocity in raw_notes:
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

    logger.info("Solo inference complete: %d notes (model=%s)", len(cleaned_notes), model_label)
    return SoloNotes(notes=cleaned_notes)
