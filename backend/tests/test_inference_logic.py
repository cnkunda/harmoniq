"""Tests for Commit 79: ML Inference Logic (Chords & Solo)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import numpy as np
import pytest

from app.chord_inference import _get_segment_db, infer_chords
from app.solo_inference import infer_solo, _snap_to_grid
from app.schemas import BeatGrid


@pytest.fixture(autouse=True)
def _mock_basic_pitch_import():
    """Prevent basic-pitch from hanging on model download during import."""
    if "basic_pitch" not in sys.modules:
        mock_model_path = MagicMock(spec=Path)
        mock_model_path.is_dir.return_value = True
        mock_model_path.suffix = ""
        mock_model_path.exists.return_value = True
        mock_model_path.with_name.return_value = mock_model_path
        mock_model_path.name = "nmp"

        mock_bp = MagicMock()
        mock_bp.ICASSP_2022_MODEL_PATH = mock_model_path
        mock_inference = MagicMock()
        mock_bp.inference = mock_inference
        sys.modules["basic_pitch"] = mock_bp
        sys.modules["basic_pitch.inference"] = mock_inference
        yield
        del sys.modules["basic_pitch"]
        del sys.modules["basic_pitch.inference"]
    else:
        yield

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


@pytest.fixture
def fine_beat_grid():
    """120 BPM 4/4 grid with tick-level resolution (0.25s spacing) for micro-note tests."""
    return BeatGrid(
        bpm=120.0,
        beats=[0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0],
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

    from app.chord_inference import _get_interpreter
    _get_interpreter.cache_clear()

    class _MockInterp:
        def get_input_details(self): return [{"index": 0}]
        def get_output_details(self): return [{"index": 1}]
        def set_tensor(self, *a): pass
        def invoke(self): pass
        def get_tensor(self, i): return np.zeros((1, 277), dtype=np.float32)
        def allocate_tensors(self): pass

    monkeypatch.setattr("app.chord_inference._get_interpreter", lambda: _MockInterp())

    def _no_keras(y, sr):
        raise RuntimeError("Keras mocked out")

    monkeypatch.setattr("app.chord_inference._run_keras_raw", _no_keras)

    def mock_load(path, sr=None, mono=True):
        audio = np.concatenate([
            np.full(44100, 0.5),
            np.zeros(44100)
        ])
        return audio, 44100

    def _make_frame(time_sec, chord, confidence):
        probs = np.full(277, 1e-6, dtype=np.float32)
        probs[0] = confidence
        probs /= probs.sum()
        return {"time": time_sec, "chord": chord, "confidence": confidence, "probs": probs}

    def mock_tflite_raw(y, sr):
        return [
            _make_frame(0.1, "C:maj", 0.9),
            _make_frame(0.6, "C:maj", 0.9),
            _make_frame(1.1, "C:maj", 0.9),
            _make_frame(1.6, "C:maj", 0.9),
        ]

    monkeypatch.setattr("librosa.load", mock_load)
    monkeypatch.setattr("app.chord_inference._run_tflite_raw", mock_tflite_raw)

    timeline = infer_chords(tmp_path / "dummy.wav", mock_beat_grid)

    assert timeline.events[0].chord == "C:maj"
    assert timeline.events[1].chord == "C:maj"
    assert timeline.events[2].chord == "N"
    assert timeline.events[3].chord == "N"

def test_chord_majority_vote_pooling(monkeypatch, tmp_path, mock_beat_grid):
    """Ensure flickering ML predictions are smoothed by the BeatGrid."""

    from app.chord_inference import _get_interpreter
    _get_interpreter.cache_clear()

    class _MockInterp:
        def get_input_details(self): return [{"index": 0}]
        def get_output_details(self): return [{"index": 1}]
        def set_tensor(self, *a): pass
        def invoke(self): pass
        def get_tensor(self, i): return np.zeros((1, 277), dtype=np.float32)
        def allocate_tensors(self): pass

    monkeypatch.setattr("app.chord_inference._get_interpreter", lambda: _MockInterp())

    def _no_keras(y, sr):
        raise RuntimeError("Keras mocked out")

    monkeypatch.setattr("app.chord_inference._run_keras_raw", _no_keras)

    monkeypatch.setattr("librosa.load", lambda *a, **k: (np.full(44100, 0.5), 44100))

    def _make_frame(time_sec, chord, confidence):
        probs = np.full(277, 1e-6, dtype=np.float32)
        idx = 0 if chord == "C:maj" else 1
        probs[idx] = confidence
        probs /= probs.sum()
        return {"time": time_sec, "chord": chord, "confidence": confidence, "probs": probs}

    def mock_flickering_tflite(y, sr):
        return [
            _make_frame(0.1, "C:maj", 0.8),
            _make_frame(0.2, "C#:min", 0.9),
            _make_frame(0.3, "C:maj", 0.8),
        ]

    monkeypatch.setattr("app.chord_inference._run_tflite_raw", mock_flickering_tflite)

    timeline = infer_chords(tmp_path / "dummy.wav", mock_beat_grid)

    assert timeline.events[0].chord == "C:maj"

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

def test_solo_micro_note_filtering(monkeypatch, fine_beat_grid):
    """Ensure micro-notes that pass duration filter are preserved with minimum tick duration."""
    
    # One real note, one grace note that gets crushed by quantization
    # The grace note (0.26s-0.24s played backward, or 0.24s-0.26s very short)
    # Both start and end snap to the same grid point (0.25), but it's preserved with min duration
    mock_notes = [
        (0.0, 0.5, 60, 0.8, None),
        (0.24, 0.26, 64, 0.8, None) # Very short note that snaps to same grid point
    ]
    
    monkeypatch.setattr("basic_pitch.inference.predict", lambda *a, **kw: (None, None, mock_notes))

    solo = infer_solo(Path("dummy.wav"), fine_beat_grid)
    assert len(solo.notes) == 2
    assert solo.notes[0].pitch == 60
    assert solo.notes[1].pitch == 64
    # At 120 BPM with tick_value=0.25, one tick = (60/120)*0.25 = 0.125s
    assert solo.notes[1].duration == 0.125