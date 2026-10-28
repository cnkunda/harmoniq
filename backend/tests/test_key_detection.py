"""Tests for normalized Krumhansl-Schmuckler key estimation."""

from __future__ import annotations

import numpy as np
import pytest

from app.key_detection import (
    KS_MAJOR,
    KS_MINOR,
    PITCH_NAMES,
    estimate_key_from_chroma,
    estimate_key_literal,
)
from app.pipeline_proof import estimate_key_literal as pipeline_estimate_key_literal


def _profile_chroma(root: int, mode: str) -> np.ndarray:
    profile = KS_MAJOR if mode == "major" else KS_MINOR
    return np.roll(profile, root)


@pytest.mark.parametrize("root", range(12))
@pytest.mark.parametrize("mode", ["major", "minor"])
def test_exact_profiles_round_trip(root: int, mode: str):
    estimated_root, estimated_mode, confidence = estimate_key_from_chroma(
        _profile_chroma(root, mode)
    )
    assert estimated_root == root
    assert estimated_mode == mode
    assert confidence > 0.99


def test_c_major_full_profile():
    root, mode, confidence = estimate_key_from_chroma(KS_MAJOR)
    assert (PITCH_NAMES[root], mode) == ("C", "major")
    assert confidence > 0.99


def test_c_sharp_minor_full_profile():
    root, mode, confidence = estimate_key_from_chroma(_profile_chroma(1, "minor"))
    assert (PITCH_NAMES[root], mode) == ("C#", "minor")
    assert confidence > 0.99


def test_pipeline_wrapper_matches_shared_estimator():
    chroma = _profile_chroma(7, "major")
    assert estimate_key_literal(chroma) == ("G", "major")
    assert pipeline_estimate_key_literal(chroma) == ("G", "major")


def test_flat_chroma_has_zero_confidence():
    root, mode, confidence = estimate_key_from_chroma(np.ones(12))
    assert confidence == 0.0
    assert (PITCH_NAMES[root], mode) == ("C", "major")


def test_wrong_length_raises():
    with pytest.raises(ValueError):
        estimate_key_from_chroma([0.0] * 11)
