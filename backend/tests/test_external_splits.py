"""Tests for external gate split generation (Stage A)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from scripts.make_external_splits import (  # noqa: E402
    _pseudo_real_id,
    _stratified_holdout,
)


def _profiles():
    # hdim7 is the rarest quality (2 tracks) → must appear in the holdout.
    return {
        "t01": {"maj"},
        "t02": {"maj", "min"},
        "t03": {"min"},
        "t04": {"7"},
        "t05": {"7", "hdim7"},
        "t06": {"hdim7"},
        "t07": {"maj7"},
        "t08": {"maj7"},
        "t09": {"sus4"},
        "t10": {"sus4"},
    }


def test_holdout_is_deterministic():
    ids = sorted(_profiles())
    a = _stratified_holdout(ids, _profiles(), val_frac=0.2, test_frac=0.2, seed=0)
    b = _stratified_holdout(ids, _profiles(), val_frac=0.2, test_frac=0.2, seed=0)
    assert a == b


def test_holdout_has_no_overlap_and_covers_rare_qualities():
    ids = sorted(_profiles())
    profiles = _profiles()
    test, val = _stratified_holdout(ids, profiles, val_frac=0.2, test_frac=0.2, seed=0)
    assert not set(test) & set(val)
    assert len(test) == 2 and len(val) == 2
    test_qualities = set().union(*(profiles[t] for t in test))
    # The rarest quality (2 tracks) must be represented in the test set.
    assert "hdim7" in test_qualities
    assert len(test_qualities) >= 2


def test_holdout_seed_changes_fill_order():
    ids = sorted(_profiles())
    # With a large holdout the hash fill dominates; the seed changes it.
    a, _ = _stratified_holdout(ids, _profiles(), val_frac=0.2, test_frac=0.5, seed=0)
    b, _ = _stratified_holdout(ids, _profiles(), val_frac=0.2, test_frac=0.5, seed=7)
    assert a != b


def test_pseudo_real_id_mapping():
    assert _pseudo_real_id(
        "idmt_raw:dataset4/Career SG/fast/classical/audio/classical_1_80BPM"
    ) == "classical_classical_1_80BPM"
    assert _pseudo_real_id("youtube:abc_D_maj") is None
