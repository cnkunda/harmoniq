"""Shared fixtures for training pipeline tests."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory with GuitarSet-like structure.

    Creates:
        <tmp>/guitarset/raw/            — empty (audio not needed for unit tests)
        <tmp>/guitarset/processed/timelines/  — empty
        <tmp>/guitarset/processed/cqt/  — empty
        <tmp>/idmt_smt_guitar/          — similar structure
        <tmp>/vst_synthetic/
    """
    roots = [
        "guitarset/raw",
        "guitarset/processed/timelines",
        "guitarset/processed/cqt",
        "idmt_smt_guitar/processed/timelines",
        "idmt_smt_guitar/processed/cqt",
        "vst_synthetic/midi",
        "vst_synthetic/wav",
        "vst_synthetic/processed/cqt",
    ]
    for r in roots:
        (tmp_path / r).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def white_noise_audio() -> tuple[np.ndarray, int]:
    """Short white noise signal at 44.1kHz for CQT extraction tests."""
    import librosa

    sr = 44100
    duration = 1.0
    y = np.random.randn(int(sr * duration)).astype(np.float32) * 0.01
    return y, sr


@pytest.fixture
def sine_wave_audio() -> tuple[np.ndarray, int]:
    """440Hz sine wave at 44.1kHz for CQT extraction tests."""
    import librosa

    sr = 44100
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = (np.sin(2 * np.pi * 440 * t) * 0.1).astype(np.float32)
    return y, sr
