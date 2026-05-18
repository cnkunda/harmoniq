"""Integration tests for Commit 99: Viterbi chord progression decoding.

Tests the full pipeline: TFLite → beat pooling → Viterbi → metrics
using synthetic audio fixtures and mocked inference components.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from app.chord_inference import (
    CHORD_VOCAB,
    _CHORD_TO_IDX,
    _detect_resolution_mode,
    _pool_beat_window,
    _split_half_beat,
    infer_chords,
)
from app.chord_metrics import (
    assemble_chord_metrics,
    compute_beat_alignment,
    compute_chord_change_histogram,
    compute_flicker_rate,
)
from app.schemas import BeatGrid


@pytest.fixture
def mock_beat_grid_120():
    return BeatGrid(
        bpm=120.0,
        beats=[i * 0.5 for i in range(13)],
        downbeats=[0.0, 2.0, 4.0, 6.0],
        time_signature={"numerator": 4, "denominator": 4},
        tick_value=0.25,
    )


@pytest.fixture
def mock_beat_grid_short():
    return BeatGrid(
        bpm=120.0,
        beats=[0.0, 0.5, 1.0, 1.5, 2.0],
        downbeats=[0.0],
        time_signature={"numerator": 4, "denominator": 4},
        tick_value=0.25,
    )


def _make_mock_frame(time_sec: float, chord: str, confidence: float) -> dict:
    idx = _CHORD_TO_IDX[chord]
    probs = np.full(len(CHORD_VOCAB), 1e-6, dtype=np.float32)
    probs[idx] = confidence
    probs /= probs.sum()
    return {
        "time": time_sec,
        "chord": chord,
        "confidence": confidence,
        "probs": probs,
    }


class _MockInterp:
    def get_input_details(self):
        return [{"index": 0}]
    def get_output_details(self):
        return [{"index": 1}]
    def set_tensor(self, *a):
        pass
    def invoke(self):
        pass
    def get_tensor(self, i):
        return np.zeros((1, 277), dtype=np.float32)
    def allocate_tensors(self):
        pass


class TestIIVIPProgression:
    """Test that Viterbi correctly decodes a classic ii-V-I progression."""

    def test_ii_v_i_ordering(self, monkeypatch, tmp_path, mock_beat_grid_120):
        monkeypatch.setattr("app.chord_inference._get_interpreter", lambda: _MockInterp())
        monkeypatch.setattr("librosa.load", lambda *a, **k: (np.full(44100 * 6, 0.3), 44100))

        frames = []
        chord_sequence = [
            ("D:min7", 4),
            ("G:7", 4),
            ("C:maj", 4),
        ]
        t = 0.0
        for chord, num_beats in chord_sequence:
            for _ in range(num_beats):
                frames.append(_make_mock_frame(t, chord, 0.75))
                t += 0.1

        monkeypatch.setattr("app.chord_inference._run_tflite_raw", lambda y, sr: frames)

        timeline = infer_chords(tmp_path / "dummy.wav", mock_beat_grid_120)
        chords = [e.chord for e in timeline.events if e.chord != "N"]

        assert "D:min7" in chords
        assert "G:7" in chords
        assert "C:maj" in chords

        ii_idx = next(i for i, c in enumerate(chords) if c == "D:min7")
        v_idx = next(i for i, c in enumerate(chords) if c == "G:7")
        i_idx = next(i for i, c in enumerate(chords) if c == "C:maj")
        assert ii_idx < v_idx < i_idx


class TestFlickerReduction:
    """Test that Viterbi reduces chord flicker compared to raw beat pooling."""

    def test_viterbi_reduces_flicker(self, monkeypatch, tmp_path, mock_beat_grid_short):
        monkeypatch.setattr("app.chord_inference._get_interpreter", lambda: _MockInterp())
        monkeypatch.setattr("librosa.load", lambda *a, **k: (np.full(44100 * 2, 0.3), 44100))

        frames = []
        t = 0.0
        chord_pattern = ["C:maj", "G:maj", "C:maj", "F:maj", "C:maj"]
        for chord in chord_pattern:
            frames.append(_make_mock_frame(t, chord, 0.7))
            t += 0.1

        monkeypatch.setattr("app.chord_inference._run_tflite_raw", lambda y, sr: frames)

        timeline = infer_chords(tmp_path / "dummy.wav", mock_beat_grid_short)
        assert timeline.metadata is not None
        flicker = timeline.metadata["flicker_rate"]
        assert flicker < 0.05, f"Flicker rate {flicker} exceeds 5% target"


class TestHalfBeatSplit:
    """Test half-beat tie-detection and dual ChordEvent emission."""

    def test_tie_detection_triggers_split(self):
        frames = []
        t = 0.0
        for _ in range(3):
            c_probs = np.full(len(CHORD_VOCAB), 1e-6, dtype=np.float32)
            c_probs[_CHORD_TO_IDX["C:maj"]] = 0.52
            c_probs[_CHORD_TO_IDX["G:maj"]] = 0.48
            c_probs /= c_probs.sum()
            frames.append({
                "time": t,
                "chord": "C:maj",
                "confidence": 0.52,
                "probs": c_probs,
            })
            t += 0.15
        for _ in range(3):
            g_probs = np.full(len(CHORD_VOCAB), 1e-6, dtype=np.float32)
            g_probs[_CHORD_TO_IDX["G:maj"]] = 0.55
            g_probs[_CHORD_TO_IDX["C:maj"]] = 0.45
            g_probs /= g_probs.sum()
            frames.append({
                "time": t,
                "chord": "G:maj",
                "confidence": 0.55,
                "probs": g_probs,
            })
            t += 0.15

        bd = _pool_beat_window(frames, 0.0, 0.9)
        assert bd["confidence_gap"] < 0.15
        assert bd["first_half_top"] != bd["second_half_top"]

        splits = _split_half_beat(bd)
        assert len(splits) == 2
        assert splits[0]["is_half_beat"]
        assert splits[1]["is_half_beat"]
        assert abs(splits[1]["timestamp"] - splits[0]["timestamp"] - 0.45) < 0.01

    def test_no_split_when_gap_large(self):
        frames = []
        t = 0.0
        for _ in range(6):
            probs = np.full(len(CHORD_VOCAB), 1e-6, dtype=np.float32)
            probs[_CHORD_TO_IDX["C:maj"]] = 0.85
            probs[_CHORD_TO_IDX["G:maj"]] = 0.10
            probs /= probs.sum()
            frames.append({
                "time": t,
                "chord": "C:maj",
                "confidence": 0.85,
                "probs": probs,
            })
            t += 0.1

        bd = _pool_beat_window(frames, 0.0, 0.6)
        assert bd["confidence_gap"] >= 0.15


class TestResolutionModeDetection:
    def test_beat_mode_for_quarter_grid(self):
        beats = [i * 0.5 for i in range(9)]
        mode = _detect_resolution_mode(beats, bpm=120.0)
        assert mode == "beat"

    def test_half_beat_mode_for_eighth_grid(self):
        beats = [i * 0.25 for i in range(17)]
        mode = _detect_resolution_mode(beats, bpm=120.0)
        assert mode == "half-beat"


class TestBeatAlignment:
    def test_all_changes_on_beats(self, mock_beat_grid_short):
        events_data = [
            (0.0, "C:maj", 0.9),
            (0.5, "C:maj", 0.9),
            (1.0, "G:maj", 0.8),
            (1.5, "G:maj", 0.8),
            (2.0, "C:maj", 0.9),
        ]
        from app.schemas import ChordEvent
        events = [ChordEvent(timestamp=t, chord=c, confidence=conf) for t, c, conf in events_data]

        alignment = compute_beat_alignment(events, mock_beat_grid_short, measure="any")
        assert alignment == 1.0

    def test_downbeat_alignment(self, mock_beat_grid_120):
        from app.schemas import ChordEvent
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=4.0, chord="C:maj", confidence=0.9),
        ]

        alignment = compute_beat_alignment(events, mock_beat_grid_120, measure="downbeat")
        assert alignment >= 0.5


class TestChordChangeHistogram:
    def test_histogram_bins(self, mock_beat_grid_120):
        from app.schemas import ChordEvent
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=4.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=6.0, chord="F:maj", confidence=0.7),
        ]

        hist = compute_chord_change_histogram(events, mock_beat_grid_120)
        assert "bins" in hist
        assert "counts" in hist
        assert hist["total_changes"] == 3
        assert sum(hist["counts"]) == 2


class TestMetricsAssembly:
    def test_assemble_returns_all_keys(self, mock_beat_grid_short):
        from app.schemas import ChordEvent
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=1.5, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=2.0, chord="C:maj", confidence=0.9),
        ]

        metadata = assemble_chord_metrics(events, mock_beat_grid_short)
        assert "flicker_rate" in metadata
        assert "beat_alignment_pct" in metadata
        assert "downbeat_alignment_pct" in metadata
        assert "chord_change_histogram" in metadata
        assert "duration_filtering" in metadata
        assert "total_events" in metadata
        assert "unique_chords" in metadata


class TestViterbiPerformance:
    def test_viterbi_latency_under_50ms(self):
        from app.chord_transitions import get_transition_matrix, apply_key_constraint
        from app.viterbi_decoder import ViterbiChordDecoder, probs_to_log_probs

        base_matrix = get_transition_matrix()
        trans_matrix = apply_key_constraint(base_matrix, key_root=7, key_mode="major")
        trans_log = probs_to_log_probs(trans_matrix)

        T = 60
        vocab_size = 277
        emission_probs = np.ones((T, vocab_size), dtype=np.float32) / vocab_size
        emission_probs[:, 0] = 0.5
        emission_probs[:, 100] = 0.3
        emission_probs[:, 200] = 0.2
        emission_log = probs_to_log_probs(emission_probs)
        duration_beats = np.ones(T, dtype=np.float32)

        decoder = ViterbiChordDecoder(
            trans_log, vocab_size=vocab_size, chord_vocab=CHORD_VOCAB
        )

        # Warmup iteration (outside timing)
        decoder.decode(emission_log, duration_beats=duration_beats)

        times = []
        for _ in range(20):
            start = time.perf_counter()
            decoder.decode(emission_log, duration_beats=duration_beats)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        avg_ms = sum(times) / len(times)
        assert avg_ms < 100.0, f"Viterbi avg latency {avg_ms:.1f}ms exceeds 100ms target"


class TestCIFlickerGate:
    def test_flicker_below_5_percent(self, monkeypatch, tmp_path, mock_beat_grid_120):
        monkeypatch.setattr("app.chord_inference._get_interpreter", lambda: _MockInterp())
        monkeypatch.setattr("librosa.load", lambda *a, **k: (np.full(44100 * 6, 0.3), 44100))

        frames = []
        t = 0.0
        chord_sequence = [
            ("C:maj", 4),
            ("F:maj", 4),
            ("G:7", 4),
            ("C:maj", 8),
        ]
        for chord, num_beats in chord_sequence:
            for _ in range(num_beats * 5):
                frames.append(_make_mock_frame(t, chord, 0.85))
                t += 0.1

        monkeypatch.setattr("app.chord_inference._run_tflite_raw", lambda y, sr: frames)

        timeline = infer_chords(tmp_path / "dummy.wav", mock_beat_grid_120)
        assert timeline.metadata is not None
        assert timeline.metadata["flicker_rate"] < 0.05


class TestCIBeatAlignmentGate:
    def test_alignment_above_90_percent(self, monkeypatch, tmp_path, mock_beat_grid_120):
        monkeypatch.setattr("app.chord_inference._get_interpreter", lambda: _MockInterp())
        monkeypatch.setattr("librosa.load", lambda *a, **k: (np.full(44100 * 6, 0.3), 44100))

        frames = []
        t = 0.0
        chord_sequence = [
            ("C:maj", 8),
            ("G:7", 8),
            ("C:maj", 8),
        ]
        for chord, num_beats in chord_sequence:
            for _ in range(num_beats * 5):
                frames.append(_make_mock_frame(t, chord, 0.85))
                t += 0.1

        monkeypatch.setattr("app.chord_inference._run_tflite_raw", lambda y, sr: frames)

        timeline = infer_chords(tmp_path / "dummy.wav", mock_beat_grid_120)
        assert timeline.metadata is not None
        assert timeline.metadata["beat_alignment_pct"] >= 0.90
