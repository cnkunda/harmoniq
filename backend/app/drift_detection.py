"""Prediction drift detection for Harmoniq.

Compares current chord prediction distributions against deployment baseline
to detect model drift. Uses KL divergence and chi-squared tests.
"""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("harmoniq.drift_detection")

# ---------------------------------------------------------------------------
# Baseline management
# ---------------------------------------------------------------------------

_baseline_distribution: np.ndarray | None = None
_baseline_path: str | None = None


def load_baseline(path: str | None = None) -> bool:
    """Load the deployment baseline distribution.

    Args:
        path: Path to baseline .npy file. Defaults to HARMONIQ_DRIFT_BASELINE env.

    Returns:
        True if baseline loaded successfully.
    """
    global _baseline_distribution, _baseline_path

    if path is None:
        path = os.getenv("HARMONIQ_DRIFT_BASELINE", "models/drift_baseline.npy")

    try:
        _baseline_distribution = np.load(path)
        _baseline_path = path
        # Normalize
        total = _baseline_distribution.sum()
        if total > 0:
            _baseline_distribution = _baseline_distribution / total
        logger.info("drift_baseline_loaded path=%s shape=%s", path, _baseline_distribution.shape)
        return True
    except Exception as exc:
        logger.warning("drift_baseline_load_failed path=%s exception=%s", path, exc)
        return False


def save_baseline(distribution: np.ndarray, path: str | None = None) -> bool:
    """Save a baseline distribution for future drift detection.

    Args:
        distribution: Raw chord prediction counts.
        path: Output path. Defaults to HARMONIQ_DRIFT_BASELINE env.

    Returns:
        True if saved successfully.
    """
    global _baseline_distribution, _baseline_path

    if path is None:
        path = os.getenv("HARMONIQ_DRIFT_BASELINE", "models/drift_baseline.npy")

    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # Normalize and save
        total = distribution.sum()
        normalized = distribution / total if total > 0 else distribution
        np.save(path, normalized)
        _baseline_distribution = normalized
        _baseline_path = path
        logger.info("drift_baseline_saved path=%s", path)
        return True
    except Exception as exc:
        logger.warning("drift_baseline_save_failed path=%s exception=%s", path, exc)
        return False


def compute_baseline_from_predictions(predictions: list[list[float]]) -> np.ndarray:
    """Compute a baseline distribution from a batch of predictions.

    Args:
        predictions: List of per-frame prediction vectors.

    Returns:
        Normalized distribution over chord classes.
    """
    if not predictions:
        return np.zeros(277)

    # Average across all frames
    avg = np.mean(predictions, axis=0)
    total = avg.sum()
    if total > 0:
        avg = avg / total
    return avg


# ---------------------------------------------------------------------------
# Drift metrics
# ---------------------------------------------------------------------------


def kl_divergence(p: np.ndarray, q: np.ndarray, epsilon: float = 1e-10) -> float:
    """Compute KL(P || Q) between two distributions.

    Args:
        p: True distribution.
        q: Approximate distribution.
        epsilon: Small value to avoid log(0).

    Returns:
        KL divergence (non-negative).
    """
    p = np.clip(p, epsilon, None)
    q = np.clip(q, epsilon, None)
    # Normalize
    p = p / p.sum()
    q = q / q.sum()
    return float(np.sum(p * np.log(p / q)))


def js_divergence(p: np.ndarray, q: np.ndarray, epsilon: float = 1e-10) -> float:
    """Compute Jensen-Shannon divergence between two distributions.

    More stable than KL divergence; bounded in [0, ln(2)].
    """
    p = np.clip(p, epsilon, None)
    q = np.clip(q, epsilon, None)
    p = p / p.sum()
    q = q / q.sum()
    m = 0.5 * (p + q)
    return 0.5 * (kl_divergence(p, m) + kl_divergence(q, m))


