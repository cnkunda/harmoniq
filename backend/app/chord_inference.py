"""Chord Inference with Viterbi Decoding (Commit 99).

Pipeline:
  Audio → CRNN (Keras or TFLite) → enriched beat pooling
       → half-beat tie-detection → Viterbi decoding → metrics → ChordTimeline

Inference chain (auto-selects best available):
  1. Keras model (.keras) — full CRNN, Python backend only
  2. TFLite model (.tflite) — mobile-optimized, requires Flex delegate
  3. Chroma template matching — pure librosa, always available

Replaces the old _smooth_chords median filter with statistically optimal
Viterbi sequence decoding using a music-theory transition matrix.
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.schemas import BeatGrid, ChordEvent, ChordTimeline
from app.pipeline_proof import TARGET_SR
from app.chord_vocab import CHORD_INTERVALS as _CHORD_INTERVALS

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
_CHORD_TO_IDX = {chord: i for i, chord in enumerate(CHORD_VOCAB)}
_NUM_CLASSES = len(CHORD_VOCAB)  # 277

_TFLITE_PATH = Path(__file__).parent / "chord_model.tflite"
_KERAS_PATH = Path(__file__).parent / "chord_model.keras"
_WINDOW = 128
_HOP_FRAMES = 64  # 50% overlap (Commit 100)
_HOP_SEC = 0.1
_BINS_PER_OCTAVE = 12
_NUM_OCTAVES = 3
_CHROMA_BINS = _BINS_PER_OCTAVE * _NUM_OCTAVES  # 36
_BASS_BINS = 4
_FEATURE_DIM = _CHROMA_BINS + _BASS_BINS         # 40
_BATCH_CHUNK = 512

# Precomputed triangular window for overlap-and-blend (Commit 100)
_TRIANGULAR_WINDOW = np.minimum(
    np.arange(_WINDOW) / (_WINDOW / 2),
    (_WINDOW - 1 - np.arange(_WINDOW)) / (_WINDOW / 2 - 1)
).astype(np.float32)

TIE_THRESHOLD = 0.15
SUBDIVISION_RATIO = 0.65


def _get_segment_db(y_segment: np.ndarray) -> float:
    if len(y_segment) == 0:
        return -100.0
    rms = np.sqrt(np.mean(y_segment**2))
    if rms < 1e-9:
        return -100.0
    return float(20 * math.log10(rms))


def _smooth_chords(events: list[ChordEvent]) -> list[ChordEvent]:
    """Fallback 3-point median filter. Kept for compatibility; Viterbi replaces this."""
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


# ---------------------------------------------------------------------------
# Model loading: Keras (primary) → TFLite (mobile) → Chroma (fallback)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_keras_model():
    """Load the full Keras CRNN model for Python backend inference.

    Returns the model or raises if .keras file is missing/unloadable.
    """
    if not _KERAS_PATH.exists():
        raise FileNotFoundError(f"Keras model not found at {_KERAS_PATH}")

    import os
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
    import tensorflow as tf

    model = tf.keras.models.load_model(str(_KERAS_PATH))
    logger.info("Chord model loaded via Keras (%s)", _KERAS_PATH.name)
    return model


@lru_cache(maxsize=1)
def _get_interpreter():
    """Load the TFLite interpreter once and cache it for the process lifetime."""
    path = str(_TFLITE_PATH)
    if not _TFLITE_PATH.exists():
        raise FileNotFoundError(f"TFLite model not found at {_TFLITE_PATH}")

    try:
        import tflite_runtime.interpreter as tflite

        interp = tflite.Interpreter(model_path=path)
        logger.info("Chord model loaded via tflite-runtime")
    except ImportError:
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


def _extract_features(y: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    """Extract CQT features and build sliding windows.

    Returns:
        (windows, hop) where windows has shape [T_overlap, _WINDOW, _FEATURE_DIM]
    """
    import librosa

    hop = int(sr * _HOP_SEC)
    cqt = librosa.cqt(y=y, sr=sr, hop_length=hop, n_bins=36, bins_per_octave=12)
    cqt = np.abs(cqt)
    cqt = cqt.T.astype(np.float32)

    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    cqt = cqt / norms

    bass = cqt[:, :4]
    features = np.concatenate([cqt, bass], axis=1)
    windows = _build_windows(features)
    return windows, hop


def _build_windows(features: np.ndarray) -> np.ndarray:
    """Build overlapping sliding windows from feature sequence.

    Uses 50% overlap (hop = _HOP_FRAMES) with symmetric padding.

    Returns array of shape [T_overlap, _WINDOW, _FEATURE_DIM].
    """
    T = len(features)
    pad = np.zeros((_WINDOW // 2, _FEATURE_DIM), dtype=np.float32)
    padded = np.concatenate([pad, features, pad], axis=0)

    T_overlap = (T + _HOP_FRAMES - 1) // _HOP_FRAMES
    windows = np.zeros((T_overlap, _WINDOW, _FEATURE_DIM), dtype=np.float32)
    for k in range(T_overlap):
        start = k * _HOP_FRAMES
        windows[k] = padded[start : start + _WINDOW]
    return windows


def _merge_overlapping_predictions(
    window_probs: np.ndarray,
    num_frames: int,
) -> np.ndarray:
    """Merge per-window predictions using triangular windowing overlap-and-blend.

    Args:
        window_probs: Shape [T_overlap, _WINDOW, _NUM_CLASSES], per-frame
            probability distributions from each overlapping window.
        num_frames: Original frame count T (before padding/overlap).

    Returns:
        Merged probabilities of shape [T, _NUM_CLASSES].
    """
    T_overlap, W, N = window_probs.shape
    accum_probs = np.zeros((num_frames, N), dtype=np.float64)
    accum_weights = np.zeros(num_frames, dtype=np.float64)

    for k in range(T_overlap):
        for p in range(W):
            f = k * _HOP_FRAMES + p - _WINDOW // 2
            if 0 <= f < num_frames:
                w = float(_TRIANGULAR_WINDOW[p])
                accum_weights[f] += w
                accum_probs[f] += w * window_probs[k, p]

    merged = accum_probs / accum_weights[:, None].clip(1e-8)
    return merged.astype(np.float32)


_BOUNDARY_PENALTY_FRAMES = 2
_BOUNDARY_PENALTY_MIN = 0.7


def _apply_boundary_penalty(probs: np.ndarray) -> np.ndarray:
    """Apply multiplicative confidence penalty near internal window boundaries.

    Reduces confidence for frames within _BOUNDARY_PENALTY_FRAMES of every
    original non-overlapping window edge (every _WINDOW frames). This makes
    the Viterbi decoder prefer self-transitions at boundaries, reducing
    spurious chord changes.

    Probabilities are re-normalized after penalty to preserve emission strength.

    Args:
        probs: Shape [T, _NUM_CLASSES], merged probability distributions.

    Returns:
        Penalized and re-normalized probabilities (rows sum to 1.0).
    """
    T = probs.shape[0]
    result = probs.copy()

    boundary_indices = list(range(_WINDOW, T, _WINDOW))

    for b in boundary_indices:
        for d in range(-_BOUNDARY_PENALTY_FRAMES, _BOUNDARY_PENALTY_FRAMES + 1):
            idx = b + d
            if 0 <= idx < T:
                distance = abs(d)
                if distance == 0:
                    penalty = _BOUNDARY_PENALTY_MIN
                else:
                    penalty = _BOUNDARY_PENALTY_MIN + (1.0 - _BOUNDARY_PENALTY_MIN) * (distance / _BOUNDARY_PENALTY_FRAMES)
                result[idx] *= penalty

    # Re-normalize to preserve emission strength
    row_sums = result.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums == 0, 1.0, row_sums)
    result = result / row_sums

    return result


def _run_keras_raw(y: np.ndarray, sr: int) -> list[dict]:
    """Run inference using the full Keras CRNN model."""
    windows, hop = _extract_features(y, sr)
    model = _get_keras_model()

    T_overlap = len(windows)
    T = T_overlap * _HOP_FRAMES - _WINDOW // 2

    window_outputs = np.empty((T_overlap, _WINDOW, _NUM_CLASSES), dtype=np.float32)

    for start in range(0, T_overlap, _BATCH_CHUNK):
        end = min(start + _BATCH_CHUNK, T_overlap)
        chunk = windows[start:end]
        pred = model.predict(chunk, verbose=0)
        window_outputs[start:end] = pred.reshape(end - start, _WINDOW, _NUM_CLASSES)

    merged_probs = _merge_overlapping_predictions(window_outputs, T)

    results = []
    for i in range(T):
        pred_idx = int(np.argmax(merged_probs[i]))
        results.append({
            "time": i * _HOP_SEC,
            "chord": CHORD_VOCAB[pred_idx],
            "confidence": float(merged_probs[i][pred_idx]),
            "probs": merged_probs[i],
        })
    return results


def _run_tflite_raw(y: np.ndarray, sr: int) -> list[dict]:
    """Run inference using the TFLite model (requires Flex delegate for CRNN)."""
    windows, hop = _extract_features(y, sr)

    interp = _get_interpreter()
    inp_detail = interp.get_input_details()[0]
    outp_detail = interp.get_output_details()[0]

    T_overlap = len(windows)
    T = T_overlap * _HOP_FRAMES - _WINDOW // 2

    window_outputs = np.empty((T_overlap, _WINDOW, _NUM_CLASSES), dtype=np.float32)

    for start in range(0, T_overlap, _BATCH_CHUNK):
        end = min(start + _BATCH_CHUNK, T_overlap)
        chunk = windows[start:end]
        interp.set_tensor(inp_detail["index"], chunk)
        interp.invoke()
        output = interp.get_tensor(outp_detail["index"])
        window_outputs[start:end] = output.reshape(end - start, _WINDOW, _NUM_CLASSES)

    merged_probs = _merge_overlapping_predictions(window_outputs, T)

    results = []
    for i in range(T):
        pred_idx = int(np.argmax(merged_probs[i]))
        results.append({
            "time": i * _HOP_SEC,
            "chord": CHORD_VOCAB[pred_idx],
            "confidence": float(merged_probs[i][pred_idx]),
            "probs": merged_probs[i],
        })
    return results


def _run_chroma_raw(y: np.ndarray, sr: int, hop_length: int = 512) -> list[dict]:
    """Run chord estimation via chroma template matching (no neural model needed).

    Uses cosine similarity between per-frame chroma vectors and chord templates
    built from music-theory intervals. Less accurate than the CRNN but always
    available.
    """
    import librosa

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
    chroma = chroma.T.astype(np.float32)

    templates = _build_chroma_templates()

    T = len(chroma)
    all_probs = np.zeros((T, _NUM_CLASSES), dtype=np.float32)

    for i in range(T):
        frame = chroma[i]
        norm = np.linalg.norm(frame)
        if norm < 1e-8:
            all_probs[i, _CHORD_TO_IDX["N"]] = 1.0
            continue

        frame_norm = frame / norm
        similarities = templates @ frame_norm

        softmax_sim = similarities - similarities.max()
        exp_sim = np.exp(softmax_sim * 5.0)
        exp_sim /= exp_sim.sum()
        all_probs[i] = exp_sim

    chroma_times = librosa.frames_to_time(np.arange(T), sr=sr, hop_length=hop_length)

    results = []
    for i in range(T):
        pred_idx = int(np.argmax(all_probs[i]))
        results.append({
            "time": float(chroma_times[i]),
            "chord": CHORD_VOCAB[pred_idx],
            "confidence": float(all_probs[i][pred_idx]),
            "probs": all_probs[i],
        })
    return results


def _run_inference(y: np.ndarray, sr: int) -> list[dict]:
    """Run chord inference using the best available model.

    Chain: Keras → TFLite → Chroma template matching.
    """
    try:
        raw_frames = _run_keras_raw(y, sr)
        logger.info("Chord inference: %d frames (Keras CRNN)", len(raw_frames))
        return raw_frames
    except Exception as exc:
        logger.warning("Keras inference unavailable: %s", exc)

    try:
        raw_frames = _run_tflite_raw(y, sr)
        logger.info("Chord inference: %d frames (TFLite CRNN)", len(raw_frames))
        return raw_frames
    except Exception as exc:
        logger.warning("TFLite inference unavailable: %s", exc)

    raw_frames = _run_chroma_raw(y, sr)
    logger.warning("Falling back to chroma template matching (%d frames)", len(raw_frames))
    return raw_frames


# ---------------------------------------------------------------------------
# Chroma template cache
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _build_chroma_templates() -> np.ndarray:
    """Build 12-bin chroma templates for all 277 chord classes.

    Returns:
        np.ndarray of shape [277, 12], row-normalized.
    """
    templates = np.zeros((_NUM_CLASSES, 12), dtype=np.float32)

    for idx, chord_label in enumerate(CHORD_VOCAB):
        if chord_label == "N":
            templates[idx] = 1.0 / 12
            continue

        root_str, quality = chord_label.split(":")
        root_idx = _ROOTS.index(root_str)
        intervals = _CHORD_INTERVALS.get(quality, [0, 4, 7])

        template = np.zeros(12, dtype=np.float32)
        for semitone in intervals:
            pitch_class = (root_idx + semitone) % 12
            weight = 1.0 if semitone <= 12 else 0.7
            template[pitch_class] += weight
            template[(pitch_class + 7) % 12] += 0.3

        norm = np.linalg.norm(template)
        if norm > 0:
            template /= norm
        templates[idx] = template

    return templates


# ---------------------------------------------------------------------------
# Beat pooling, half-beat detection, key estimation
# ---------------------------------------------------------------------------

def _detect_resolution_mode(beats: list[float], bpm: float) -> str:
    """Detect if the beat grid is already at half-beat (8th-note) resolution.

    Returns:
        "half-beat" if median inter-beat interval < 65% of expected quarter-note.
        "beat" otherwise.
    """
    if len(beats) < 3:
        return "beat"

    intervals = np.diff(beats)
    median_interval = float(np.median(intervals))
    expected_qn = 60.0 / bpm if bpm > 0 else 0.5

    if median_interval < expected_qn * SUBDIVISION_RATIO:
        return "half-beat"
    return "beat"


def _pool_beat_window(
    window_frames: list[dict],
    start_t: float,
    end_t: float,
) -> dict:
    """Pool frame predictions within a beat window into a full distribution.

    Returns:
        Dict with timestamp, probs [277], top candidates, confidence gap,
        first/second half distributions, and metadata.
    """
    probs_sum = np.zeros(_NUM_CLASSES, dtype=np.float64)
    first_half_sum = np.zeros(_NUM_CLASSES, dtype=np.float64)
    second_half_sum = np.zeros(_NUM_CLASSES, dtype=np.float64)
    mid_t = (start_t + end_t) / 2

    for f in window_frames:
        p = f["probs"]
        probs_sum += p
        if f["time"] < mid_t:
            first_half_sum += p
        else:
            second_half_sum += p

    total = probs_sum.sum()
    if total > 0:
        probs = probs_sum / total
        first_half = first_half_sum / max(first_half_sum.sum(), 1e-10)
        second_half = second_half_sum / max(second_half_sum.sum(), 1e-10)
    else:
        probs = np.ones(_NUM_CLASSES, dtype=np.float64) / _NUM_CLASSES
        first_half = probs.copy()
        second_half = probs.copy()

    top_idx = int(np.argmax(probs))
    top_conf = float(probs[top_idx])

    second_probs = probs.copy()
    second_probs[top_idx] = -1
    second_idx = int(np.argmax(second_probs))
    second_conf = float(probs[second_idx])

    first_half_top = int(np.argmax(first_half))
    second_half_top = int(np.argmax(second_half))

    return {
        "timestamp": start_t,
        "probs": probs.astype(np.float32),
        "top_chord_idx": top_idx,
        "top_confidence": top_conf,
        "second_chord_idx": second_idx,
        "second_confidence": second_conf,
        "confidence_gap": top_conf - second_conf,
        "frame_count": len(window_frames),
        "duration_sec": end_t - start_t,
        "first_half_probs": first_half.astype(np.float32),
        "second_half_probs": second_half.astype(np.float32),
        "first_half_top": first_half_top,
        "second_half_top": second_half_top,
    }


def _split_half_beat(beat_data: dict) -> list[dict]:
    """Split a beat into two half-beat events when tie-detection triggers.

    Trigger: confidence_gap < 0.15 AND first_half_top != second_half_top.

    Returns:
        List of two beat-data dicts (first half, second half).
    """
    duration = beat_data["duration_sec"]
    half_dur = duration / 2

    first = {
        "timestamp": beat_data["timestamp"],
        "probs": beat_data["first_half_probs"],
        "top_chord_idx": beat_data["first_half_top"],
        "top_confidence": float(beat_data["first_half_probs"][beat_data["first_half_top"]]),
        "second_chord_idx": 0,
        "second_confidence": 0.0,
        "confidence_gap": 0.0,
        "frame_count": beat_data["frame_count"],
        "duration_sec": half_dur,
        "is_half_beat": True,
    }

    second = {
        "timestamp": beat_data["timestamp"] + half_dur,
        "probs": beat_data["second_half_probs"],
        "top_chord_idx": beat_data["second_half_top"],
        "top_confidence": float(beat_data["second_half_probs"][beat_data["second_half_top"]]),
        "second_chord_idx": 0,
        "second_confidence": 0.0,
        "confidence_gap": 0.0,
        "frame_count": beat_data["frame_count"],
        "duration_sec": half_dur,
        "is_half_beat": True,
    }

    return [first, second]


def _estimate_key_from_audio(y: np.ndarray, sr: int) -> tuple[int, str, float]:
    """Estimate musical key using Krumhansl-Schmuckler correlation.

    Returns:
        (key_root_0_11, mode_str, confidence_float)
    """
    import librosa

    KS_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    KS_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_mean = chroma.mean(axis=1)
    except Exception:
        return 0, "major", 0.0

    chroma_list = chroma_mean.tolist()
    if len(chroma_list) != 12:
        return 0, "major", 0.0

    best_corr = -math.inf
    best: tuple[int, str] = (0, "major")

    for mode, profile in [("major", KS_MAJOR), ("minor", KS_MINOR)]:
        for shift in range(12):
            rotated = profile[shift:] + profile[:shift]
            c = sum(a * b for a, b in zip(chroma_list, rotated))
            if c > best_corr:
                best_corr = c
                best = (shift, mode)

    confidence = min(best_corr / 50.0, 1.0)
    return best[0], best[1], confidence


# ---------------------------------------------------------------------------
# Main inference entry point
# ---------------------------------------------------------------------------

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

    raw_frames = _run_inference(y, sr)

    if raw_frames and "probs" in raw_frames[0]:
        all_probs = np.array([f["probs"] for f in raw_frames])
        penalized_probs = _apply_boundary_penalty(all_probs)
        for i, f in enumerate(raw_frames):
            f["probs"] = penalized_probs[i]
            pred_idx = int(np.argmax(penalized_probs[i]))
            f["chord"] = CHORD_VOCAB[pred_idx]
            f["confidence"] = float(penalized_probs[i][pred_idx])

    track_peak_db = _get_segment_db(y)
    relative_threshold_db = track_peak_db - 30.0

    beats = beat_grid.beats
    if len(beats) < 2:
        return ChordTimeline(events=[])

    frame_times = np.array([f["time"] for f in raw_frames])

    resolution_mode = _detect_resolution_mode(beats, beat_grid.bpm)
    logger.info("Beat grid resolution mode: %s (bpm=%.1f)", resolution_mode, beat_grid.bpm)

    beat_data_list: list[dict] = []

    for i in range(len(beats) - 1):
        start_t = beats[i]
        end_t = beats[i + 1]
        start_sample = int(start_t * sr)
        end_sample = int(end_t * sr)
        y_slice = y[start_sample:end_sample]
        segment_db = _get_segment_db(y_slice)

        if segment_db < relative_threshold_db:
            n_probs = np.zeros(_NUM_CLASSES, dtype=np.float32)
            n_idx = _CHORD_TO_IDX.get("N", _NUM_CLASSES - 1)
            n_probs[n_idx] = 1.0
            beat_data_list.append({
                "timestamp": start_t,
                "probs": n_probs,
                "top_chord_idx": n_idx,
                "top_confidence": 1.0,
                "second_chord_idx": 0,
                "second_confidence": 0.0,
                "confidence_gap": 1.0,
                "frame_count": 0,
                "duration_sec": end_t - start_t,
                "first_half_probs": n_probs.copy(),
                "second_half_probs": n_probs.copy(),
                "first_half_top": n_idx,
                "second_half_top": n_idx,
                "is_half_beat": False,
            })
            continue

        start_idx = int(np.searchsorted(frame_times, start_t, side="left"))
        end_idx = int(np.searchsorted(frame_times, end_t, side="left"))
        window_frames = raw_frames[start_idx:end_idx]

        if not window_frames:
            prev_chord = beat_data_list[-1]["top_chord_idx"] if beat_data_list else _CHORD_TO_IDX.get("N", _NUM_CLASSES - 1)
            prev_probs = np.zeros(_NUM_CLASSES, dtype=np.float32)
            prev_probs[prev_chord] = 1.0
            beat_data_list.append({
                "timestamp": start_t,
                "probs": prev_probs,
                "top_chord_idx": prev_chord,
                "top_confidence": 0.5,
                "second_chord_idx": 0,
                "second_confidence": 0.0,
                "confidence_gap": 0.5,
                "frame_count": 0,
                "duration_sec": end_t - start_t,
                "first_half_probs": prev_probs.copy(),
                "second_half_probs": prev_probs.copy(),
                "first_half_top": prev_chord,
                "second_half_top": prev_chord,
                "is_half_beat": False,
            })
            continue

        bd = _pool_beat_window(window_frames, start_t, end_t)
        bd["is_half_beat"] = False
        beat_data_list.append(bd)

    if resolution_mode == "beat":
        expanded_data: list[dict] = []
        for bd in beat_data_list:
            if (
                bd["confidence_gap"] < TIE_THRESHOLD
                and bd["frame_count"] >= 2
                and bd["first_half_top"] != bd["second_half_top"]
                and bd["probs"][bd["first_half_top"]] != 1.0
            ):
                splits = _split_half_beat(bd)
                expanded_data.extend(splits)
                logger.debug(
                    "Half-beat split at t=%.2f: %s → %s",
                    bd["timestamp"],
                    CHORD_VOCAB[splits[0]["top_chord_idx"]],
                    CHORD_VOCAB[splits[1]["top_chord_idx"]],
                )
            else:
                expanded_data.append(bd)
        beat_data_list = expanded_data
    else:
        for bd in beat_data_list:
            bd["is_half_beat"] = True

    T = len(beat_data_list)
    emission_probs = np.zeros((T, _NUM_CLASSES), dtype=np.float32)
    duration_beats_arr = np.zeros(T, dtype=np.float32)
    timestamps = np.zeros(T, dtype=np.float64)

    beat_unit = 60.0 / beat_grid.bpm if beat_grid.bpm > 0 else 0.5

    for t, bd in enumerate(beat_data_list):
        emission_probs[t] = bd["probs"]
        duration_beats_arr[t] = bd["duration_sec"] / beat_unit
        timestamps[t] = bd["timestamp"]

    key_root, key_mode, key_conf = _estimate_key_from_audio(y, sr)
    logger.info("Detected key: %s %s (confidence=%.2f)", _ROOTS[key_root], key_mode, key_conf)

    try:
        from app.chord_transitions import (
            apply_key_constraint,
            get_transition_matrix,
        )
        from app.viterbi_decoder import ViterbiChordDecoder, probs_to_log_probs

        base_matrix = get_transition_matrix()

        if key_conf >= 0.3:
            trans_matrix = apply_key_constraint(base_matrix, key_root, key_mode)
        else:
            trans_matrix = base_matrix
            logger.info("Key confidence low (%.2f), using unconstrained transition matrix", key_conf)

        trans_log_probs = probs_to_log_probs(trans_matrix)
        emission_log_probs = probs_to_log_probs(emission_probs)

        decoder = ViterbiChordDecoder(
            transition_log_probs=trans_log_probs,
            vocab_size=_NUM_CLASSES,
            chord_vocab=CHORD_VOCAB,
        )

        optimal_path, _ = decoder.decode(
            emission_log_probs,
            duration_beats=duration_beats_arr,
            duration_penalty_weight=0.5,
        )

        events: list[ChordEvent] = []
        for t in range(T):
            chord_idx = int(optimal_path[t])
            events.append(ChordEvent(
                timestamp=float(timestamps[t]),
                chord=CHORD_VOCAB[chord_idx],
                confidence=round(float(emission_probs[t, chord_idx]), 3),
            ))

    except Exception as exc:
        logger.error("Viterbi decoding failed: %s. Falling back to beat-pooling + median filter.", exc)
        events = _fallback_to_pooling(beat_data_list)
        events = _smooth_chords(events)

    chord_count = len([e for e in events if e.chord != "N"])
    logger.info("Chord inference complete: %d/%d non-N chords", chord_count, len(events))

    try:
        from app.chord_metrics import assemble_chord_metrics
        metadata = assemble_chord_metrics(events, beat_grid)
    except Exception as exc:
        logger.warning("Failed to compute chord metrics: %s", exc)
        metadata = None

    return ChordTimeline(events=events, metadata=metadata)


def _fallback_to_pooling(beat_data_list: list[dict]) -> list[ChordEvent]:
    """Fallback: use beat-pooling winners without Viterbi."""
    events = []
    for bd in beat_data_list:
        events.append(ChordEvent(
            timestamp=bd["timestamp"],
            chord=CHORD_VOCAB[bd["top_chord_idx"]],
            confidence=round(bd["top_confidence"], 3),
        ))
    return events
