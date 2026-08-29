"""TFLite Chord Inference with Volume Thresholding and Beat Pooling (Commit 79).

Fixed for ML Inference Stability & Diagnostics (Commit 95):
  - Replaces print() with structured logging.
  - Standardized model loading with backend detection logging.
  - Diagnostics for model mismatch errors.

Segment Boundary Tie Mechanism (Commit 100, MT3 paper insight):
  - Overlap-and-blend: inference windows are placed every _WINDOW_STRIDE
    frames (50% overlap) and per-frame predictions are accumulated with
    triangular weights (1 - distance/half from window center). Frames near a
    window's edge are near the center of a neighboring window, so the
    degraded context at window edges never dominates and boundary flicker is
    suppressed without a separate re-declaration pass.
  - Boundary confidence penalty: predictions within _BOUNDARY_PENALTY_FRAMES
    of the track edges (zero-padded context) have confidence scaled by
    _BOUNDARY_CONFIDENCE_FACTOR to reduce false positives.
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
from app.viterbi import (
    load_transition_matrix,
    postprocess_chords,
    compute_flicker_rate,
    compute_chord_change_histogram,
)

logger = logging.getLogger("harmoniq.inference.chord")

_ROOTS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_CHORD_QUALITIES = [
    "maj", "min",
    "7", "maj7", "min7",
    "9", "min9", "maj9", "11", "13",
    "7#9", "7b9", "7#5", "7b5", "alt7",
    "sus2", "sus4", "7sus4",
    "dim", "dim7", "aug", "6", "min6",
]

CHORD_VOCAB = [f"{root}:{qual}" for qual in _CHORD_QUALITIES for root in _ROOTS] + ["N"]

_MODEL_PATH = Path(__file__).parent / "chord_model.tflite"
_KERAS_MODEL_PATH = Path(__file__).parent / "chord_model.keras"
_WINDOW = 128
_WINDOW_STRIDE = _WINDOW // 2       # 50% overlap between consecutive windows
_BOUNDARY_PENALTY_FRAMES = 2        # confidence penalty zone at track edges (0.2s @ 0.1s hop)
_BOUNDARY_CONFIDENCE_FACTOR = 0.85
_HOP_SEC = 0.1
_BINS_PER_OCTAVE = 12
_NUM_OCTAVES = 3
_CHROMA_BINS = _BINS_PER_OCTAVE * _NUM_OCTAVES  # 36
_BASS_BINS = 4
_FEATURE_DIM = _CHROMA_BINS + _BASS_BINS         # 40


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


def _load_flex_delegate():
    """Try to load the TFLite Flex delegate for SELECT_TF_OPS support.

    Returns a delegate list (empty if Flex is unavailable).
    """
    try:
        import tensorflow as tf

        delegate = tf.lite.experimental.load_delegate("libtensorflowlite_flex.so")
        logger.info("Flex delegate loaded for SELECT_TF_OPS support")
        return [delegate]
    except Exception:
        logger.debug("Flex delegate unavailable — SELECT_TF_OPS ops will fail")
        return []


class _KerasModelWrapper:
    """Thin wrapper around a Keras model that mimics the TFLite Interpreter API.

    Used as a fallback when the TFLite model requires SELECT_TF_OPS and the
    Flex delegate is unavailable.

    Handles both keras (standalone) and tf_keras saves, and registers the
    custom CircularCqtPad layer used by the chord model.
    """

    def __init__(self, model_path: str):
        # Try to register custom layer so Functional load can find it
        try:
            from app.chord_model_layers import CircularCqtPad  # type: ignore

            custom_objects = {"CircularCqtPad": CircularCqtPad}
        except Exception:
            # Fallback: define a minimal stub for load purposes
            try:
                import keras

                @keras.saving.register_keras_serializable(package="Custom", name="CircularCqtPad")
                class _StubCircularCqtPad(keras.layers.Layer):
                    def call(self, inputs):
                        return inputs

                custom_objects = {"CircularCqtPad": _StubCircularCqtPad}
            except Exception:
                custom_objects = {}

        last_exc: Exception | None = None
        # Try keras (standalone, Keras 3) first — matches how build_chord_tflite saves
        for loader in (
            lambda p: __import__("keras").saving.load_model(p, compile=False, custom_objects=custom_objects),  # type: ignore
            lambda p: __import__("tf_keras").models.load_model(p, compile=False, custom_objects=custom_objects),  # type: ignore
            lambda p: __import__("tensorflow").keras.models.load_model(p, compile=False, custom_objects=custom_objects),  # type: ignore
        ):
            try:
                self._model = loader(model_path)  # type: ignore
                break
            except Exception as exc:
                last_exc = exc
                continue
        else:
            raise RuntimeError(f"All Keras loaders failed for {model_path}: {last_exc}") from last_exc

        self._input_details = [{"index": 0, "shape": self._model.inputs[0].shape}]
        self._output_details = [{"index": 0, "shape": self._model.outputs[0].shape}]
        self._last_input = None

    def get_input_details(self):
        return self._input_details

    def get_output_details(self):
        return self._output_details

    def set_tensor(self, index, value):
        self._last_input = value

    def invoke(self):
        self._output = self._model(self._last_input, training=False)

    def get_tensor(self, index):
        return self._output.numpy()

    def allocate_tensors(self):
        pass  # No-op for Keras


@lru_cache(maxsize=1)
def _get_interpreter():
    """Load the model once and cache it for the process lifetime.

    Tries tflite-runtime first (with Flex delegate if available), falls back
    to TensorFlow Lite, then falls back to the Keras model directly.
    """
    path = str(_MODEL_PATH)
    if not _MODEL_PATH.exists() and not _KERAS_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Neither chord model found at {_MODEL_PATH} nor {_KERAS_MODEL_PATH}"
        )

    # Try tflite-runtime (lighter dependency)
    try:
        import tflite_runtime.interpreter as tflite

        flex_delegates = _load_flex_delegate()
        interp = tflite.Interpreter(
            model_path=path,
            experimental_delegates=flex_delegates or None,
        )
        logger.info("Chord model loaded via tflite-runtime")
        interp.allocate_tensors()
        return interp
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("TFLite load failed (%s), trying Keras fallback", exc)

    # Fall back to TensorFlow Lite
    try:
        import tensorflow as tf

        flex_delegates = _load_flex_delegate()
        interp = tf.lite.Interpreter(
            model_path=path,
            experimental_delegates=flex_delegates or None,
        )
        logger.info("Chord model loaded via TensorFlow Lite")
        interp.allocate_tensors()
        return interp
    except Exception as exc:
        logger.warning("TFLite interpreter failed (%s), trying Keras model", exc)

    # Fall back to Keras model directly (no Flex delegate needed)
    if _KERAS_MODEL_PATH.exists():
        try:
            wrapper = _KerasModelWrapper(str(_KERAS_MODEL_PATH))
            logger.info("Chord model loaded via Keras (fallback)")
            return wrapper
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load Keras chord model at {_KERAS_MODEL_PATH}: {exc}"
            ) from exc

    raise RuntimeError(
        "Chord inference requires tflite-runtime or tensorflow. "
        "Install with: pip install tflite-runtime"
    )


def _window_layout(T: int) -> tuple[list[int], np.ndarray]:
    """Return the 50%-overlap window layout for a feature sequence.

    Args:
        T: Number of feature frames.

    Returns:
        (centers, frame_weights) where ``centers`` holds the feature-frame
        index at the middle of each inference window (windows are ``_WINDOW``
        frames long, strided by ``_WINDOW_STRIDE``) and ``frame_weights`` is
        an array of shape ``(len(centers), T)`` with the triangular weight
        ``1 - |f - center| / half`` each window contributes to every frame.
        Every frame is covered by at least one window; frames in the overlap
        zone are covered by two, weighted toward the nearer center.
    """
    if T <= 0:
        return [], np.zeros((0, 0), dtype=np.float64)
    half = _WINDOW // 2
    centers = list(range(0, T, _WINDOW_STRIDE))
    frame_weights = np.zeros((len(centers), T), dtype=np.float64)
    for k, c in enumerate(centers):
        f_start = max(0, c - half)
        f_end = min(T, c + half)
        for f in range(f_start, f_end):
            frame_weights[k, f] = 1.0 - abs(f - c) / half
    return centers, frame_weights


def _predict_overlap_blend(features: np.ndarray) -> tuple[list[dict], int]:
    """Run TFLite on 50%-overlapping windows and blend per-frame predictions.

    Windows are placed every ``_WINDOW_STRIDE`` frames; the predictions each
    window produces are accumulated per frame with triangular weights (see
    ``_window_layout``). The final per-frame prediction is the argmax of the
    weight-normalized accumulation, so a frame sitting at the edge of one
    window is dominated by the neighboring window that has it near its
    center. This is the MT3-inspired overlap-and-blend: a chord held across a
    window boundary is emitted as one stable event instead of flickering
    between the two windows' predictions.

    Returns (results, number_of_windows_blended).
    """
    interp = _get_interpreter()
    inp_detail = interp.get_input_details()[0]
    outp_detail = interp.get_output_details()[0]

    T = len(features)
    half = _WINDOW // 2
    pad = np.zeros((half, _FEATURE_DIM), dtype=np.float32)
    padded = np.concatenate([pad, features, pad], axis=0)

    centers, frame_weights = _window_layout(T)
    acc = np.zeros((T, len(CHORD_VOCAB)), dtype=np.float64)
    weight_sum = np.zeros(T, dtype=np.float64)

    for k, c in enumerate(centers):
        window = padded[c : c + _WINDOW]
        if len(window) < _WINDOW:
            window = np.concatenate(
                [window, np.zeros((_WINDOW - len(window), _FEATURE_DIM), dtype=np.float32)],
                axis=0,
            )
        interp.set_tensor(inp_detail["index"], window[np.newaxis, :, :])
        interp.invoke()
        probs = interp.get_tensor(outp_detail["index"])[0].astype(np.float64)
        acc += frame_weights[k][:, None] * probs[None, :]
        weight_sum += frame_weights[k]

    results = []
    for f in range(T):
        if weight_sum[f] <= 0:
            pred_idx = 0
            confidence = 0.0
        else:
            blended = acc[f] / weight_sum[f]
            pred_idx = int(np.argmax(blended))
            confidence = float(blended[pred_idx])
        results.append({
            "time": f * _HOP_SEC,
            "chord": CHORD_VOCAB[pred_idx],
            "confidence": confidence,
        })
    return results, len(centers)


def _apply_boundary_penalty(results: list[dict]) -> int:
    """Scale down confidence of predictions within edge frames of the track.

    The first/last ``_BOUNDARY_PENALTY_FRAMES`` frames sit at the ends of the
    feature sequence where the window context is zero-padded — the model's
    least reliable region. Confidence is multiplied by
    ``_BOUNDARY_CONFIDENCE_FACTOR`` there, reducing false positives at
    segment edges. Returns the number of penalized frames.
    """
    n = len(results)
    if n == 0:
        return 0
    edge = min(_BOUNDARY_PENALTY_FRAMES, (n + 1) // 2)
    penalized = 0
    for i in range(n):
        if i < edge or i >= n - edge:
            results[i]["confidence"] *= _BOUNDARY_CONFIDENCE_FACTOR
            penalized += 1
    return penalized


def _edge_flicker_events(results: list[dict], boundary_frames: int = _BOUNDARY_PENALTY_FRAMES) -> int:
    """Count raw-frame chord changes occurring inside the boundary zones.

    These are exactly the segment-edge flicker events that overlap-and-blend
    and the boundary confidence penalty are designed to suppress. Exposed as
    a per-job metric so boundary flicker is observable.
    """
    n = len(results)
    if n < 2:
        return 0
    edge = min(boundary_frames, (n + 1) // 2)
    zones = set(range(edge)) | set(range(n - edge, n))
    return sum(
        1
        for i in range(1, n)
        if results[i]["chord"] != results[i - 1]["chord"] and (i in zones or i - 1 in zones)
    )


def _run_tflite_raw(y: np.ndarray, sr: int) -> list[dict]:
    import librosa

    hop = int(sr * _HOP_SEC)

    # Extract 36-bin CQT
    cqt = librosa.cqt(y=y, sr=sr, hop_length=hop, n_bins=36, bins_per_octave=12)
    cqt = np.abs(cqt)
    cqt = cqt.T.astype(np.float32)

    # Normalize per frame
    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    cqt = cqt / norms

    # Extract bass channel (bins 0-3)
    bass = cqt[:, :4]

    # Concatenate: [36 CQT + 4 bass] = [T, 40]
    features = np.concatenate([cqt, bass], axis=1)

    # Overlap-and-blend inference (Commit 100: MT3 tie mechanism)
    results, blend_windows = _predict_overlap_blend(features)
    logger.info("Chord inference: blended %d overlapping windows", blend_windows)

    penalized = _apply_boundary_penalty(results)
    logger.info("Chord inference: boundary confidence penalty applied to %d frames", penalized)

    edge_flicker = _edge_flicker_events(results)
    logger.info("Chord inference: %d edge-flicker events after blending", edge_flicker)

    return results


def _boundary_metrics_for_frames(results: list[dict]) -> dict:
    """Recompute the Commit 100 boundary-tie metrics for a raw frame list.

    Pure and cheap, so callers (including tests that mock
    ``_run_tflite_raw``) can always produce a consistent metrics dict from
    whatever frame list was actually consumed.
    """
    T = len(results)
    edge = min(_BOUNDARY_PENALTY_FRAMES, (T + 1) // 2)
    return {
        "blend_windows": len(_window_layout(T)[0]),
        "boundary_frames_penalized": sum(1 for i in range(T) if i < edge or i >= T - edge),
        "edge_flicker_events": _edge_flicker_events(results),
    }


def infer_chords(
    audio_path: Path,
    beat_grid: BeatGrid,
    key_signature: str | None = None,
) -> tuple[ChordTimeline, dict]:
    """Run TFLite chord inference with Viterbi post-processing.

    Args:
        audio_path: Path to the audio file.
        beat_grid: Beat grid for quantization.
        key_signature: Optional key signature (e.g., "C major") for
            key-constrained Viterbi decoding.

    Returns:
        Tuple of (ChordTimeline, metrics dict with flicker rate, beat alignment, etc.).
    """
    try:
        import librosa
    except ImportError as exc:
        raise RuntimeError("librosa is required for chord inference.") from exc

    try:
        y, sr = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
    except FileNotFoundError:
        logger.warning("Audio file not found at %s. Returning empty chord timeline.", audio_path)
        return ChordTimeline(events=[]), {}
    except Exception as exc:
        raise RuntimeError(f"Error loading audio file {audio_path}: {exc}") from exc

    # Verify model is loadable before running expensive chroma extraction
    try:
        _get_interpreter()
    except (FileNotFoundError, RuntimeError) as exc:
        logger.error("Chord model unavailable: %s", exc)
        return ChordTimeline(events=[]), {}

    raw_frames = _run_tflite_raw(y, sr)
    logger.info("Chord inference: %d raw frames from %s", len(raw_frames), audio_path.name)

    track_peak_db = _get_segment_db(y)
    relative_threshold_db = track_peak_db - 30.0

    events: list[ChordEvent] = []
    beats = beat_grid.beats
    frame_times = np.array([f["time"] for f in raw_frames])
    silent_beats: set[int] = set()

    for i in range(len(beats) - 1):
        start_t = beats[i]
        end_t = beats[i + 1]
        start_sample = int(start_t * sr)
        end_sample = int(end_t * sr)
        y_slice = y[start_sample:end_sample]
        segment_db = _get_segment_db(y_slice)
        if segment_db < relative_threshold_db:
            events.append(ChordEvent(timestamp=start_t, chord="N", confidence=1.0))
            silent_beats.add(i)
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

    # Viterbi post-processing (replaces simple _smooth_chords)
    transition_matrix = load_transition_matrix()
    smoothed, metrics = postprocess_chords(
        events=events,
        beats=beats,
        downbeats=beat_grid.downbeats,
        transition_matrix=transition_matrix,
        key_signature=key_signature,
        frame_predictions=raw_frames,
    )
    # Commit 100: surface segment-boundary tie metrics (overlap blend windows,
    # edge confidence penalties, and the edge flicker those mechanisms suppress).
    metrics = {**metrics, **_boundary_metrics_for_frames(raw_frames)}

    # Re-apply volume-thresholded silence: beats that were gated to "N"
    # must remain "N" regardless of Viterbi's smoothing.
    re_applied = []
    for i, ev in enumerate(smoothed.events):
        if i in silent_beats and ev.chord != "N":
            re_applied.append(ChordEvent(
                timestamp=ev.timestamp,
                chord="N",
                confidence=1.0,
            ))
        else:
            re_applied.append(ev)
    smoothed = ChordTimeline(events=re_applied)

    chord_count = len([e for e in smoothed.events if e.chord != "N"])
    logger.info(
        "Chord inference complete: %d/%d non-N chords, flicker=%.2f%%, beat_align=%.1f%%",
        chord_count,
        len(smoothed.events),
        metrics.get("flicker_rate", 0) * 100,
        metrics.get("beat_alignment_downbeat", 0) * 100,
    )
    return smoothed, metrics
