"""Basic Pitch Solo Inference with Grid Quantization (Commit 79).

Fixed for ML Inference Stability & Diagnostics (Commit 95):
  - Resolves AttributeError '_UserObject' by using basic-pitch's default model path
    instead of forcing the .onnx filename.
  - Adds graceful fallback chain: default → TF SavedModel → ONNX → empty.
  - Replaces print() with structured logging for diagnostics.
  - Logs which model format is in use on each inference call.

Segment Boundary Tie Mechanism (Commit 100, MT3 paper insight):
  - Long tracks are split into overlapping segments. Each segment is
    transcribed independently with basic-pitch, then ``merge_segments_with_ties``
    applies the MT3 "tie section": an active-note table (keyed by pitch) is
    carried across segment boundaries. A note detected in the next segment
    whose onset falls within ``TIE_WINDOW_S`` of the previous same-pitch
    note's end is treated as a re-declaration and tied into a single
    continuous note; notes never re-declared survive from their first
    detection (the "forgotten note" failure mode) instead of being dropped at
    the boundary.
  - Fresh onsets inside ``BOUNDARY_WINDOW_S`` after a segment boundary are
    velocity-dampened: the model's partial-context predictions there are the
    most likely false positives.
"""

from __future__ import annotations

import bisect
import logging
import tempfile
import wave
from pathlib import Path

import numpy as np

from app.schemas import BeatGrid, SoloNote, SoloNotes

logger = logging.getLogger("harmoniq.inference.solo")

# Commit 100: segment geometry and tie parameters.
SEGMENT_LENGTH_S = 60.0
SEGMENT_OVERLAP_S = 15.0
TIE_WINDOW_S = 0.15          # re-declaration tolerance (~2 frames at 0.1s hop)
BOUNDARY_WINDOW_S = 0.2      # fresh-onset damping zone after a segment boundary
BOUNDARY_VELOCITY_FACTOR = 0.85


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


# ---------------------------------------------------------------------------
# Commit 100: segment geometry + MT3-style active-note tie mechanism
# ---------------------------------------------------------------------------


def _segment_ranges(
    duration_s: float,
    segment_length_s: float = SEGMENT_LENGTH_S,
    overlap_s: float = SEGMENT_OVERLAP_S,
) -> list[tuple[float, float]]:
    """Split a duration into overlapping segments.

    Segments are ``segment_length_s`` long and stride by
    ``segment_length_s - overlap_s``, so consecutive segments share an
    overlap zone in which notes spanning a boundary are detected twice — the
    raw material the tie mechanism needs to declare continuations.
    """
    if duration_s <= 0:
        return []
    if duration_s <= segment_length_s:
        return [(0.0, duration_s)]
    stride = segment_length_s - overlap_s
    if stride <= 0:
        stride = segment_length_s / 2.0
    ranges: list[tuple[float, float]] = []
    start = 0.0
    while start < duration_s - 1e-9:
        end = min(start + segment_length_s, duration_s)
        ranges.append((start, end))
        if end >= duration_s - 1e-9:
            break
        start += stride
    return ranges


def merge_segments_with_ties(
    segmented_notes: list[list[tuple[float, float, int, float]]],
    tie_window_s: float = TIE_WINDOW_S,
) -> list[tuple[float, float, int, float]]:
    """Merge per-segment note lists into one timeline using MT3 tie semantics.

    Each element of ``segmented_notes`` holds notes detected in one segment
    as ``(start_time_s, end_time_s, pitch_midi, velocity)`` in absolute time.

    An "active notes" table (keyed by MIDI pitch) is carried across segment
    boundaries. When a note in the next segment has the same pitch and its
    onset falls within ``tie_window_s`` of the previous same-pitch note's
    end, it is a re-declaration (MT3's tie section): the two detections are
    tied into a single continuous note (start from the first, end/velocity
    extended from the max). A note that is never re-declared is emitted
    intact from its first detection, so notes the model fails to re-detect
    after a boundary — the "forgotten note" failure mode — are not dropped
    and not shortened.

    Notes are assumed sorted by start time within each segment.
    """
    result: list[tuple[float, float, int, float]] = []
    active: dict[int, int] = {}  # pitch -> index of the current note in `result`

    for segment in segmented_notes:
        for start, end, pitch, velocity in sorted(segment, key=lambda n: n[0]):
            prev_idx = active.get(int(pitch))
            if prev_idx is not None:
                prev_start, prev_end, prev_pitch, prev_velocity = result[prev_idx]
                if start <= prev_end + tie_window_s:
                    result[prev_idx] = (
                        prev_start,
                        max(prev_end, end),
                        prev_pitch,
                        max(prev_velocity, velocity),
                    )
                    continue
            result.append((start, end, int(pitch), float(velocity)))
            active[int(pitch)] = len(result) - 1
    return result


