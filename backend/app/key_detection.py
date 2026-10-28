"""Krumhansl-Schmuckler key estimation from chroma vectors.

The estimator uses Pearson correlation between the mean chroma vector and
rotated major/minor key profiles. Root names use sharps to match the chord
vocabulary (``C#`` rather than ``Db``).
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

KS_MAJOR = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=np.float64,
)
KS_MINOR = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=np.float64,
)


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    """Return the Pearson correlation, or 0.0 for a constant vector."""
    a_centered = a - a.mean()
    b_centered = b - b.mean()
    denom = float(np.linalg.norm(a_centered) * np.linalg.norm(b_centered))
    if denom < 1e-12:
        return 0.0
    return float(np.dot(a_centered, b_centered) / denom)


def estimate_key_from_chroma(chroma_mean: Sequence[float]) -> tuple[int, str, float]:
    """Estimate the key root, mode, and confidence from a 12-bin chroma vector.

    Args:
        chroma_mean: Mean chroma vector, one value per pitch class (C=0).

    Returns:
        ``(root_index_0_11, mode, confidence)`` where mode is ``"major"`` or
        ``"minor"`` and confidence is the best Pearson correlation clipped to
        ``[0.0, 1.0]``.

    Raises:
        ValueError: If *chroma_mean* does not contain exactly 12 values.
    """
    chroma = np.asarray(list(chroma_mean), dtype=np.float64)
    if chroma.shape != (12,):
        raise ValueError("chroma_mean must contain exactly 12 values")
    if not np.all(np.isfinite(chroma)):
        raise ValueError("chroma_mean must contain only finite values")

    best_corr = -np.inf
    best_root = 0
    best_mode = "major"

    for mode, profile in (("major", KS_MAJOR), ("minor", KS_MINOR)):
        for root in range(12):
            rotated = np.roll(profile, root)
            corr = _pearson(chroma, rotated)
            if corr > best_corr:
                best_corr = corr
                best_root = root
                best_mode = mode

    confidence = float(np.clip(best_corr, 0.0, 1.0))
    return best_root, best_mode, confidence


def estimate_key_literal(chroma_mean: Sequence[float]) -> tuple[str, str]:
    """Return ``(root_name, mode)`` for a 12-bin chroma vector."""
    root, mode, _ = estimate_key_from_chroma(chroma_mean)
    return PITCH_NAMES[root], mode
