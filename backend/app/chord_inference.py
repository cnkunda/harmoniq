"""TFLite Chord Inference with Volume Thresholding and Beat Pooling (Commit 79)."""

import math
from collections import Counter
from pathlib import Path
import numpy as np

from app.schemas import BeatGrid, ChordEvent, ChordTimeline
from app.pipeline_proof import TARGET_SR

# MVP Vocabulary. Expand this as your model improves.
CHORD_VOCAB = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B", "N"]
SILENCE_THRESHOLD_DB = -40.0 # TODO: Consider making this dynamic or configurable based on overall audio loudness for robustness.

def _get_segment_db(y_segment: np.ndarray) -> float:
    """Calculates the RMS energy of a segment in decibels."""
    if len(y_segment) == 0:
        return -100.0
    rms = np.sqrt(np.mean(y_segment**2))
    if rms < 1e-9:
        return -100.0
    return float(20 * math.log10(rms))

def _run_tflite_raw(y: np.ndarray, sr: int) -> list[dict]:
    """
    MOCK TFLITE WRAPPER.
    Replace this with your actual TFLite interpreter invocation.
    Assume it returns frame-wise predictions every 0.1 seconds.
    """
    # For now, return a dummy list of high-confidence 'C's for compilation purposes.
    duration = len(y) / sr
    frames = int(duration / 0.1)
    return [{"time": i * 0.1, "chord": "C", "confidence": 0.85} for i in range(frames)]

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
    
    events = []
    beats = beat_grid.beats
    
    # 2. Iterate through each beat window (e.g., Beat 1 to Beat 2)
    for i in range(len(beats) - 1):
        start_t = beats[i]
        end_t = beats[i+1]
        
        # Slicing the audio to check physical volume
        start_sample = int(start_t * sr)
        end_sample = int(end_t * sr)
        y_slice = y[start_sample:end_sample]
        
        # --- THE "N" (NO CHORD) STRATEGY ---
        segment_db = _get_segment_db(y_slice)
        if segment_db < SILENCE_THRESHOLD_DB:
            events.append(ChordEvent(timestamp=start_t, chord="N", confidence=1.0))
            continue
        
        # If it's loud enough, pool the ML predictions for this specific window
        window_frames = [f for f in raw_frames if start_t <= f["time"] < end_t]
        
        if not window_frames:
            # Fallback if the window was too small for a model frame
            events.append(ChordEvent(timestamp=start_t, chord=events[-1].chord if events else "N", confidence=0.5))
            continue
            
        # --- CONFIDENCE-WEIGHTED VOTE ---
        # Sum confidences for each chord and pick the one with the highest total confidence
        chord_confidences = Counter()
        for f in window_frames:
            chord_confidences[f["chord"]] += f["confidence"]
        
        if not chord_confidences: # Should not happen if window_frames is not empty, but as a safeguard
            most_common_chord = "N"
            avg_confidence = 0.5 # Default confidence
        else:
            most_common_chord = chord_confidences.most_common(1)[0][0]
            # Calculate the average confidence for the winning chord based on its original frames
            winning_confidences = [f["confidence"] for f in window_frames if f["chord"] == most_common_chord]
            avg_confidence = sum(winning_confidences) / len(winning_confidences)
        
        events.append(ChordEvent(
            timestamp=start_t,
            chord=most_common_chord,
            confidence=round(avg_confidence, 3)
        ))
        
    return ChordTimeline(events=events)