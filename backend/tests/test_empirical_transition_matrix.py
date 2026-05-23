"""Tests for Isophonics/Billboard empirical transition matrix builder (Commit 101)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_TO_IDX, ROOT_NOTES, CHORD_QUALITIES, NUM_CLASSES
from scripts.build_empirical_transition_matrix import (
    _parse_lab_label,
    _parse_lab_file,
    build_transition_counts,
    build_empirical_matrix,
    gather_lab_files,
)


# ---------------------------------------------------------------------------
# _parse_lab_label
# ---------------------------------------------------------------------------

class TestParseLabLabel:
    def test_harte_major(self):
        assert _parse_lab_label("C:maj") == "C:maj"

    def test_harte_minor(self):
        assert _parse_lab_label("D:min") == "D:min"

    def test_dominant_seventh(self):
        assert _parse_lab_label("G:7") == "G:7"

    def test_flat_root(self):
        assert _parse_lab_label("Bb:maj") == "A#:maj"

    def test_sharp_root(self):
        assert _parse_lab_label("F#:min") == "F#:min"

    def test_no_chord(self):
        assert _parse_lab_label("N") is None

    def test_billboard_star(self):
        assert _parse_lab_label("*") is None

    def test_billboard_pause(self):
        assert _parse_lab_label("&pause") is None

    def test_billboard_dot_repeat(self):
        assert _parse_lab_label(".", prev_label="C:maj") == "C:maj"

    def test_billboard_dot_no_prev(self):
        assert _parse_lab_label(".", prev_label=None) is None

    def test_billboard_one_bass(self):
        assert _parse_lab_label("1") is None

    def test_billboard_five_power(self):
        # Power chord "5" has no root note — can't map to 277 vocabulary
        assert _parse_lab_label("5") is None

    def test_shorthand_root_only(self):
        assert _parse_lab_label("C") == "C:maj"

    def test_shorthand_am(self):
        assert _parse_lab_label("Am") == "A:min"

    def test_shorthand_bb7(self):
        assert _parse_lab_label("Bb7") == "A#:7"

    def test_with_alterations_stripped(self):
        assert _parse_lab_label("C:maj7(#11)") == "C:maj7"

    def test_with_bass_note_stripped(self):
        assert _parse_lab_label("C:maj/G") == "C:maj"

    def test_hdim7_mapped(self):
        assert _parse_lab_label("B:hdim7") == "B:dim7"

    def test_minmaj7_mapped(self):
        assert _parse_lab_label("C:minmaj7") == "C:maj7"

    def test_min11_mapped(self):
        assert _parse_lab_label("D:min11") == "D:11"

    def test_maj11_mapped(self):
        assert _parse_lab_label("C:maj11") == "C:11"


# ---------------------------------------------------------------------------
# _parse_lab_file
# ---------------------------------------------------------------------------

class TestParseLabFile:
    def test_simple_lab(self, tmp_path):
        content = """0.000000	0.500000	C:maj
0.500000	1.000000	G:7
1.000000	2.000000	C:maj
"""
        lf = tmp_path / "test.lab"
        lf.write_text(content)
        entries = _parse_lab_file(lf)
        assert len(entries) == 3
        assert entries[0] == (0.0, 0.5, "C:maj")
        assert entries[1] == (0.5, 1.0, "G:7")
        assert entries[2] == (1.0, 2.0, "C:maj")

    def test_with_no_chords(self, tmp_path):
        content = """0.0	1.0	N
1.0	2.0	C:maj
"""
        lf = tmp_path / "silence.lab"
        lf.write_text(content)
        entries = _parse_lab_file(lf)
        assert len(entries) == 2
        assert entries[0] == (0.0, 1.0, None)
        assert entries[1] == (1.0, 2.0, "C:maj")

    def test_billboard_dot_expansion(self, tmp_path):
        content = """0.0	1.0	C:maj
1.0	2.0	.
2.0	3.0	D:min
"""
        lf = tmp_path / "dot.lab"
        lf.write_text(content)
        entries = _parse_lab_file(lf)
        assert len(entries) == 3
        assert entries[0] == (0.0, 1.0, "C:maj")
        assert entries[1] == (1.0, 2.0, "C:maj")  # dot expanded to C:maj
        assert entries[2] == (2.0, 3.0, "D:min")

    def test_billboard_special_markers(self, tmp_path):
        content = """0.0	1.0	C:maj
