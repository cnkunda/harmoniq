"""Tests for post-hoc calibration (Stage C)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from scripts.eval_chord_170 import (  # noqa: E402
    apply_calibration,
    expected_calibration_error,
    fit_calibration,
    macro_f1,
)


def _overconfident_probs(n=200, n_classes=10, seed=0):
    rng = np.random.default_rng(seed)
    y = rng.integers(0, n_classes, n)
    probs = np.full((n, n_classes), 0.01, dtype=np.float64)
    # 60% of samples put 0.9 on the wrong class, 40% on the true class.
    for i in range(n):
        target = y[i] if rng.random() < 0.4 else (y[i] + 1) % n_classes
        probs[i, target] = 0.9
    probs /= probs.sum(axis=1, keepdims=True)
    return probs, y


class TestApplyCalibration:
    def test_identity_with_defaults(self):
        probs = np.array([[0.7, 0.3], [0.2, 0.8]])
        out = apply_calibration(probs, {"temperature": 1.0})
        assert np.allclose(out, probs, atol=1e-6)

    def test_rows_sum_to_one(self):
        probs, _ = _overconfident_probs()
        out = apply_calibration(probs, {"temperature": 2.5, "prior_exponent": 0.5})
        assert np.allclose(out.sum(axis=1), 1.0)

    def test_higher_temperature_softens(self):
        probs = np.array([[0.95, 0.05]])
        soft = apply_calibration(probs, {"temperature": 3.0})
        assert soft.max() < probs.max()


class TestFitCalibration:
    def test_improves_or_preserves_supported_macro(self):
        probs, y = _overconfident_probs()
        params = fit_calibration(probs, y)
        before = macro_f1(y, probs.argmax(axis=1), labels=np.unique(y))
        after = macro_f1(y, apply_calibration(probs, params).argmax(axis=1),
                         labels=np.unique(y))
        assert after >= before - 1e-6

    def test_ece_improves_on_overconfident_probs(self):
        probs, y = _overconfident_probs()
        params = fit_calibration(probs, y)
        before = expected_calibration_error(probs, y)
        after = expected_calibration_error(apply_calibration(probs, params), y)
        assert after <= before + 1e-6

    def test_params_are_json_serialisable(self):
        import json

        probs, y = _overconfident_probs(n=50)
        params = fit_calibration(probs, y)
        json.dumps(params)  # raises if not serialisable
