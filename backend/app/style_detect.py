"""Rule-based musical style label + technique hints for lesson coach context (no extra APIs)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.pipeline_proof import LibrosaSummary


@dataclass(frozen=True)
class StyleDetectionResult:
    style_label: str
    technique_hints: list[str]


def infer_style_from_librosa_summary(summary: LibrosaSummary) -> StyleDetectionResult:
    """
    Derive a coarse style label from librosa summary features.

    Set HARMONIQ_SKIP_STYLE_DETECT=1 to force a generic label (tests / lightweight runs).
    """
    if os.getenv("HARMONIQ_SKIP_STYLE_DETECT") == "1":
        return StyleDetectionResult(style_label="general", technique_hints=[])

    bpm = float(summary.tempo_bpm)
    duration_s = float(summary.duration_s)
    n_segments = len(summary.segments) if summary.segments else 0

    hints: list[str] = []
    if bpm >= 138.0:
        label = "uptempo rock / lead energy"
        hints.extend(["tight alternate picking", "clean muting between phrases"])
    elif bpm <= 88.0:
        label = "slow ballad / expressive phrasing"
        hints.extend(["long sustain", "vibrato control", "space between phrases"])
    else:
        label = "mid-tempo groove"
        hints.extend(["locked-in rhythm", "clear note definition"])

    if duration_s > 180.0:
        hints.append("pace hand tension across longer takes")

    if n_segments >= 4:
        hints.append("smooth transitions when the arrangement shifts sections")

    return StyleDetectionResult(style_label=label, technique_hints=hints[:6])
