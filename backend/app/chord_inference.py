"""TFLite Chord Inference with Viterbi Decoding (Commit 99).

Pipeline:
  Audio → TFLite → enriched beat pooling → half-beat tie-detection
       → Viterbi decoding → metrics → ChordTimeline

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

_MODEL_PATH = Path(__file__).parent / "chord_model.tflite"
_WINDOW = 128
_HOP_SEC = 0.1
_BINS_PER_OCTAVE = 12
_NUM_OCTAVES = 3
_CHROMA_BINS = _BINS_PER_OCTAVE * _NUM_OCTAVES  # 36
_BASS_BINS = 4
_FEATURE_DIM = _CHROMA_BINS + _BASS_BINS         # 40
_BATCH_CHUNK = 512

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


@lru_cache(maxsize=1)
def _get_interpreter():
    """Load the TFLite interpreter once and cache it for the process lifetime."""
    path = str(_MODEL_PATH)
    if not _MODEL_PATH.exists():
        raise FileNotFoundError(f"Chord model not found at {_MODEL_PATH}")

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


def _build_windows(features: np.ndarray) -> np.ndarray:
    """Build batched sliding windows from feature sequence.

    Returns array of shape [T, _WINDOW, _FEATURE_DIM].
    """
    T = len(features)
    half = _WINDOW // 2
    pad = np.zeros((half, _FEATURE_DIM), dtype=np.float32)
    padded = np.concatenate([pad, features, pad], axis=0)
    windows = np.zeros((T, _WINDOW, _FEATURE_DIM), dtype=np.float32)
    for i in range(T):
        windows[i] = padded[i : i + _WINDOW]
    return windows


def _run_tflite_raw(y: np.ndarray, sr: int) -> list[dict]:
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

    interp = _get_interpreter()
    inp_detail = interp.get_input_details()[0]
    outp_detail = interp.get_output_details()[0]

    T = len(windows)
    all_probs = np.empty((T, _NUM_CLASSES), dtype=np.float32)

    for start in range(0, T, _BATCH_CHUNK):
        end = min(start + _BATCH_CHUNK, T)
        chunk = windows[start:end]
        interp.set_tensor(inp_detail["index"], chunk)
        interp.invoke()
        all_probs[start:end] = interp.get_tensor(outp_detail["index"])

    results = []
    for i in range(T):
        pred_idx = int(np.argmax(all_probs[i]))
        results.append({
            "time": i * _HOP_SEC,
            "chord": CHORD_VOCAB[pred_idx],
            "confidence": float(all_probs[i][pred_idx]),
            "probs": all_probs[i],
        })
    return results


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
    """Pool TFLite frame predictions within a beat window into a full distribution.

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

    try:
        _get_interpreter()
    except (FileNotFoundError, RuntimeError) as exc:
        logger.error("Chord model unavailable: %s. Returning empty timeline.", exc)
        return ChordTimeline(events=[])

    raw_frames = _run_tflite_raw(y, sr)
    logger.info("Chord inference: %d raw frames from %s", len(raw_frames), audio_path.name)

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


def _infer_chords_fallback(
    audio_path: Path,
    beat_grid: BeatGrid,
    y: np.ndarray,
    sr: int,
) -> ChordTimeline:
    """Fallback inference when TFLite model is unavailable.

    NOTE: Currently unreachable — _get_interpreter() failure returns
    empty timeline directly. Kept as a scaffold for future non-ML
    chord estimation (e.g., chroma-based heuristic).
    """
    return ChordTimeline(events=[])
