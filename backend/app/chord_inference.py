"""TFLite Chord Inference with Volume Thresholding and Beat Pooling (Commit 79).

Fixed for ML Inference Stability & Diagnostics (Commit 95):
  - Replaces print() with structured logging.
  - Standardized model loading with backend detection logging.
  - Diagnostics for model mismatch errors.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.schemas import BeatGrid, ChordEvent, ChordTimeline
from app.pipeline_proof import TARGET_SR

logger = logging.getLogger("harmoniq.inference.chord")

CHORD_VOCAB = [
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
    "Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "A#m", "Bm",
    "N",
]

_MODEL_PATH = Path(__file__).parent / "chord_model.tflite"
_WINDOW = 9
_HOP_SEC = 0.1


def _get_segment_db(y_segment: np.ndarray) -> float:
    if len(y_segment) == 0:
        return -100.0
    rms = np.sqrt(np.mean(y_segment**2))
    if rms < 1e-9:
        return -100.0
    return float(20 * math.log10(rms))


def _smooth_chords(events: list[ChordEvent]) -> list[ChordEvent]:
    if len(events) < 3:
        return events
    smoothed = events[:]
    for i in range(1, len(events) - 1):
        prev_chord = smoothed[i - 1].chord
        curr_chord = smoothed[i].chord
        next_chord = smoothed[i + 1].chord
        if curr_chord != prev_chord and curr_chord != next_chord and prev_chord == next_chord:
            smoothed[i] = ChordEvent(
                timestamp=smoothed[i].timestamp,
                chord=prev_chord,
                confidence=round(smoothed[i].confidence * 0.8, 3),
            )
    return smoothed


@lru_cache(maxsize=1)
def _get_interpreter():
    """Load the TFLite interpreter once and cache it for the process lifetime.

    Tries tflite-runtime first, falls back to TensorFlow Lite, then raises.
    """
    path = str(_MODEL_PATH)
    if not _MODEL_PATH.exists():
        raise FileNotFoundError(f"Chord model not found at {_MODEL_PATH}")

    # Try tflite-runtime (lighter dependency)
    try:
        import tflite_runtime.interpreter as tflite

        interp = tflite.Interpreter(model_path=path)
        logger.info("Chord model loaded via tflite-runtime")
    except ImportError:
        # Fall back to TensorFlow Lite
        try:
            import tensorflow as tf

            interp = tf.lite.Interpreter(model_path=path)
            logger.info("Chord model loaded via TensorFlow Lite")
        except ImportError as exc:
            raise RuntimeError(
                "Chord inference requires tflite-runtime or tensorflow. "
                "Install with: pip install tflite-runtime"
            ) from exc
    except Exception as exc:
        raise RuntimeError(f"Failed to load chord model at {path}: {exc}") from exc

    interp.allocate_tensors()
    input_details = interp.get_input_details()
    output_details = interp.get_output_details()
    logger.debug(
        "Chord model input shape=%s output shape=%s",
        input_details[0].get("shape"),
        output_details[0].get("shape"),
    )
    return interp


def _run_tflite_raw(y: np.ndarray, sr: int) -> list[dict]:
    import librosa

    hop = int(sr * _HOP_SEC)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop, n_chroma=12)
    chroma = chroma.T.astype(np.float32)
    norms = chroma.sum(axis=1, keepdims=True).clip(1e-8, None)
    chroma = chroma / norms

    T = len(chroma)
    half = _WINDOW // 2
    pad = np.zeros((half, 12), dtype=np.float32)
    padded = np.concatenate([pad, chroma, pad], axis=0)

    interp = _get_interpreter()
    inp_detail = interp.get_input_details()[0]
    outp_detail = interp.get_output_details()[0]

    results = []
    for i in range(T):
        window = padded[i : i + _WINDOW][np.newaxis]
        interp.set_tensor(inp_detail["index"], window)
        interp.invoke()
        probs = interp.get_tensor(outp_detail["index"])[0]
        pred_idx = int(np.argmax(probs))
        results.append({
            "time": i * _HOP_SEC,
            "chord": CHORD_VOCAB[pred_idx],
            "confidence": float(probs[pred_idx]),
        })
    return results


def infer_chords(audio_path: Path, beat_grid: BeatGrid) -> ChordTimeline:
    try:
        import librosa
    except ImportError as exc:
        raise RuntimeError("librosa is required for chord inference.") from exc

    try:
        y, sr = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
    except FileNotFoundError:
        logger.warning("Audio file not found at %s. Returning empty chord timeline.", audio_path)
        return ChordTimeline(events=[])
    except Exception as exc:
        raise RuntimeError(f"Error loading audio file {audio_path}: {exc}") from exc

    # Verify model is loadable before running expensive chroma extraction
    try:
        _get_interpreter()
    except (FileNotFoundError, RuntimeError) as exc:
        logger.error("Chord model unavailable: %s", exc)
        return ChordTimeline(events=[])

    raw_frames = _run_tflite_raw(y, sr)
    logger.info("Chord inference: %d raw frames from %s", len(raw_frames), audio_path.name)

    track_peak_db = _get_segment_db(y)
    relative_threshold_db = track_peak_db - 30.0

    events: list[ChordEvent] = []
    beats = beat_grid.beats
    frame_times = np.array([f["time"] for f in raw_frames])

    for i in range(len(beats) - 1):
        start_t = beats[i]
        end_t = beats[i + 1]
        start_sample = int(start_t * sr)
        end_sample = int(end_t * sr)
        y_slice = y[start_sample:end_sample]
        segment_db = _get_segment_db(y_slice)
        if segment_db < relative_threshold_db:
            events.append(ChordEvent(timestamp=start_t, chord="N", confidence=1.0))
            continue
        start_idx = int(np.searchsorted(frame_times, start_t, side="left"))
        end_idx = int(np.searchsorted(frame_times, end_t, side="left"))
        window_frames = raw_frames[start_idx:end_idx]
        if not window_frames:
            events.append(
                ChordEvent(timestamp=start_t, chord=events[-1].chord if events else "N", confidence=0.5)
            )
            continue
        chord_confidences: Counter = Counter()
        for f in window_frames:
            chord_confidences[f["chord"]] += f["confidence"]
        if not chord_confidences:
            most_common_chord = "N"
            avg_confidence = 0.5
        else:
            most_common_chord = chord_confidences.most_common(1)[0][0]
            winning_confidences = [f["confidence"] for f in window_frames if f["chord"] == most_common_chord]
            avg_confidence = sum(winning_confidences) / len(winning_confidences)
        events.append(ChordEvent(timestamp=start_t, chord=most_common_chord, confidence=round(avg_confidence, 3)))

    events = _smooth_chords(events)
    chord_count = len([e for e in events if e.chord != "N"])
    logger.info("Chord inference complete: %d/%d non-N chords", chord_count, len(events))
    return ChordTimeline(events=events)
