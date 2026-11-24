"""Tests for the MuQ feature extraction helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from scripts.extract_muq_features import (  # noqa: E402
    PROJECTION_DIM,
    _frame_labels,
    _projection,
)


def test_projection_shape_and_determinism():
    first = _projection()
    second = _projection()
    assert first.shape == (1024, PROJECTION_DIM)
    assert np.array_equal(first, second)


def test_frame_labels_roundtrip(tmp_path):
    path = tmp_path / "track.npz"
    labels = np.array([[0, 1], [2, 3]], dtype=np.int64)
    bass = np.array([[4, 5], [6, 7]], dtype=np.int64)
    np.savez_compressed(
        path,
        frame_labels=labels,
        frame_bass=bass,
        split=np.bytes_(b"val"),
        track_id=np.bytes_(b"track"),
    )
    flat_labels, flat_bass, split, track_id = _frame_labels(path)
    assert flat_labels.tolist() == [0, 1, 2, 3]
    assert flat_bass.tolist() == [4, 5, 6, 7]
    assert split == "val"
    assert track_id == "track"