def _dampen_boundary_onsets(
    notes: list[tuple[float, float, int, float]],
    segment_starts: list[float],
    window_s: float = BOUNDARY_WINDOW_S,
    factor: float = BOUNDARY_VELOCITY_FACTOR,
) -> tuple[list[tuple[float, float, int, float]], int]:
    """Velocity-dampen fresh onsets just after segment boundaries.

    A note whose onset lands inside ``window_s`` after a segment start was
    only ever seen with a truncated context window — exactly where the model
    emits spurious attacks. Continuations tied from the previous segment keep
    their earlier onset and are never dampened.

    Returns (notes, number_dampened).
    """
    dampened = 0
    out: list[tuple[float, float, int, float]] = []
    for start, end, pitch, velocity in notes:
        if any(b <= start < b + window_s for b in segment_starts):
            velocity = float(velocity) * factor
            dampened += 1
        out.append((start, end, int(pitch), velocity))
    return out, dampened


def _to_absolute_notes(note_events: list, offset_s: float) -> list[tuple[float, float, int, float]]:
    """Convert basic-pitch 5-tuples to 4-tuples shifted into absolute time."""
    abs_notes: list[tuple[float, float, int, float]] = []
    for note in note_events:
        start_time, end_time, pitch, velocity, _ = note
        abs_notes.append((start_time + offset_s, end_time + offset_s, int(pitch), float(velocity)))
    return abs_notes


# ---------------------------------------------------------------------------
# Shared post-processing
# ---------------------------------------------------------------------------


def _cleanup_raw_notes(
    raw_notes: list,
    beat_grid: BeatGrid,
    min_duration_s: float,
    model_label: str,
) -> list[SoloNote]:
    """Filter, unify, quantize, and velocity-map raw notes (shared paths)."""
    MAX_INPUT_VELOCITY_FLOOR = 0.5
    MIN_MIDI_VELOCITY = 40
    MAX_MIDI_VELOCITY = 120

    clean: list[tuple[float, float, int, float]] = []
    for note in raw_notes:
        start_time, end_time, pitch, velocity = note[0], note[1], note[2], note[3]
        duration = end_time - start_time
        if duration < min_duration_s:
            continue
        clean.append((start_time, end_time, int(pitch), float(velocity)))

    if not clean:
        logger.info("No solo notes after duration filtering (min_duration=%.3fs)", min_duration_s)
        return []

    max_input_velocity = max(n[3] for n in clean)
    if max_input_velocity < 0.01:
        max_input_velocity = MAX_INPUT_VELOCITY_FLOOR

    velocity_range = MAX_MIDI_VELOCITY - MIN_MIDI_VELOCITY
    cleaned_notes: list[SoloNote] = []
    grid_beats = beat_grid.beats
    LEGATO_OVERLAP_S = 0.010
    tick_seconds = (60.0 / beat_grid.bpm) * beat_grid.tick_value

    for start_time, end_time, pitch, velocity in clean:
        duration = end_time - start_time
        q_start = _snap_to_grid(start_time, grid_beats)
        q_end = _snap_to_grid(end_time, grid_beats)
        q_duration = q_end - q_start
        if q_duration <= 0:
            q_duration = tick_seconds
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
            pitch=pitch,
            velocity=midi_velocity,
        ))

    logger.info("Solo inference complete: %d notes (model=%s)", len(cleaned_notes), model_label)
    return cleaned_notes


def _model_candidates() -> list[Path | None]:
    """Build the fallback chain of model paths to try."""
    try:
        from basic_pitch import ICASSP_2022_MODEL_PATH
    except ImportError:
        return []

    default_model = ICASSP_2022_MODEL_PATH
    candidates: list[Path | None] = [default_model]

    # If the default is a TF SavedModel dir, also try ONNX
    if default_model.is_dir():
        onnx_path = default_model.with_name("nmp.onnx")
        if onnx_path.exists():
            candidates.append(onnx_path)
    # If the default is ONNX, also try the TF SavedModel
    elif default_model.suffix == ".onnx":
        tf_path = default_model.with_name("nmp")
        if tf_path.is_dir():
            candidates.append(tf_path)
    return candidates


def _run_model_chain(audio_path: Path, beat_grid: BeatGrid) -> tuple[list | None, str]:
    """Run the model fallback chain against one audio file.

    Returns (raw_note_events or None, model_label).
    """
    candidates = _model_candidates()
    model_label = "none"
    for candidate in candidates:
        if candidate is None or (not candidate.exists() and not candidate.is_dir()):
            continue
        model_label = _detect_model_type(candidate)
        logger.info("Trying solo model: %s (%s)", candidate.name, model_label)
        raw_note_events = _try_inference(audio_path, candidate, beat_grid)
        if raw_note_events is not None:
            logger.info("Solo inference succeeded with %s (%s)", candidate.name, model_label)
            return raw_note_events, model_label
        logger.warning("Solo model %s failed, trying next fallback", candidate.name)
    return None, model_label


