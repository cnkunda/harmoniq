"""Shared thresholds and guards for scoring reliability (v2 contract)."""

from __future__ import annotations

from dataclasses import dataclass


SCORE_CONTRACT_VERSION = "v2"

# Audio / signal quality guards.
MIN_VALID_RMS = 1e-4
LOW_SIGNAL_RMS = 2.5e-3
LOW_SIGNAL_VOICED_RATIO = 0.18
HIGH_CONFIDENCE_VOICED_RATIO = 0.62
HIGH_CONFIDENCE_HARMONIC_RATIO = 0.5

# Defensive clipping to avoid NaN/inf drift.
MAX_ABS_NOTE_DELTA_SECONDS = 0.25
MAX_BEND_ERROR_CENTS = 120.0


@dataclass(frozen=True)
class ReliabilityBands:
    low_max: float = 0.39
    medium_max: float = 0.74


RELIABILITY_BANDS = ReliabilityBands()


def clamp01(value: float) -> float:
    if value != value:  # NaN
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value

