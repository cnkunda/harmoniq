"""Tests for Commit 79: ML Inference Logic (Chords & Solo)."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from app.chord_inference import _get_segment_db, infer_chords
from app.solo_inference import infer_solo, _snap_to_grid
from app.schemas import BeatGrid

# --- FIXTURES ---

@pytest.fixture
def mock_beat_grid():
    """A standard 120 BPM 4/4 grid: Beats every 0.5 seconds."""
    return BeatGrid(
        bpm=120.0,
        beats=[0.0, 0.5, 1.0, 1.5, 2.0],
        downbeats=[0.0],
        time_signature={"numerator": 4, "denominator": 4},
        tick_value=0.25
    )

# --- UNIT TESTS ---

def test_get_segment_db_calculation():
    """Verify RMS to DB conversion for silence thresholding."""
    # Absolute silence
    assert _get_segment_db(np.zeros(1000)) == -100.0
    
    # Low volume noise
    noise = np.random.normal(0, 0.0001, 1000)
    db = _get_segment_db(noise)
    assert db < -60.0 # Well below our -40dB threshold

def test_snap_to_grid_logic():
    """Verify that notes are pulled to the nearest beat correctly."""
    beats = [0.0, 0.5, 1.0]
    # 0.49 should snap to 0.5
    assert _snap_to_grid(0.49, beats) == 0.5
    # 0.01 should snap to 0.0
    assert _snap_to_grid(0.01, beats) == 0.0

# --- INTEGRATION TESTS (MOCKED ML) ---

def test_chord_inference_silence_threshold(monkeypatch, tmp_path, mock_beat_grid):
    """Ensure loud audio gets a chord, but silent audio gets 'N'."""
    
    def mock_load(path, sr=None, mono=True):
        # Create 2 seconds of audio: 
        # First second is LOUD (0.5 amplitude), second second is SILENT (0.0)
        audio = np.concatenate([
            np.full(44100, 0.5), # Beat 0.0 and 0.5
            np.zeros(44100)      # Beat 1.0 and 1.5
        ])
        return audio, 44100

    def mock_tflite_raw(y, sr):
        # Model always wants to predict 'C'
        return [
            {"time": 0.1, "chord": "C", "confidence": 0.9},
            {"time": 0.6, "chord": "C", "confidence": 0.9},
            {"time": 1.1, "chord": "C", "confidence": 0.9},
            {"time": 1.6, "chord": "C", "confidence": 0.9},
        ]

    monkeypatch.setattr("librosa.load", mock_load)
    monkeypatch.setattr("app.chord_inference._run_tflite_raw", mock_tflite_raw)

    timeline = infer_chords(tmp_path / "dummy.wav", mock_beat_grid)

    # First two beats (loud) should be 'C'
    assert timeline.events[0].chord == "C"
    assert timeline.events[1].chord == "C"
    
    # Last two beats (silent) should be 'N' despite the ML model wanting to say 'C'
    assert timeline.events[2].chord == "N"
    assert timeline.events[3].chord == "N"

def test_chord_majority_vote_pooling(monkeypatch, tmp_path, mock_beat_grid):
    """Ensure flickering ML predictions are smoothed by the BeatGrid."""
    
    monkeypatch.setattr("librosa.load", lambda *a, **k: (np.full(44100, 0.5), 44100))
    
    def mock_flickering_tflite(y, sr):
        # In the first beat window (0.0 to 0.5), model flickers: C, G, C
        return [
            {"time": 0.1, "chord": "C", "confidence": 0.8},
            {"time": 0.2, "chord": "G", "confidence": 0.9}, # The outlier
            {"time": 0.3, "chord": "C", "confidence": 0.8},
        ]
    
    monkeypatch.setattr("app.chord_inference._run_tflite_raw", mock_flickering_tflite)

    timeline = infer_chords(tmp_path / "dummy.wav", mock_beat_grid)

    # The 'G' should be outvoted by the 'C's for that beat window
    assert timeline.events[0].chord == "C"

def test_solo_monophonic_truncation(monkeypatch, mock_beat_grid):
    """Verify that a solo line cannot have overlapping notes."""
    
    # Note 1: 0.1s to 0.9s (Starts at Beat 0, Ends at Beat 1.0)
    # Note 2: 0.6s to 1.2s (Starts at Beat 0.5, Ends at Beat 1.0) -> OVERLAP!
    mock_notes = [
        (0.1, 0.9, 60, 0.8, None),
        (0.6, 1.2, 64, 0.9, None)
    ]
    
    # Mock basic-pitch to return these overlapping notes
    monkeypatch.setattr("basic_pitch.inference.predict", lambda *a: (None, None, mock_notes))

    solo = infer_solo(Path("dummy.wav"), mock_beat_grid)

    # Note 0 should have been truncated to end when Note 1 starts (at 0.5s)
    assert solo.notes[0].start_time == 0.0 # 0.1 snapped to 0.0
    assert solo.notes[0].duration == 0.5   # Truncated from 0.9 to 0.5
    
    # Note 1 starts at 0.5
    assert solo.notes[1].start_time == 0.5 # 0.6 snapped to 0.5
    assert solo.notes[1].duration == 0.5   # 1.2 snapped to 1.0, 1.0-0.5 = 0.5

def test_solo_micro_note_filtering(monkeypatch, mock_beat_grid):
    """Ensure noise/very short notes are discarded."""
    
    # One real note, one note that is only 0.01s long (noise)
    mock_notes = [
        (0.0, 0.5, 60, 0.8, None),
        (0.6, 0.61, 64, 0.8, None) # Micro-note
    ]
    
    monkeypatch.setattr("basic_pitch.inference.predict", lambda *a: (None, None, mock_notes))

    solo = infer_solo(Path("dummy.wav"), mock_beat_grid)

    # Only the real note should survive
    assert len(solo.notes) == 1
    assert solo.notes[0].pitch == 60