1.0	2.0	*
2.0	3.0	&pause
3.0	4.0	1
"""
        lf = tmp_path / "special.lab"
        lf.write_text(content)
        entries = _parse_lab_file(lf)
        assert len(entries) == 4
        assert entries[1][2] is None  # * → None
        assert entries[2][2] is None  # &pause → None
        assert entries[3][2] is None  # 1 → None

    def test_power_chord(self, tmp_path):
        content = """0.0	1.0	5
1.0	2.0	C:maj
"""
        lf = tmp_path / "power.lab"
        lf.write_text(content)
        entries = _parse_lab_file(lf)
        assert len(entries) == 2
        assert entries[0][2] is None  # power chord skipped


# ---------------------------------------------------------------------------
# build_transition_counts
# ---------------------------------------------------------------------------

class TestBuildTransitionCounts:
    def test_simple_progression(self, tmp_path):
        content = """0.0	1.0	C:maj
1.0	2.0	G:7
2.0	3.0	C:maj
"""
        lf = tmp_path / "simple.lab"
        lf.write_text(content)
        counts, starts, quality_freq = build_transition_counts([lf])
        assert counts.shape == (NUM_CLASSES, NUM_CLASSES)
        # C:maj → G:7 transition
        c_maj_idx = CHORD_TO_IDX["C:maj"]
        g_7_idx = CHORD_TO_IDX["G:7"]
        assert counts[c_maj_idx, g_7_idx] >= 1
        assert counts[g_7_idx, c_maj_idx] >= 1
        # Quality distribution
        assert quality_freq["maj"] >= 2  # C:maj appears twice
        assert quality_freq["7"] >= 1

    def test_empty_file(self, tmp_path):
        lf = tmp_path / "empty.lab"
        lf.write_text("")
        counts, starts, quality_freq = build_transition_counts([lf])
        assert counts.sum() == 0

    def test_single_chord_no_transition(self, tmp_path):
        content = """0.0	2.0	C:maj
"""
        lf = tmp_path / "single.lab"
        lf.write_text(content)
        counts, starts, quality_freq = build_transition_counts([lf])
        assert counts.sum() == 0
        assert quality_freq["maj"] == 1


class TestBuildEmpiricalMatrix:
    def test_shape_and_stochastic(self):
        counts = np.random.randint(0, 10, size=(NUM_CLASSES, NUM_CLASSES)).astype(np.int64)
        matrix = build_empirical_matrix(counts, smoothing=1.0)
        assert matrix.shape == (NUM_CLASSES, NUM_CLASSES)
        row_sums = matrix.sum(axis=1)
        assert np.allclose(row_sums, 1.0, atol=1e-5)

    def test_smoothing_handles_zero_rows(self):
        counts = np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.int64)
        matrix = build_empirical_matrix(counts, smoothing=1.0)
        assert np.allclose(matrix.sum(axis=1), 1.0, atol=1e-5)

    def test_laplace_smoothing_effect(self):
        counts = np.eye(NUM_CLASSES, dtype=np.int64) * 10
        matrix = build_empirical_matrix(counts, smoothing=1.0)
        # Diagonal should be high but not 1.0 (smoothing distributes mass)
        assert np.allclose(matrix.diagonal().mean(), 0.0, atol=0.5)  # mostly off-diagonal


class TestGatherLabFiles:
    def test_finds_lab_files(self, tmp_path):
        (tmp_path / "isophonics" / "beatles").mkdir(parents=True)
        (tmp_path / "isophonics" / "queen").mkdir(parents=True)
        (tmp_path / "billboard").mkdir(parents=True)

        (tmp_path / "isophonics" / "beatles" / "song1.lab").write_text("")
        (tmp_path / "isophonics" / "queen" / "song2.lab").write_text("")
        (tmp_path / "billboard" / "song3.lab").write_text("")

        files = gather_lab_files(tmp_path)
        assert len(files) == 3
