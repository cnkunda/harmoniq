"""TFLite Chord Inference with Volume Thresholding and Beat Pooling (Commit 79)."""

import math
from collections import Counter
from functools import lru_cache
from pathlib import Path
import numpy as np

from app.schemas import BeatGrid, ChordEvent, ChordTimeline
from app.pipeline_proof import TARGET_SR

# Vocabulary — must match CHORD_VOCAB in build_model.py.
CHORD_VOCAB = [
    # Major triads
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
    # Minor triads
    "Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "A#m", "Bm",
    # No chord
    "N",
]

_MODEL_PATH = Path(__file__).parent / "chord_model.tflite"
_WINDOW     = 9      # context frames fed to the model — must match build_model.py
_HOP_SEC    = 0.1   # frame stride in seconds — must match build_model.py


def _get_segment_db(y_segment: np.ndarray) -> float:
    """Calculates the RMS energy of a segment in decibels."""
    if len(y_segment) == 0:
        return -100.0
    rms = np.sqrt(np.mean(y_segment**2))
    if rms < 1e-9:
        return -100.0
    return float(20 * math.log10(rms))


def _smooth_chords(events: list[ChordEvent]) -> list[ChordEvent]:
    """
    Apply hold rule: isolated chords that differ from both neighbors are smoothed.
    Example: C -> G -> C becomes C -> C -> C (G is considered a blip).
    """
    if len(events) < 3:
        return events

    smoothed = events[:]
    for i in range(1, len(events) - 1):
        prev_chord = smoothed[i-1].chord
        curr_chord = smoothed[i].chord
        next_chord = smoothed[i+1].chord

        # If current chord differs from both neighbors, it's a blip - smooth it
        if curr_chord != prev_chord and curr_chord != next_chord and prev_chord == next_chord:
            smoothed[i] = ChordEvent(
                timestamp=smoothed[i].timestamp,
                chord=prev_chord,
                confidence=round(smoothed[i].confidence * 0.8, 3)  # Reduce confidence for smoothed chord
            )

    return smoothed


@lru_cache(maxsize=1)
def _get_interpreter():
    """Load the TFLite interpreter once and cache it for the process lifetime."""
    try:
        import tflite_runtime.interpreter as tflite
        interp = tflite.Interpreter(model_path=str(_MODEL_PATH))
    except ImportError:
        import tensorflow as tf
        interp = tf.lite.Interpreter(model_path=str(_MODEL_PATH))
    interp.allocate_tensors()
    return interp


def _run_tflite_raw(y: np.ndarray, sr: int) -> list[dict]:
    """
    Run frame-wise chord inference using the TFLite model.

    Extracts a CQT chromagram at _HOP_SEC intervals, feeds each frame through
    the model with a sliding context window, and returns a list of predictions:
        [{"time": float, "chord": str, "confidence": float}, ...]
    """
    import librosa

    hop = int(sr * _HOP_SEC)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop, n_chroma=12)
    chroma = chroma.T.astype(np.float32)                            # (T, 12)
    norms  = chroma.sum(axis=1, keepdims=True).clip(1e-8, None)
    chroma = chroma / norms                                         # L1-normalise

    T    = len(chroma)
    half = _WINDOW // 2
    pad  = np.zeros((half, 12), dtype=np.float32)
    padded = np.concatenate([pad, chroma, pad], axis=0)             # (T + WINDOW - 1, 12)

    interp      = _get_interpreter()
    inp_detail  = interp.get_input_details()[0]
    outp_detail = interp.get_output_details()[0]

    results = []
    for i in range(T):
        window = padded[i : i + _WINDOW][np.newaxis]                # (1, WINDOW, 12)
        interp.set_tensor(inp_detail["index"], window)
        interp.invoke()
        probs = interp.get_tensor(outp_detail["index"])[0]          # (NUM_CLASSES,)

        pred_idx = int(np.argmax(probs))
        results.append({
            "time":       i * _HOP_SEC,
            "chord":      CHORD_VOCAB[pred_idx],
            "confidence": float(probs[pred_idx]),
        })

    return results


def infer_chords(audio_path: Path, beat_grid: BeatGrid) -> ChordTimeline:
    """Extracts a beat-aligned chord progression using volume thresholding."""
    try:
        import librosa
    except ImportError as exc:
        raise RuntimeError("librosa is required for chord inference.") from exc

    try:
        y, sr = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
    except FileNotFoundError:
        print(f"WARNING: Audio file not found at {audio_path}. Returning empty chord timeline.")
        return ChordTimeline(events=[])
    except Exception as exc:
        raise RuntimeError(f"Error loading audio file {audio_path}: {exc}") from exc

    # 1. Get raw frame-by-frame predictions from the ML model
    raw_frames = _run_tflite_raw(y, sr)

    # --- RELATIVE SILENCE THRESHOLD ---
    # Calculate threshold relative to track peak (30 dB below peak)
    # This adapts to both loud mastered tracks and quiet acoustic recordings
    track_peak_db = _get_segment_db(y)
    relative_threshold_db = track_peak_db - 30.0

    events = []
    beats  = beat_grid.beats

    # Pre-extract frame times as numpy array for vectorized binary search
    frame_times = np.array([f["time"] for f in raw_frames])

    # 2. Iterate through each beat window (e.g., Beat 1 to Beat 2)
    for i in range(len(beats) - 1):
        start_t = beats[i]
        end_t   = beats[i + 1]

        # Slicing the audio to check physical volume
        start_sample = int(start_t * sr)
        end_sample   = int(end_t * sr)
        y_slice      = y[start_sample:end_sample]

        # --- THE "N" (NO CHORD) STRATEGY ---
        segment_db = _get_segment_db(y_slice)
        if segment_db < relative_threshold_db:
            events.append(ChordEvent(timestamp=start_t, chord="N", confidence=1.0))
            continue

        # If it's loud enough, pool the ML predictions for this specific window
        # Use binary search to find frame indices: O(log N) per beat instead of O(N)
        start_idx    = int(np.searchsorted(frame_times, start_t, side='left'))
        end_idx      = int(np.searchsorted(frame_times, end_t, side='left'))
        window_frames = raw_frames[start_idx:end_idx]

        if not window_frames:
            # Fallback if the window was too small for a model frame
            events.append(ChordEvent(timestamp=start_t, chord=events[-1].chord if events else "N", confidence=0.5))
            continue

        # --- CONFIDENCE-WEIGHTED VOTE ---
        # Sum confidences for each chord and pick the one with the highest total confidence
        chord_confidences = Counter()
        for f in window_frames:
            chord_confidences[f["chord"]] += f["confidence"]

        if not chord_confidences:  # Should not happen if window_frames is not empty, but as a safeguard
            most_common_chord = "N"
            avg_confidence    = 0.5
        else:
            most_common_chord   = chord_confidences.most_common(1)[0][0]
            # Calculate the average confidence for the winning chord based on its original frames
            winning_confidences = [f["confidence"] for f in window_frames if f["chord"] == most_common_chord]
            avg_confidence      = sum(winning_confidences) / len(winning_confidences)

        events.append(ChordEvent(
            timestamp=start_t,
            chord=most_common_chord,
            confidence=round(avg_confidence, 3)
        ))

    # Apply harmonic smoothing to eliminate ML flicker / isolated blips
    events = _smooth_chords(events)

    return ChordTimeline(events=events)
