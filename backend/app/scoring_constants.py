"""Shared thresholds and guards for scoring reliability (v2 contract)."""

from __future__ import annotations

from dataclasses import dataclass


SCORE_CONTRACT_VERSION = "v2"

# Musical tolerance modes (commit 92)
# Expressive mode allows timing drag/push for musical feel
# Technique mode enforces strict timing for precision practice
MUSICAL_TOLERANCE_MODES = {
    "expressive": {"timing_tolerance_ms": 75, "cents_tolerance": 30},
    "technique": {"timing_tolerance_ms": 20, "cents_tolerance": 20},
}

# Default timing tolerance (fallback if mode not specified)
DEFAULT_TIMING_TOLERANCE_MS = 20
DEFAULT_CENTS_TOLERANCE = 20

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

