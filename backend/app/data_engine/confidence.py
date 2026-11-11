"""Confidence filtering for W1 pseudo-labels.

The MT3 teacher has no native per-note confidence (the NoteSequence schema
has no confidence field; ``model_server`` falls back to 0.9). The reliable
signal we do have is the chord decoder's template coverage. W1 therefore
filters training windows by the chord confidence at the window centre and
uses the same value as a proxy for note confidence.

This is intentionally conservative and documented; W5 replaces it with a
calibrated signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.chord_vocab import CHORD_TO_IDX

NO_CHORD_INDEX = CHORD_TO_IDX["N"]


@dataclass(frozen=True)
class PseudoLabelConfig:
    """Thresholds for one pseudo-label run."""

    min_chord_confidence: float = 0.60
    min_note_confidence: float = 0.50
    require_chords: bool = False
    min_kept_windows: int = 1


@dataclass(frozen=True)
class ChordInterval:
    start: float
    end: float
    chord: str
    confidence: float


def chord_intervals(events: Sequence, audio_duration: float) -> list[ChordInterval]:
    """Convert decoded chord events into half-open intervals.

    The last event extends to ``audio_duration`` when known; otherwise it
    gets a 1-second tail.
    """
    intervals: list[ChordInterval] = []
    ordered = sorted(events, key=lambda event: float(event.timestamp))
    for index, event in enumerate(ordered):
        start = float(event.timestamp)
        if index + 1 < len(ordered):
            end = float(ordered[index + 1].timestamp)
        elif audio_duration > start:
            end = float(audio_duration)
        else:
            end = start + 1.0
        if end <= start:
            end = start + 1e-3
        intervals.append(
            ChordInterval(
                start=start,
                end=end,
                chord=str(event.chord),
                confidence=float(event.confidence),
            )
        )
    return intervals


def _interval_at(
    intervals: Sequence[ChordInterval], time_s: float
) -> ChordInterval | None:
    for interval in intervals:
        if interval.start <= time_s < interval.end:
            return interval
    return None


def label_windows(
    intervals: Sequence[ChordInterval],
    center_times: Sequence[float],
    config: PseudoLabelConfig,
) -> tuple[list[int], list[float], list[bool]]:
    """Return ``(labels, confidences, keep_mask)`` for every window.

    A window with no covering chord interval is treated as no-chord with
    confidence 0.0, so it is dropped unless the threshold is 0.
    """
    labels: list[int] = []
    confidences: list[float] = []
    keep: list[bool] = []

    for time_s in center_times:
        interval = _interval_at(intervals, float(time_s))
        if interval is None:
            labels.append(NO_CHORD_INDEX)
            confidences.append(0.0)
            keep.append(False)
            continue
        index = CHORD_TO_IDX.get(interval.chord, NO_CHORD_INDEX)
        labels.append(index)
        confidences.append(float(interval.confidence))
        keep.append(float(interval.confidence) >= config.min_chord_confidence)

    return labels, confidences, keep


def has_confident_chord(
    labels: Sequence[int], keep: Sequence[bool]
) -> bool:
    """Whether the kept windows contain at least one non-N chord."""
    return any(
        kept and label != NO_CHORD_INDEX
        for label, kept in zip(labels, keep, strict=True)
    )


def label_distribution(labels: Sequence[int]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for label in labels:
        counts[int(label)] = counts.get(int(label), 0) + 1
    return dict(sorted(counts.items()))
