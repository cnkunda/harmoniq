"""Tests for shared chord vocabulary (Commit 98)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import (
    CHORD_VOCAB,
    CHORD_TO_IDX,
    CHORD_INTERVALS,
    CHORD_QUALITIES,
    ROOT_NOTES,
    NUM_CLASSES,
    MIREX_VOCAB,
    NUM_CLASSES_MIREX,
    mirex_label,
)


class TestVocabularySize:
    def test_277_total_classes(self):
        assert NUM_CLASSES == 277
        assert len(CHORD_VOCAB) == 277

    def test_276_chord_plus_1_no_chord(self):
        n_chords = len(CHORD_QUALITIES) * len(ROOT_NOTES)
        assert n_chords == 276
        assert CHORD_VOCAB[-1] == "N"

    def test_twelve_roots(self):
        assert len(ROOT_NOTES) == 12

    def test_twenty_three_qualities(self):
        assert len(CHORD_QUALITIES) == 23

    def test_all_qualities_have_intervals(self):
        for q in CHORD_QUALITIES:
            assert q in CHORD_INTERVALS
            assert len(CHORD_INTERVALS[q]) >= 2


class TestChordToIdx:
    def test_C_maj_maps_to_zero(self):
        assert CHORD_TO_IDX["C:maj"] == 0

    def test_C_sharp_maj_maps_to_one(self):
        assert CHORD_TO_IDX["C#:maj"] == 1

    def test_N_maps_to_276(self):
        assert CHORD_TO_IDX["N"] == 276

    def test_all_277_mappings_roundtrip(self):
        for i, chord in enumerate(CHORD_VOCAB):
            assert CHORD_TO_IDX[chord] == i
            assert CHORD_VOCAB[CHORD_TO_IDX[chord]] == chord

    def test_quality_ordering(self):
        for qi, q in enumerate(CHORD_QUALITIES):
            idx = qi * 12
            assert CHORD_VOCAB[idx] == f"C:{q}"
            assert CHORD_VOCAB[idx + 11] == f"B:{q}"


class TestChordIntervals:
    def test_major_triad(self):
        assert CHORD_INTERVALS["maj"] == [0, 4, 7]

    def test_minor_triad(self):
        assert CHORD_INTERVALS["min"] == [0, 3, 7]

    def test_dominant_seventh(self):
        assert CHORD_INTERVALS["7"] == [0, 4, 7, 10]

    def test_all_intervals_sorted(self):
        for q, intervals in CHORD_INTERVALS.items():
            assert intervals == sorted(intervals), f"{q} intervals not sorted"
            assert intervals[0] == 0, f"{q} does not start at root"


class TestMirexMapping:
    def test_mirex_vocab_size(self):
        assert len(MIREX_VOCAB) == 25
        assert NUM_CLASSES_MIREX == 25

    def test_mirex_contains_major_minor_N(self):
        for root in ROOT_NOTES:
            assert f"{root}:maj" in MIREX_VOCAB
            assert f"{root}:min" in MIREX_VOCAB
        assert "N" in MIREX_VOCAB

    def test_C_maj_maps_to_mirex(self):
        idx = CHORD_TO_IDX["C:maj"]
        assert mirex_label(idx) == MIREX_VOCAB.index("C:maj")

    def test_C_min_maps_to_mirex(self):
        idx = CHORD_TO_IDX["C:min"]
        assert mirex_label(idx) == MIREX_VOCAB.index("C:min")

    def test_C_7_maps_to_C_maj_mirex(self):
        idx = CHORD_TO_IDX["C:7"]
        assert mirex_label(idx) == MIREX_VOCAB.index("C:maj")

    def test_C_min7_maps_to_C_min_mirex(self):
        idx = CHORD_TO_IDX["C:min7"]
        assert mirex_label(idx) == MIREX_VOCAB.index("C:min")

    def test_N_maps_to_N_mirex(self):
        idx = CHORD_TO_IDX["N"]
        assert mirex_label(idx) == MIREX_VOCAB.index("N")

    def test_all_277_map_to_mirex(self):
        for i in range(NUM_CLASSES):
            mirex = mirex_label(i)
            assert 0 <= mirex < NUM_CLASSES_MIREX
