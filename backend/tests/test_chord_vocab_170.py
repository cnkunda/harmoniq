"""Tests for the 170-class chord vocabulary (Chord 170 program)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_vocab import CHORD_VOCAB, CHORD_TO_IDX, NUM_CLASSES  # noqa: E402
from app.chord_vocab_170 import (  # noqa: E402
    BASS_VOCAB,
    BASS_X_IDX,
    CHORD_TO_IDX_170,
    CHORD_VOCAB_170,
    MAP_277_TO_170_TABLE,
    N_IDX_170,
    NUM_CLASSES_170,
    NUM_CLASSES_BASS,
    QUALITIES_14,
    QUALITY_INTERVALS_170,
    QUALITY_MAP_277_TO_170,
    ROOTS_12,
    X_IDX_170,
    map_277_to_170,
)


class TestVocabulary:
    def test_exactly_170_classes(self):
        assert len(CHORD_VOCAB_170) == 170
        assert len(set(CHORD_VOCAB_170)) == 170

    def test_168_chords_plus_n_and_x(self):
        chords = CHORD_VOCAB_170[:-2]
        assert len(chords) == 168
        assert CHORD_VOCAB_170[-2:] == ["N", "X"]
        assert N_IDX_170 == 168
        assert X_IDX_170 == 169

    def test_12_roots_x_14_qualities(self):
        for quality in QUALITIES_14:
            for root in ROOTS_12:
                label = f"{root}:{quality}"
                assert label in CHORD_TO_IDX_170

    def test_vocab_is_product_of_roots_and_qualities(self):
        expected = {f"{root}:{qual}" for qual in QUALITIES_14 for root in ROOTS_12}
        assert set(CHORD_VOCAB_170[:-2]) == expected

    def test_bass_vocab_13_classes(self):
        assert len(BASS_VOCAB) == NUM_CLASSES_BASS == 13
        assert BASS_VOCAB[:12] == ROOTS_12
        assert BASS_VOCAB[12] == "X"
        assert BASS_X_IDX == 12

    def test_unique_indices(self):
        assert len(set(CHORD_TO_IDX_170.values())) == 170

    def test_interval_shapes(self):
        assert QUALITY_INTERVALS_170["minmaj7"] == [0, 3, 7, 11]
        assert QUALITY_INTERVALS_170["hdim7"] == [0, 3, 6, 10]
        assert QUALITY_INTERVALS_170["maj7"] == [0, 4, 7, 11]
        assert QUALITY_INTERVALS_170["7"] == [0, 4, 7, 10]


class TestMap277To170:
    def test_all_indices_map_into_170_range(self):
        table = MAP_277_TO_170_TABLE
        assert len(table) == NUM_CLASSES
        assert min(table) >= 0
        assert max(table) <= X_IDX_170

    def test_n_maps_to_n(self):
        assert map_277_to_170(NUM_CLASSES - 1) == N_IDX_170
        assert MAP_277_TO_170_TABLE[NUM_CLASSES - 1] == N_IDX_170

    def test_identity_qualities_preserve_root(self):
        for quality_277, quality_170 in [
            ("maj", "maj"), ("min", "min"), ("7", "7"),
            ("maj7", "maj7"), ("min7", "min7"), ("dim", "dim"),
            ("dim7", "dim7"), ("aug", "aug"), ("sus2", "sus2"), ("sus4", "sus4"),
        ]:
            for root in ["C", "F#", "B"]:
                idx_277 = CHORD_TO_IDX[f"{root}:{quality_277}"]
                idx_170 = map_277_to_170(idx_277)
                assert CHORD_VOCAB_170[idx_170] == f"{root}:{quality_170}"

    def test_extended_collapse(self):
        assert CHORD_VOCAB_170[map_277_to_170(CHORD_TO_IDX["C:9"])] == "C:7"
        assert CHORD_VOCAB_170[map_277_to_170(CHORD_TO_IDX["C:11"])] == "C:7"
        assert CHORD_VOCAB_170[map_277_to_170(CHORD_TO_IDX["C:13"])] == "C:7"
        assert CHORD_VOCAB_170[map_277_to_170(CHORD_TO_IDX["C:maj9"])] == "C:maj7"
        assert CHORD_VOCAB_170[map_277_to_170(CHORD_TO_IDX["D:min9"])] == "D:min7"

    def test_altered_dominants_collapse_to_7(self):
        for quality in ("7#9", "7b9", "7#5", "7b5", "alt7"):
            idx = map_277_to_170(CHORD_TO_IDX[f"A:{quality}"])
            assert CHORD_VOCAB_170[idx] == "A:7"

    def test_sixth_chords_rename(self):
        assert CHORD_VOCAB_170[map_277_to_170(CHORD_TO_IDX["F:6"])] == "F:maj6"
        assert CHORD_VOCAB_170[map_277_to_170(CHORD_TO_IDX["F:min6"])] == "F:min6"

    def test_7sus4_drops_seventh(self):
        assert CHORD_VOCAB_170[map_277_to_170(CHORD_TO_IDX["G:7sus4"])] == "G:sus4"

    def test_map_covers_all_23_qualities(self):
        assert len(QUALITY_MAP_277_TO_170) == 23

    def test_mapped_qualities_are_supported(self):
        mapped_qualities = set(QUALITY_MAP_277_TO_170.values())
        assert mapped_qualities <= set(QUALITIES_14)

    def test_minmaj7_and_hdim7_have_no_277_source(self):
        mapped_qualities = set(QUALITY_MAP_277_TO_170.values())
        assert "minmaj7" not in mapped_qualities
        assert "hdim7" not in mapped_qualities

    def test_vectorized_table_matches_function(self):
        for idx in range(NUM_CLASSES):
            assert MAP_277_TO_170_TABLE[idx] == map_277_to_170(idx)


class Test277VocabUnchanged:
    def test_277_vocab_still_intact(self):
        assert len(CHORD_VOCAB) == 277
        assert "N" in CHORD_VOCAB

    def test_all_277_qualities_have_explicit_mapping(self):
        from app.chord_vocab import CHORD_INTERVALS

        assert set(QUALITY_MAP_277_TO_170) == set(CHORD_INTERVALS)
