"""Tests for Commit 99: Viterbi chord decoder."""

from __future__ import annotations

import numpy as np
import pytest

from app.viterbi_decoder import ViterbiChordDecoder, probs_to_log_probs
from app.chord_inference import CHORD_VOCAB


def _make_uniform_emissions(T: int, vocab_size: int = 277) -> np.ndarray:
    probs = np.ones((T, vocab_size), dtype=np.float32) / vocab_size
    return probs


def _make_peaked_emissions(
    T: int, peak_indices: list[int], vocab_size: int = 277, peak_val: float = 0.8
) -> np.ndarray:
    """Create emission probs where each time step has a clear peak."""
    probs = np.ones((T, vocab_size), dtype=np.float32) * (1 - peak_val) / (vocab_size - 1)
    for t, idx in enumerate(peak_indices):
        probs[t, idx] = peak_val
    return probs


class TestProbsToLogProbs:
    def test_basic_conversion(self):
        probs = np.array([0.5, 0.3, 0.2])
        log_probs = probs_to_log_probs(probs)
        assert log_probs.shape == probs.shape
        assert np.all(np.isfinite(log_probs))

    def test_floor_prevents_inf(self):
        probs = np.array([0.0, 1e-50, 0.5])
        log_probs = probs_to_log_probs(probs)
        assert not np.any(np.isinf(log_probs))

    def test_log_probs_are_negative(self):
        probs = np.array([0.5, 0.3, 0.2])
        log_probs = probs_to_log_probs(probs)
        assert np.all(log_probs <= 0)


class TestViterbiSingleStep:
    def test_single_step_returns_argmax(self):
        vocab_size = 5
        trans_log = np.log(np.ones((vocab_size, vocab_size)) / vocab_size)
        emissions = np.array([[0.1, 0.6, 0.1, 0.1, 0.1]])
        emission_log = probs_to_log_probs(emissions)

        decoder = ViterbiChordDecoder(trans_log, vocab_size=vocab_size)
        path, _ = decoder.decode(emission_log)

        assert len(path) == 1
        assert path[0] == 1

    def test_empty_input(self):
        vocab_size = 5
        trans_log = np.log(np.ones((vocab_size, vocab_size)) / vocab_size)
        emission_log = np.empty((0, vocab_size), dtype=np.float64)

        decoder = ViterbiChordDecoder(trans_log, vocab_size=vocab_size)
        path, log_probs = decoder.decode(emission_log)

        assert len(path) == 0
        assert len(log_probs) == 0


class TestViterbiForwardPass:
    def test_known_sequence_recovery(self):
        """Viterbi should recover a known sequence when emissions are clear."""
        vocab_size = 5
        trans_log = np.log(np.ones((vocab_size, vocab_size)) / vocab_size)
        peak_indices = [0, 1, 2, 3, 4]
        emissions = _make_peaked_emissions(5, peak_indices, vocab_size, peak_val=0.9)
        emission_log = probs_to_log_probs(emissions)

        decoder = ViterbiChordDecoder(trans_log, vocab_size=vocab_size)
        path, _ = decoder.decode(emission_log)

        np.testing.assert_array_equal(path, np.array(peak_indices, dtype=np.int32))

    def test_transition_bias_overrides_weak_emission(self):
        """Strong transition prior should override weak emission signal."""
        vocab_size = 3
        trans = np.array([
            [0.50, 0.30, 0.20],
            [0.20, 0.50, 0.30],
            [0.30, 0.20, 0.50],
        ], dtype=np.float32)
        trans_log = np.log(trans)

        emissions = np.array([
            [0.50, 0.25, 0.25],
            [0.25, 0.50, 0.25],
            [0.25, 0.25, 0.50],
        ], dtype=np.float32)
        emission_log = probs_to_log_probs(emissions)

        decoder = ViterbiChordDecoder(trans_log, vocab_size=vocab_size)
        path, _ = decoder.decode(emission_log)

        np.testing.assert_array_equal(path, np.array([0, 1, 2], dtype=np.int32))


class TestViterbiBacktracking:
    def test_backtracking_produces_valid_path(self):
        vocab_size = 4
        trans_log = np.log(np.ones((vocab_size, vocab_size)) / vocab_size)
        emissions = _make_peaked_emissions(10, [0, 1, 2, 3, 0, 1, 2, 3, 0, 1], vocab_size)
        emission_log = probs_to_log_probs(emissions)

        decoder = ViterbiChordDecoder(trans_log, vocab_size=vocab_size)
        path, log_probs = decoder.decode(emission_log)

        assert len(path) == 10
        assert len(log_probs) == 10
        assert np.all(np.isfinite(log_probs))
        assert np.all(path >= 0) and np.all(path < vocab_size)


