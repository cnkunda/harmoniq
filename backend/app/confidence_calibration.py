"""Commit 184: evaluation-only calibration math for the heuristic confidence.

This module is not used by the analysis pipeline. It turns predicted chord
confidence and empirical correctness into reliability bins and Expected
Calibration Error (ECE), so the ECE reported in docs/EVALUATION.md is
reproducible and unit-tested independently of MT3.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from app.chord_vocab import CHORD_TO_IDX, MIREX_TO_IDX, mirex_label

N_INDEX = MIREX_TO_IDX["N"]


@dataclass(frozen=True)
class CalibrationBin:
    """One equal-width confidence bin in a reliability table."""

    lower: float
    upper: float
    count: int
    weight: float
    avg_confidence: float
    accuracy: float

    @property
    def gap(self) -> float:
        """Absolute calibration gap for this bin."""
        return abs(self.accuracy - self.avg_confidence)


def chord_to_mirex_index(chord: str) -> int:
    """Map a decoder/annotation chord label to its 25-class MIREX index.

    Handles both MIREX labels ("D#:maj") and the 277-class vocabulary
    ("D#:maj7"). Unknown labels and "N" map to the no-chord index.
    """
    if chord in MIREX_TO_IDX:
        return MIREX_TO_IDX[chord]
    index_277 = CHORD_TO_IDX.get(chord)
    if index_277 is None:
        return N_INDEX
    return mirex_label(index_277)


def majority_gt_index(
    intervals: Sequence[tuple[float, float, int]],
    start: float,
    end: float,
) -> tuple[int, float]:
    """Return the ground-truth MIREX index covering most of [start, end).

    The second element is the winning overlap in seconds. A zero overlap
    means the interval falls outside the annotated timeline.
    """
    if end <= start:
        return N_INDEX, 0.0

    best_index = N_INDEX
    best_overlap = 0.0
    for gt_start, gt_end, gt_index in intervals:
        overlap = min(end, gt_end) - max(start, gt_start)
        if overlap > best_overlap:
            best_index = gt_index
            best_overlap = overlap
    return best_index, best_overlap


def bin_calibration(
    confidences: Sequence[float],
    correct: Sequence[float],
    weights: Sequence[float],
    *,
    num_bins: int = 10,
) -> list[CalibrationBin]:
    """Group weighted samples into equal-width confidence bins.

    ``correct`` is 1.0 for a correct prediction and 0.0 otherwise. ``weights``
    are durations in seconds, so the table matches the duration-weighted
    heuristic used by ``chord_section_confidence``.
    """
    if num_bins < 1:
        raise ValueError("num_bins must be at least 1")

    conf = np.asarray(confidences, dtype=np.float64)
    corr = np.asarray(correct, dtype=np.float64)
    weight = np.asarray(weights, dtype=np.float64)

    if conf.shape != corr.shape or conf.shape != weight.shape:
        raise ValueError("confidences, correct, and weights must have the same length")
    if conf.size == 0:
        return []
    if not np.all(np.isfinite(conf)) or not np.all(np.isfinite(corr)) or not np.all(np.isfinite(weight)):
        raise ValueError("calibration inputs must be finite")
    if np.any(weight < 0):
        raise ValueError("sample weights must be non-negative")

    conf = np.clip(conf, 0.0, 1.0)
    edges = np.linspace(0.0, 1.0, num_bins + 1)

    bins: list[CalibrationBin] = []
    for index in range(num_bins):
        lower = float(edges[index])
        upper = float(edges[index + 1])
        if index == num_bins - 1:
            mask = (conf >= lower) & (conf <= upper)
        else:
            mask = (conf >= lower) & (conf < upper)

        count = int(mask.sum())
        weight_sum = float(weight[mask].sum())
        if weight_sum > 0.0:
            avg_confidence = float((conf[mask] * weight[mask]).sum() / weight_sum)
            accuracy = float((corr[mask] * weight[mask]).sum() / weight_sum)
        else:
            avg_confidence = 0.0
            accuracy = 0.0

        bins.append(
            CalibrationBin(
                lower=lower,
                upper=upper,
                count=count,
                weight=weight_sum,
                avg_confidence=avg_confidence,
                accuracy=accuracy,
            )
        )

    return bins


def expected_calibration_error(
    bins: Sequence[CalibrationBin],
    *,
    total_weight: float | None = None,
) -> float:
    """Weighted average absolute accuracy/confidence gap across bins."""
    if total_weight is None:
        total_weight = float(sum(item.weight for item in bins))
    if total_weight <= 0.0:
        return 0.0
    return float(
        sum((item.weight / total_weight) * item.gap for item in bins)
    )
