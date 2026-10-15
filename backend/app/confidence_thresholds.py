"""Commit 156: single source of truth for confidence / confusion thresholds.

Coach hedging (`coach.py`), confusion computation (`instrument_confusion.py`),
flagging (`analyze_audio.py`, `score.py`), and confidence bands all import
from here. No duplicated magic numbers.
"""

from __future__ import annotations

import math
from typing import Literal

# ---- Instrument-confusion hedging tiers (0.0–1.0) ----

#: Hedge trigger: at or above this, coach copy hedges about the transcription.
HEDGE_TRIGGER = 0.3

#: Strong-hedge trigger: at or above this, avoid specific technique claims.
STRONG_HEDGE_TRIGGER = 0.6

# ---- Transcription-confidence bands (heuristic, not calibrated) ----

#: Below this the confidence band is "low".
CONFIDENCE_LOW_MAX = 0.5

#: Below this (and at/above CONFIDENCE_LOW_MAX) the band is "medium".
CONFIDENCE_MEDIUM_MAX = 0.75

ConfidenceBand = Literal["low", "medium", "high"]


def normalize_confusion(value: float | int | None) -> float | None:
    """Clamp a confusion value to [0, 1]. NaN and non-numbers become None.

    Missing data means unchanged copy: callers must treat None as "unknown",
    never as 0 or as high.
    """
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    result = float(value)
    if math.isnan(result):
        return None
    return float(max(0.0, min(1.0, result)))


def hedge_tier(value: float | int | None) -> Literal["none", "soft", "strong"]:
    """Map a confusion value to a hedging tier.

    None (missing) and anything below HEDGE_TRIGGER → "none" (prompt and
    copy byte-for-byte unchanged). Out-of-range values are clamped first,
    NaN treated as missing.
    """
    normalized = normalize_confusion(value)
    if normalized is None or normalized < HEDGE_TRIGGER:
        return "none"
    if normalized >= STRONG_HEDGE_TRIGGER:
        return "strong"
    return "soft"


def confidence_band(value: float | int | None) -> ConfidenceBand | None:
    """Map a transcription-confidence score to a coarse band.

    Bands keep the UI from implying false precision: the underlying score
    is a hand-tuned heuristic, not a calibrated probability. None (missing)
    maps to None — unknown quality is not asserted as low.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    result = float(value)
    if math.isnan(result):
        return None
    if result < CONFIDENCE_LOW_MAX:
        return "low"
    if result < CONFIDENCE_MEDIUM_MAX:
        return "medium"
    return "high"