class TestDurationPenalty:
    def test_sub_beat_penalty_reduces_emission(self):
        vocab_size = 5
        trans_log = np.log(np.ones((vocab_size, vocab_size)) / vocab_size)
        chord_vocab = ["C:maj", "D:min", "E:min", "F:maj", "G:7"]

        emissions = _make_peaked_emissions(1, [2], vocab_size, peak_val=0.7)
        emission_log = probs_to_log_probs(emissions)

        decoder = ViterbiChordDecoder(
            trans_log, vocab_size=vocab_size, chord_vocab=chord_vocab
        )
        path_no_penalty, _ = decoder.decode(emission_log, duration_beats=np.array([1.0]))
        path_penalty, _ = decoder.decode(emission_log, duration_beats=np.array([0.25]))

        assert len(path_no_penalty) == 1
        assert len(path_penalty) == 1

    def test_dominant_chords_get_reduced_penalty(self):
        vocab_size = 5
        trans_log = np.log(np.ones((vocab_size, vocab_size)) / vocab_size)
        chord_vocab = ["C:maj", "D:min", "E:min", "F:maj", "G:7"]

        emissions = np.ones((1, vocab_size), dtype=np.float32) / vocab_size
        emissions[0, 4] = 0.4
        emissions[0, 0] = 0.35
        emission_log = probs_to_log_probs(emissions)

        decoder = ViterbiChordDecoder(
            trans_log, vocab_size=vocab_size, chord_vocab=chord_vocab
        )

        path, _ = decoder.decode(emission_log, duration_beats=np.array([0.3]))
        assert len(path) == 1

    def test_no_penalty_for_full_beat(self):
        vocab_size = 3
        trans_log = np.log(np.ones((vocab_size, vocab_size)) / vocab_size)
        chord_vocab = ["C:maj", "D:min", "G:7"]

        emissions = _make_peaked_emissions(1, [1], vocab_size, peak_val=0.8)
        emission_log = probs_to_log_probs(emissions)

        decoder = ViterbiChordDecoder(
            trans_log, vocab_size=vocab_size, chord_vocab=chord_vocab
        )
        path, log_probs = decoder.decode(emission_log, duration_beats=np.array([1.0]))

        assert path[0] == 1


class TestNumericalStability:
    def test_no_nan_or_inf_in_delta(self):
        vocab_size = 5
        trans_log = np.log(np.ones((vocab_size, vocab_size)) / vocab_size)
        emissions = _make_peaked_emissions(20, [0] * 20, vocab_size, peak_val=0.6)
        emission_log = probs_to_log_probs(emissions)

        decoder = ViterbiChordDecoder(trans_log, vocab_size=vocab_size)
        path, log_probs = decoder.decode(emission_log)

        assert not np.any(np.isnan(log_probs))
        assert not np.any(np.isinf(log_probs))

    def test_very_low_emissions_handled(self):
        vocab_size = 5
        trans_log = np.log(np.ones((vocab_size, vocab_size)) / vocab_size)
        emissions = np.full((3, vocab_size), 1e-20, dtype=np.float32)
        emission_log = probs_to_log_probs(emissions)

        decoder = ViterbiChordDecoder(trans_log, vocab_size=vocab_size)
        path, log_probs = decoder.decode(emission_log)

        assert len(path) == 3
        assert not np.any(np.isnan(log_probs))


class TestViterbiWithChordVocab:
    def test_chord_vocab_enables_duration_logic(self):
        vocab_size = 277
        trans_log = np.log(np.ones((vocab_size, vocab_size)) / vocab_size)

        emissions = _make_peaked_emissions(3, [0, 100, 200], vocab_size, peak_val=0.7)
        emission_log = probs_to_log_probs(emissions)

        decoder = ViterbiChordDecoder(
            trans_log, vocab_size=vocab_size, chord_vocab=CHORD_VOCAB
        )
        path, _ = decoder.decode(
            emission_log,
            duration_beats=np.array([0.5, 1.0, 0.25]),
            duration_penalty_weight=0.5,
        )

        assert len(path) == 3
        assert np.all(path >= 0) and np.all(path < vocab_size)
