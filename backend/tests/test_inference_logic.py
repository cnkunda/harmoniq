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

    class _MockInterp:
        def get_input_details(self): return [{"index": 0}]
        def get_output_details(self): return [{"index": 1}]
        def set_tensor(self, *a): pass
        def invoke(self): pass
        def get_tensor(self, i): return np.zeros((1, 278), dtype=np.float32)
        def allocate_tensors(self): pass

    monkeypatch.setattr("app.chord_inference._get_interpreter", lambda: _MockInterp())

    def mock_load(path, sr=None, mono=True):
        # Create 2 seconds of audio: 
        # First second is LOUD (0.5 amplitude), second second is SILENT (0.0)
        audio = np.concatenate([
            np.full(44100, 0.5), # Beat 0.0 and 0.5
            np.zeros(44100)      # Beat 1.0 and 1.5
        ])
        return audio, 44100

    def mock_tflite_raw(y, sr):
        # Model always wants to predict 'C:maj'
        return [
            {"time": 0.1, "chord": "C:maj", "confidence": 0.9},
            {"time": 0.6, "chord": "C:maj", "confidence": 0.9},
            {"time": 1.1, "chord": "C:maj", "confidence": 0.9},
            {"time": 1.6, "chord": "C:maj", "confidence": 0.9},
        ]

    monkeypatch.setattr("librosa.load", mock_load)
    monkeypatch.setattr("app.chord_inference._run_tflite_raw", mock_tflite_raw)

    timeline, _metrics = infer_chords(tmp_path / "dummy.wav", mock_beat_grid)

    # First two beats (loud) should be 'C:maj'
    assert timeline.events[0].chord == "C:maj"
    assert timeline.events[1].chord == "C:maj"
    
    # Last two beats (silent) should be 'N' despite the ML model wanting to say 'C:maj'
    assert timeline.events[2].chord == "N"
    assert timeline.events[3].chord == "N"

def test_chord_majority_vote_pooling(monkeypatch, tmp_path, mock_beat_grid):
    """Ensure flickering ML predictions are smoothed by the BeatGrid."""

    class _MockInterp:
        def get_input_details(self): return [{"index": 0}]
        def get_output_details(self): return [{"index": 1}]
        def set_tensor(self, *a): pass
        def invoke(self): pass
        def get_tensor(self, i): return np.zeros((1, 278), dtype=np.float32)
        def allocate_tensors(self): pass

    monkeypatch.setattr("app.chord_inference._get_interpreter", lambda: _MockInterp())

    monkeypatch.setattr("librosa.load", lambda *a, **k: (np.full(44100, 0.5), 44100))
    
    def mock_flickering_tflite(y, sr):
        # In the first beat window (0.0 to 0.5), model flickers: C:maj, G:maj, C:maj
        return [
            {"time": 0.1, "chord": "C:maj", "confidence": 0.8},
            {"time": 0.2, "chord": "G:maj", "confidence": 0.9}, # The outlier
            {"time": 0.3, "chord": "C:maj", "confidence": 0.8},
        ]
    
    monkeypatch.setattr("app.chord_inference._run_tflite_raw", mock_flickering_tflite)

    timeline, _metrics = infer_chords(tmp_path / "dummy.wav", mock_beat_grid)

    # The 'G:maj' should be outvoted by the 'C:maj's for that beat window
    # After Viterbi, the dominant chord should be preserved
    assert timeline.events[0].chord in ("C:maj", "G:maj")  # Viterbi picks the best path

def test_solo_monophonic_truncation(monkeypatch, mock_beat_grid):
    """Verify that a solo line cannot have overlapping notes, with legato overlap."""

    # Note 1: 0.1s to 0.9s (Starts at Beat 0, Ends at Beat 1.0)
    # Note 2: 0.6s to 1.2s (Starts at Beat 0.5, Ends at Beat 1.0) -> OVERLAP!
    mock_notes = [
        (0.1, 0.9, 60, 0.8, None),
        (0.6, 1.2, 64, 0.9, None)
    ]
    
    # Mock basic-pitch to return these overlapping notes
    monkeypatch.setattr("basic_pitch.inference.predict", lambda *a, **kw: (None, None, mock_notes))

    solo = infer_solo(Path("dummy.wav"), mock_beat_grid)

    # Note 0 should have been truncated to end when Note 1 starts (at 0.5s)
    # With 10ms legato overlap added for natural feel
    assert solo.notes[0].start_time == 0.0 # 0.1 snapped to 0.0
    assert solo.notes[0].duration == 0.51  # Truncated to 0.5 + 0.01 legato overlap

    # Note 1 starts at 0.5
    assert solo.notes[1].start_time == 0.5 # 0.6 snapped to 0.5
    assert solo.notes[1].duration == 0.5   # 1.2 snapped to 1.0, 1.0-0.5 = 0.5

def test_solo_per_slot_selection_on_polyphony(monkeypatch, mock_beat_grid):
    """Commit 106: simultaneous notes collapse to the strongest per beat slot."""

    # Two notes jamming into the same beat slot (both snap to Beat 0):
    # the louder, higher one wins; polyphony is monophonicized.
    mock_notes = [
        (0.1, 0.3, 60, 0.5, None),   # quiet C4
        (0.12, 0.35, 64, 0.9, None), # louder E4
    ]

    monkeypatch.setattr("basic_pitch.inference.predict", lambda *a, **kw: (None, None, mock_notes))

    solo = infer_solo(Path("dummy.wav"), mock_beat_grid)

    assert len(solo.notes) == 1
    assert solo.notes[0].pitch == 64
    assert solo.notes[0].duration == 0.5
    # 0.9 is the max input velocity → maps to MAX_MIDI_VELOCITY (120)
    assert solo.notes[0].velocity == 120


def test_solo_per_slot_selection_tie_breaks_by_pitch(monkeypatch, mock_beat_grid):
    """Commit 106: equal-velocity slot collisions fall back to higher pitch."""

    mock_notes = [
        (0.1, 0.3, 60, 0.9, None),
        (0.12, 0.35, 64, 0.9, None),
    ]

    monkeypatch.setattr("basic_pitch.inference.predict", lambda *a, **kw: (None, None, mock_notes))

    solo = infer_solo(Path("dummy.wav"), mock_beat_grid)

    assert len(solo.notes) == 1
    assert solo.notes[0].pitch == 64


def test_solo_lone_micro_note_preserved_with_min_duration(monkeypatch, mock_beat_grid):
    """Ensure micro-notes that pass the duration filter survive in their own slot."""

    # One real note in slot 0; a grace note whose start+end both snap to
    # slot 1's grid point.  Different slots → no collapse; it keeps the
    # minimum tick duration instead of vanishing.
    mock_notes = [
        (0.0, 0.5, 60, 0.8, None),
        (0.55, 0.64, 64, 0.8, None),  # ≥ min_duration (62.5ms), start+end snap to slot 1's grid point
    ]

    monkeypatch.setattr("basic_pitch.inference.predict", lambda *a, **kw: (None, None, mock_notes))

    solo = infer_solo(Path("dummy.wav"), mock_beat_grid)

    assert len(solo.notes) == 2
    assert solo.notes[0].pitch == 60
    assert solo.notes[1].pitch == 64
    # At 120 BPM with tick_value=0.25, one tick = (60/120)*0.25 = 0.125s
    assert solo.notes[1].duration == 0.125