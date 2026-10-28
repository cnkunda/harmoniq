"""Tests for Basic Pitch cache canonicalization."""

from __future__ import annotations

import sys
import types
from pathlib import Path

from app.pipeline_proof import _BASIC_PITCH_CACHE, basic_pitch_predict_events


def test_default_and_explicit_model_share_cache(monkeypatch):
    model_path = Path("/tmp/fake-basic-pitch-model")
    calls = []

    class FakeBasicPitchModule(types.ModuleType):
        ICASSP_2022_MODEL_PATH = model_path

    def fake_predict(audio_path, **kwargs):
        calls.append((audio_path, kwargs))
        return None, None, [(0.0, 0.5, 60, 0.9, None)]

    fake_inference = types.ModuleType("basic_pitch.inference")
    fake_inference.predict = fake_predict

    monkeypatch.setitem(sys.modules, "basic_pitch", FakeBasicPitchModule("basic_pitch"))
    monkeypatch.setitem(sys.modules, "basic_pitch.inference", fake_inference)
    _BASIC_PITCH_CACHE.clear()

    first = basic_pitch_predict_events(
        Path("guitar.wav"), model_path=model_path, midi_tempo=120.0
    )
    second = basic_pitch_predict_events(
        Path("guitar.wav"), model_path=None, midi_tempo=120.0
    )

    assert len(calls) == 1
    assert first == second
    assert len(first) == 1
    assert first[0].pitch_midi == 60
