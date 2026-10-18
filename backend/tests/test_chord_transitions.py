"""Tests for Commit 99: Transition matrix builder, caching, and key constraints."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from app.chord_transitions import (
    _CHORD_TO_IDX,
    _ROOTS,
    apply_key_constraint,
    build_transition_matrix,
    get_diatonic_indices,
    get_transition_matrix,
    load_transition_matrix,
    save_transition_matrix,
)
from app.chord_inference import CHORD_VOCAB


class TestTransitionMatrixShape:
    def test_matrix_is_25x25(self):
        matrix = build_transition_matrix()
        assert matrix.shape == (25, 25)

    def test_matrix_is_row_stochastic(self):
        matrix = build_transition_matrix()
        row_sums = matrix.sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-5)

    def test_all_entries_non_negative(self):
        matrix = build_transition_matrix()
        assert np.all(matrix >= 0)


class TestRootIntervalWeights:
    def test_unison_is_competitive(self):
        matrix = build_transition_matrix()
        c_idx = _CHORD_TO_IDX["C:maj"]
        unison_prob = matrix[c_idx, c_idx]
        fifth_prob = matrix[c_idx, _CHORD_TO_IDX["G:maj"]]
        assert unison_prob > fifth_prob * 0.5

    def test_perfect_fifth_is_strong(self):
        matrix = build_transition_matrix()
        c_idx = _CHORD_TO_IDX["C:maj"]
        g_idx = _CHORD_TO_IDX["G:maj"]
        f_idx = _CHORD_TO_IDX["F:maj"]
        assert matrix[c_idx, g_idx] > 0.005
        assert matrix[c_idx, f_idx] > 0.005

    def test_tritone_is_penalized(self):
        matrix = build_transition_matrix()
        c_idx = _CHORD_TO_IDX["C:maj"]
        fs_idx = _CHORD_TO_IDX["F#:maj"]
        g_idx = _CHORD_TO_IDX["G:maj"]
        assert matrix[c_idx, fs_idx] < matrix[c_idx, g_idx]


class TestQualityCompatibility:
    def test_same_quality_persistence(self):
        matrix = build_transition_matrix()
        c_idx = _CHORD_TO_IDX["C:maj"]
        same = matrix[c_idx, c_idx]
        diff = matrix[c_idx, _CHORD_TO_IDX["D:maj"]]
        assert same > diff


class TestNoChordTransitions:
    def test_n_to_n_is_highest_in_row(self):
        matrix = build_transition_matrix()
        n_idx = _CHORD_TO_IDX["N"]
        n_row = matrix[n_idx]
        assert n_row[n_idx] > n_row.max() * 0.5

    def test_n_to_chord_is_low(self):
        matrix = build_transition_matrix()
        n_idx = _CHORD_TO_IDX["N"]
        c_idx = _CHORD_TO_IDX["C:maj"]
        assert matrix[n_idx, c_idx] < 0.05

    def test_chord_to_n_is_low(self):
        matrix = build_transition_matrix()
        c_idx = _CHORD_TO_IDX["C:maj"]
        n_idx = _CHORD_TO_IDX["N"]
        assert matrix[c_idx, n_idx] < 0.05


class TestCaching:
    def test_save_and_load_roundtrip(self):
        matrix = build_transition_matrix()
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_matrix.npy"
            save_transition_matrix(matrix, cache_path)
            loaded = load_transition_matrix(cache_path)
            np.testing.assert_allclose(np.array(loaded), matrix, atol=1e-6)

    def test_cache_miss_builds_matrix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_matrix.npy"
            matrix = load_transition_matrix(cache_path)
            assert cache_path.exists()
            assert matrix.shape == (25, 25)


class TestKeyConstraints:
    def test_g_major_diatonic_chords(self):
        indices = get_diatonic_indices(key_root=7, key_mode="major")
        expected_labels = {
            "G:maj", "A:min", "B:min", "C:maj",
            "D:maj", "E:min", "F#:min",
        }
        expected_indices = {_CHORD_TO_IDX[label] for label in expected_labels}
        assert indices == expected_indices

    def test_a_minor_diatonic_chords(self):
        indices = get_diatonic_indices(key_root=9, key_mode="minor")
        expected_labels = {
            "A:min", "B:min", "C:maj", "D:min",
            "E:min", "F:maj", "G:maj",
        }
        expected_indices = {_CHORD_TO_IDX[label] for label in expected_labels}
        assert indices == expected_indices

    def test_key_constraint_penalizes_non_diatonic(self):
        matrix = build_transition_matrix()
        constrained = apply_key_constraint(matrix, key_root=7, key_mode="major")

        g_idx = _CHORD_TO_IDX["G:maj"]
        fs_idx = _CHORD_TO_IDX["F#:maj"]

        assert constrained[g_idx, fs_idx] < matrix[g_idx, fs_idx]

    def test_key_constraint_preserves_diatonic_transitions(self):
        matrix = build_transition_matrix()
        constrained = apply_key_constraint(matrix, key_root=7, key_mode="major")

        g_idx = _CHORD_TO_IDX["G:maj"]
        d_idx = _CHORD_TO_IDX["D:maj"]

        diatonic_ratio = constrained[g_idx, d_idx] / max(matrix[g_idx, d_idx], 1e-10)
        non_diatonic_ratio = constrained[g_idx, _CHORD_TO_IDX["F#:maj"]] / max(
            matrix[g_idx, _CHORD_TO_IDX["F#:maj"]], 1e-10
        )
        assert diatonic_ratio > non_diatonic_ratio

    def test_tritone_non_diatonic_heavily_penalized(self):
        matrix = build_transition_matrix()
        constrained = apply_key_constraint(matrix, key_root=0, key_mode="major")

        c_idx = _CHORD_TO_IDX["C:maj"]
        fs_idx = _CHORD_TO_IDX["F#:maj"]

        assert constrained[c_idx, fs_idx] < 0.01

    def test_constrained_matrix_is_row_stochastic(self):
        matrix = build_transition_matrix()
        constrained = apply_key_constraint(matrix, key_root=7, key_mode="major")
        row_sums = constrained.sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-5)

    def test_base_matrix_not_mutated(self):
        matrix = build_transition_matrix()
        original = matrix.copy()
        apply_key_constraint(matrix, key_root=7, key_mode="major")
        np.testing.assert_allclose(matrix, original, atol=1e-6)


class TestChordToIdxMapping:
    def test_all_vocab_entries_mapped(self):
        for chord in CHORD_VOCAB:
            assert chord in _CHORD_TO_IDX

    def test_mapping_is_bijective(self):
        assert len(_CHORD_TO_IDX) == len(CHORD_VOCAB)
        inverse = {v: k for k, v in _CHORD_TO_IDX.items()}
        for idx in range(len(CHORD_VOCAB)):
            assert inverse[idx] == CHORD_VOCAB[idx]
