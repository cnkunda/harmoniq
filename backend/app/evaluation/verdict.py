"""Pass/Warn/Fail rubric from docs/EVALUATION.md.

The original 5-song evaluation was manual. This module makes the rubric
explicit and testable so the expanded manifest can carry expected
verdicts and the harness can assert them.

Track-level rules (from docs/EVALUATION.md:25-31):

- pipeline: complete = pass, partial = warn, no result/error = fail;
- chords: any chord with mean confidence >= 0.5 = pass; chords present but
  mean confidence < 0.5 = warn; no chords = fail;
- solo: notes present = pass; notes present but low confidence = warn;
  no notes when the track is expected to have a guitar line = fail.

The overall verdict is the worst component verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Verdict = Literal["pass", "warn", "fail"]

_ORDER: dict[Verdict, int] = {"pass": 0, "warn": 1, "fail": 2}

#: Mean confidence below this is treated as "low" by the rubric.
LOW_CONFIDENCE = 0.5


@dataclass(frozen=True)
class VerdictInput:
    """The minimal signals needed to apply the rubric."""

    completed: bool
    error: str | None
    has_chords: bool
    mean_chord_confidence: float | None
    expects_notes: bool
    has_notes: bool
    mean_note_confidence: float | None
    qualitative: bool = False


def _worst(*verdicts: Verdict) -> Verdict:
    return max(verdicts, key=lambda value: _ORDER[value])


def compute_verdict(signals: VerdictInput) -> Verdict | None:
    """Apply the docs/EVALUATION.md rubric, or None for qualitative tracks."""
    if not signals.completed or signals.error:
        return "fail"
    if signals.qualitative:
        return None

    if not signals.has_chords:
        chord_verdict: Verdict = "fail"
    elif (
        signals.mean_chord_confidence is not None
        and signals.mean_chord_confidence < LOW_CONFIDENCE
    ):
        chord_verdict = "warn"
    else:
        chord_verdict = "pass"

    if not signals.expects_notes:
        return chord_verdict

    if not signals.has_notes:
        solo_verdict: Verdict = "fail"
    elif (
        signals.mean_note_confidence is not None
        and signals.mean_note_confidence < LOW_CONFIDENCE
    ):
        solo_verdict = "warn"
    else:
        solo_verdict = "pass"

    return _worst(chord_verdict, solo_verdict)


def verdict_matches(expected: Verdict | None, actual: Verdict | None) -> bool | None:
    """Return whether the actual verdict matches, or None when no expectation."""
    if expected is None:
        return None
    if actual is None:
        return False
    return expected == actual
