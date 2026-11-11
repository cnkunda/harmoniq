"""W0: forced-tier escape hatch used by the evaluation baselines."""

from __future__ import annotations

import numpy as np
import pytest

from app import chord_inference


def _audio() -> np.ndarray:
    return np.zeros(4096, dtype=np.float32)


def test_force_chroma_skips_neural_models(monkeypatch):
    monkeypatch.setattr(
        chord_inference,
        "_run_chroma_raw",
        lambda y, sr: [{"chord": "C:maj", "confidence": 0.5, "time": 0.0}],
    )
    monkeypatch.setattr(
        chord_inference,
        "_run_keras_raw",
        lambda y, sr: pytest.fail("Keras should not run for forced chroma"),
    )
    frames = chord_inference._run_inference(_audio(), 22050, force_tier="chroma")
    assert frames[0]["chord"] == "C:maj"
    assert chord_inference.get_last_inference_tier() == "chroma"


def test_force_crnn_returns_keras_without_falling_through(monkeypatch):
    monkeypatch.setattr(
        chord_inference,
        "_run_keras_raw",
        lambda y, sr: [{"chord": "G:maj", "confidence": 0.7, "time": 0.0}],
    )
    monkeypatch.setattr(
        chord_inference,
        "_run_chroma_raw",
        lambda y, sr: pytest.fail("chroma should not run for forced CRNN"),
    )
    frames = chord_inference._run_inference(_audio(), 22050, force_tier="crnn")
    assert frames[0]["chord"] == "G:maj"
    assert chord_inference.get_last_inference_tier() == "crnn"


def test_force_crnn_fails_loudly_when_unavailable(monkeypatch):
    def _boom(y, sr):
        raise RuntimeError("model missing")

    monkeypatch.setattr(chord_inference, "_run_keras_raw", _boom)
    monkeypatch.setattr(chord_inference, "_run_tflite_raw", _boom)
    with pytest.raises(RuntimeError, match="CRNN tier requested"):
        chord_inference._run_inference(_audio(), 22050, force_tier="crnn")


def test_invalid_force_tier_fails_loudly():
    with pytest.raises(ValueError, match="unsupported force_tier"):
        chord_inference._run_inference(_audio(), 22050, force_tier="bogus")