def chi_squared_test(observed: np.ndarray, expected: np.ndarray) -> float:
    """Compute chi-squared statistic between observed and expected distributions."""
    observed = np.clip(observed, 1e-10, None)
    expected = np.clip(expected, 1e-10, None)
    # Normalize both
    observed = observed / observed.sum()
    expected = expected / expected.sum()
    return float(np.sum((observed - expected) ** 2 / expected))


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


class DriftResult:
    """Result of a drift detection check."""

    def __init__(
        self,
        is_drifting: bool,
        kl_div: float,
        js_div: float,
        chi_squared: float,
        threshold_kl: float,
        threshold_js: float,
        top_shifted_chords: list[dict[str, Any]],
        message: str,
    ):
        self.is_drifting = is_drifting
        self.kl_divergence = kl_div
        self.js_divergence = js_div
        self.chi_squared = chi_squared
        self.threshold_kl = threshold_kl
        self.threshold_js = threshold_js
        self.top_shifted_chords = top_shifted_chords
        self.message = message

    def to_dict(self) -> dict:
        return {
            "is_drifting": self.is_drifting,
            "kl_divergence": self.kl_divergence,
            "js_divergence": self.js_divergence,
            "chi_squared": self.chi_squared,
            "threshold_kl": self.threshold_kl,
            "threshold_js": self.threshold_js,
            "top_shifted_chords": self.top_shifted_chords,
            "message": self.message,
        }


def detect_drift(
    current_predictions: list[list[float]],
    threshold_kl: float = 0.05,
    threshold_js: float = 0.01,
    top_n: int = 10,
) -> DriftResult:
    """Detect drift by comparing current predictions against baseline.

    Args:
        current_predictions: Per-frame prediction vectors from current batch.
        threshold_kl: KL divergence threshold for drift detection.
        threshold_js: JS divergence threshold for drift detection.
        top_n: Number of top shifted chords to report.

    Returns:
        DriftResult with drift status and metrics.
    """
    global _baseline_distribution

    current_dist = compute_baseline_from_predictions(current_predictions)

    if _baseline_distribution is None:
        if not load_baseline():
            return DriftResult(
                is_drifting=False,
                kl_div=0.0,
                js_div=0.0,
                chi_squared=0.0,
                threshold_kl=threshold_kl,
                threshold_js=threshold_js,
                top_shifted_chords=[],
                message="No baseline available — skipping drift detection",
            )

    # Compute metrics
    kl = kl_divergence(current_dist, _baseline_distribution)
    js = js_divergence(current_dist, _baseline_distribution)
    chi2 = chi_squared_test(current_dist, _baseline_distribution)

    # Find top shifted chords
    diffs = current_dist - _baseline_distribution
    top_indices = np.argsort(np.abs(diffs))[::-1][:top_n]
    top_shifted = []
    for idx in top_indices:
        if abs(diffs[idx]) > 1e-6:
            top_shifted.append({
                "chord_index": int(idx),
                "baseline_freq": round(float(_baseline_distribution[idx]), 6),
                "current_freq": round(float(current_dist[idx]), 6),
                "diff": round(float(diffs[idx]), 6),
            })

    is_drifting = kl > threshold_kl or js > threshold_js

    if is_drifting:
        message = f"Drift detected: KL={kl:.4f} (threshold={threshold_kl}), JS={js:.4f} (threshold={threshold_js})"
        logger.warning("drift_detected kl=%.4f js=%.4f chi2=%.2f", kl, js, chi2)
    else:
        message = f"No drift: KL={kl:.4f}, JS={js:.4f}"
        logger.info("no_drift kl=%.4f js=%.4f", kl, js)

    return DriftResult(
        is_drifting=is_drifting,
        kl_div=kl,
        js_div=js,
        chi_squared=chi2,
        threshold_kl=threshold_kl,
        threshold_js=threshold_js,
        top_shifted_chords=top_shifted,
        message=message,
    )