def _write_wav(path: Path, y: np.ndarray, sr: int) -> None:
    """Write float audio to a 16-bit PCM WAV (for segment inference)."""
    pcm16 = np.clip(y, -1.0, 1.0)
    pcm16 = (pcm16 * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())


def infer_solo(
    melodic_stem_path: Path,
    beat_grid: BeatGrid,
    segment_length_s: float = SEGMENT_LENGTH_S,
    overlap_s: float = SEGMENT_OVERLAP_S,
) -> SoloNotes:
    try:
        from basic_pitch import ICASSP_2022_MODEL_PATH  # noqa: F401  (import check)
    except ImportError:
        logger.warning("basic-pitch not installed. Returning empty solo notes.")
        return SoloNotes(notes=[])

    # Minimum duration threshold
    min_duration_s = (60.0 / beat_grid.bpm) * (beat_grid.tick_value * 0.5)

    # Duration is only needed to decide whether segmentation is required;
    # a missing/unreadable file falls back to single-pass. soundfile is used
    # directly (it is a librosa dependency) because librosa.get_duration
    # falls back to the deprecated audioread on unreadable paths, which can
    # stall for tens of seconds on a missing file.
    duration_s: float | None = None
    if melodic_stem_path.is_file():
        try:
            import soundfile as sf

            duration_s = float(sf.info(str(melodic_stem_path)).duration)
        except Exception:
            logger.warning("Could not read audio duration for %s; using single-pass", melodic_stem_path)

    ranges = _segment_ranges(duration_s if duration_s is not None else -1.0, segment_length_s, overlap_s)
    if duration_s is not None and len(ranges) > 1:
        raw_note_events, model_label = _infer_segmented(melodic_stem_path, ranges, beat_grid)
    else:
        raw_note_events, model_label = _run_model_chain(melodic_stem_path, beat_grid)

    if raw_note_events is None:
        logger.error("All solo model formats failed — returning empty solo notes. (model=%s)", model_label)
        return SoloNotes(notes=[])

    normalized = [
        (n[0], n[1], int(n[2]), float(n[3])) for n in raw_note_events
    ]
    cleaned_notes = _cleanup_raw_notes(normalized, beat_grid, min_duration_s, model_label)
    return SoloNotes(notes=cleaned_notes)


def _infer_segmented(
    audio_path: Path,
    ranges: list[tuple[float, float]],
    beat_grid: BeatGrid,
) -> tuple[list | None, str]:
    """Transcribe audio in overlapping segments and tie notes across boundaries.

    Each segment is written to a temporary WAV, transcribed with the model
    fallback chain, offset into absolute time, then merged with the MT3
    active-note tie mechanism. Fresh onsets inside the boundary damping zone
    are velocity-penalized.

    Returns (merged notes as basic-pitch-style 5-tuples or None, model_label).
    """
    import librosa

    duration_s = ranges[-1][1]
    model_label = "none"
    segmented_notes: list[list[tuple[float, float, int, float]]] = []
    for start_s, end_s in ranges:
        y_slice, sr = librosa.load(
            str(audio_path), sr=44100, mono=True, offset=start_s, duration=end_s - start_s
        )
        if len(y_slice) == 0:
            continue
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            _write_wav(tmp_path, y_slice, sr)
            segment_events, model_label = _run_model_chain(tmp_path, beat_grid)
            if segment_events is None:
                logger.warning("Segment [%.1f, %.1f) failed; skipping", start_s, end_s)
                continue
            segment_offsets = _to_absolute_notes(segment_events, start_s)
            segmented_notes.append(segment_offsets)
        finally:
            tmp_path.unlink(missing_ok=True)

    if not segmented_notes:
        return None, model_label

    merged = merge_segments_with_ties(segmented_notes)
    boundary_starts = [start_s for start_s, _ in ranges[1:]]
    dampened, n_dampened = _dampen_boundary_onsets(merged, boundary_starts)
    logger.info(
        "Solo segmented inference: %d segments, %d raw notes -> %d tied notes "
        "(%d boundary onsets dampened, track=%.1fs)",
        len(segmented_notes),
        sum(len(s) for s in segmented_notes),
        len(merged),
        n_dampened,
        duration_s,
    )

    # Rebuild 5-tuples (bend=None) so downstream code has one canonical shape.
    return [(s, e, p, v, None) for s, e, p, v in dampened], model_label