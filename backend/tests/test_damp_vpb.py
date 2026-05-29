"""Tests for DAMP-VPB dataset pipeline (Commit 105 Phase 4).

Tests: pitch file parsing, pitch-to-chord heuristic labeling,
CQT extraction, confidence filtering.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_TO_IDX, ROOT_NOTES, CHORD_INTERVALS
from scripts.extract_damp_vpb import (
    _freq_to_pitch_class,
    _build_pc_histogram,
    _match_chord_from_histogram,
    parse_pitch_file,
    group_pitch_to_frames,
    extract_cqt,
    build_windows,
    CHROMA_BINS,
    BASS_BINS,
    FEATURE_DIM,
    WINDOW,
    N_CHORD_IDX,
)


class TestFreqToPitchClass:
    def test_A4_is_9(self):
        assert _freq_to_pitch_class(440.0) == 9

    def test_C4_is_0(self):
        freq = 261.63  # C4
        result = _freq_to_pitch_class(freq)
        assert result == 0

    def test_G3_is_7(self):
        freq = 196.00  # G3
        result = _freq_to_pitch_class(freq)
        assert result == 7

    def test_zero_freq(self):
        assert _freq_to_pitch_class(0) is None

    def test_negative_freq(self):
        assert _freq_to_pitch_class(-1) is None

    def test_nan_freq(self):
        assert _freq_to_pitch_class(float('nan')) is None

    def test_out_of_range_low(self):
        assert _freq_to_pitch_class(10.0) is None  # Below E0

    def test_out_of_range_high(self):
        assert _freq_to_pitch_class(20000.0) is None  # Above C8


class TestBuildPcHistogram:
    def test_all_same_pc(self):
        pcs = [0, 0, 0, 0]
        hist = _build_pc_histogram(pcs)
        assert hist[0] == pytest.approx(1.0)
        assert hist.sum() == pytest.approx(1.0)

    def test_empty_pcs(self):
        hist = _build_pc_histogram([])
        assert hist.sum() == 0

    def test_all_none(self):
        hist = _build_pc_histogram([None, None])
        assert hist.sum() == 0

    def test_mixed_histogram(self):
        pcs = [0, 4, 7]  # C major triad
        hist = _build_pc_histogram(pcs)
        assert hist[0] > 0
        assert hist[4] > 0
        assert hist[7] > 0
        assert hist.sum() == pytest.approx(1.0)


class TestMatchChordFromHistogram:
    def test_C_major_triad(self):
        # Perfect C major: C, E, G (0, 4, 7)
        pcs = [0, 4, 7, 0, 4, 7, 0, 4, 7]
        hist = _build_pc_histogram(pcs)
        chord, confidence = _match_chord_from_histogram(hist, confidence_threshold=0.5)
        assert chord == "C:maj", f"Expected C:maj, got {chord}"
        assert confidence > 0.5

    def test_A_minor_triad(self):
        pcs = [9, 0, 4, 9, 0, 4]  # A, C, E
        hist = _build_pc_histogram(pcs)
        chord, confidence = _match_chord_from_histogram(hist, confidence_threshold=0.5)
        assert chord == "A:min"
        assert confidence > 0.5

    def test_G7_chord(self):
        # G7: G, B, D, F (7, 11, 2, 5)
        pcs = [7, 11, 2, 5, 7, 11, 2, 5]
        hist = _build_pc_histogram(pcs)
        chord, confidence = _match_chord_from_histogram(hist, confidence_threshold=0.5)
        assert chord == "G:7"
        assert confidence > 0.5

    def test_below_confidence_threshold(self):
        # Random noise should not produce a confident match
        np.random.seed(42)
        pcs = np.random.randint(0, 12, size=100).tolist()
        hist = _build_pc_histogram(pcs)
        chord, confidence = _match_chord_from_histogram(hist, confidence_threshold=0.9)
        # Random noise should not match at 0.9 confidence
        if chord is not None:
            assert confidence < 0, "Random noise should have low confidence"


class TestParsePitchFile:
    def test_parses_csv(self, tmp_path):
        pitch_file = tmp_path / "test_pitch.csv"
        with open(pitch_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows([
                [0.0, 261.63],
                [0.1, 293.66],
                [0.2, 329.63],
                [0.3, 0],  # Unvoiced
                [0.4, 392.00],
            ])

        data = parse_pitch_file(pitch_file)
        assert len(data) == 4  # Zero-freq row skipped
        assert data[0][0] == 0.0
        assert abs(data[0][1] - 261.63) < 0.1

    def test_empty_file(self, tmp_path):
        pitch_file = tmp_path / "empty.csv"
        pitch_file.write_text("")
        data = parse_pitch_file(pitch_file)
        assert len(data) == 0

    def test_missing_file(self, tmp_path):
        data = parse_pitch_file(tmp_path / "nonexistent.csv")
        assert len(data) == 0

    def test_malformed_file(self, tmp_path):
        pitch_file = tmp_path / "bad.csv"
        pitch_file.write_text("not,valid,data\n1,2\n")
        data = parse_pitch_file(pitch_file)
        assert len(data) == 1


class TestGroupPitchToFrames:
    def test_simple_chord(self):
        # C major triad: C (0), E (4), G (7) at ~261, 330, 392 Hz
        pitch_data = np.array([
            [0.0, 261.63],
            [0.01, 329.63],
            [0.02, 392.00],
            [0.03, 261.63],
            [0.04, 329.63],
            [0.05, 392.00],
        ])
        chords = group_pitch_to_frames(pitch_data)
        assert len(chords) > 0

    def test_empty_pitch_data(self):
        chords = group_pitch_to_frames(np.array([]))
        assert chords == []

    def test_returns_no_chord_for_sparse_data(self):
        pitch_data = np.array([
            [0.0, 261.63],
        ])
        chords = group_pitch_to_frames(pitch_data)
        assert len(chords) > 0
        assert chords[0] == N_CHORD_IDX  # Not enough data


class TestExtractCqt:
    def test_output_shape(self):
        sr = 44100
        y = np.random.randn(int(sr * 0.3)).astype(np.float32) * 0.01
        features = extract_cqt(y, sr)
        assert features.shape[1] == FEATURE_DIM


class TestBuildWindows:
    def test_window_shape(self):
        T = 100
        features = np.random.randn(T, FEATURE_DIM).astype(np.float32)
        labels = np.random.randint(0, 10, size=T).astype(np.int32)
        windows, window_labels = build_windows(features, labels)
        expected = (T + 64 - 1) // 64
        assert windows.shape == (expected, WINDOW, FEATURE_DIM)
        assert window_labels.shape == (expected,)
