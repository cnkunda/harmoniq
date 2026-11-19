"""Tests for the quality-balanced Slakh subset selector."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_vocab_170 import BASS_X_IDX, CHORD_TO_IDX_170, N_IDX_170  # noqa: E402
from scripts.build_slakh_subset import (  # noqa: E402
    _hash_sample,
    greedy_cover,
    track_profile,
)


class TestTrackProfile:
    def test_classes_and_inversions(self):
        labels = np.array([CHORD_TO_IDX_170["C:maj"],
                           CHORD_TO_IDX_170["C:maj"],
                           N_IDX_170])
        bass = np.array([0, 4, BASS_X_IDX])
        profile = track_profile(labels, bass)
        assert profile["classes"] == {CHORD_TO_IDX_170["C:maj"]}
        assert profile["inversions"] == {0, 1}
        assert profile["n_rate"] == 1 / 3

    def test_i_iv_v(self):
        labels = np.array([CHORD_TO_IDX_170["C:maj"],
                           CHORD_TO_IDX_170["F:maj"],
                           CHORD_TO_IDX_170["G:7"]])
        profile = track_profile(labels, np.array([0, 5, 7]))
        assert len(profile["classes"]) == 3
        assert profile["inversions"] == {0}


class TestGreedyCover:
    def test_prefers_new_coverage(self):
        profiles = {
            "a": {"classes": {1}, "inversions": {0}},
            "b": {"classes": {2}, "inversions": {0}},
            "c": {"classes": {1, 2}, "inversions": {1}},
        }
        selected = greedy_cover(profiles, 2, seed=0)
        assert selected[0] == "c"
        assert len(selected) == 2

    def test_hash_sample_is_deterministic(self):
        ids = [f"Track{i:05d}" for i in range(20)]
        first = _hash_sample(ids, 5, seed=3)
        second = _hash_sample(ids, 5, seed=3)
        assert first == second
        assert len(set(first)) == 5
