"""Challenge-style metrics for the W0 evaluation harness.

Metric definitions follow the 2025 AI4Musicians AMT challenge / MIREX
conventions:

- onset match: same pitch (and optionally program) within ±50 ms;
- offset match: onset match plus offset within max(50 ms, 20% of the
  reference note duration);
- multi-instrument: per-program matching, then macro-average in the report;
- overlap: intersection-over-union of matched note intervals;
- dynamics: velocity error / correlation over matched notes;
- chord accuracy: duration-weighted frame accuracy on the 25-class MIREX
  vocabulary;
- calibration: duration-weighted ECE using the shared
  :mod:`app.confidence_calibration` math.

The functions are pure and unit-tested without MT3 or audio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.confidence_calibration import (
    CalibrationBin,
    bin_calibration,
    chord_to_mirex_index,
    expected_calibration_error,
    majority_gt_index,
)
from app.evaluation.ground_truth import GTChord, GTNote

DEFAULT_ONSET_TOLERANCE_S = 0.05
DEFAULT_OFFSET_TOLERANCE_S = 0.05
DEFAULT_OFFSET_DURATION_RATIO = 0.20
DEFAULT_CHORD_HOP_S = 0.10


@dataclass(frozen=True)
class PRF:
    """Precision / recall / F1 with raw counts."""

    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "f1": round(self.f1, 6),
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
        }


def _prf(tp: int, fp: int, fn: int) -> PRF:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    return PRF(precision=precision, recall=recall, f1=f1, tp=tp, fp=fp, fn=fn)


def _offset_tolerance(reference: GTNote) -> float:
    return max(
        DEFAULT_OFFSET_TOLERANCE_S,
        DEFAULT_OFFSET_DURATION_RATIO * reference.duration,
    )


def _same_program(left: GTNote, right: GTNote) -> bool:
    if left.program is None or right.program is None:
        return True
    return int(left.program) == int(right.program)


def match_notes(
    reference: Sequence[GTNote],
    estimate: Sequence[GTNote],
    *,
    onset_tolerance: float = DEFAULT_ONSET_TOLERANCE_S,
    require_offset: bool = False,
    require_program: bool = False,
) -> tuple[list[tuple[int, int]], PRF]:
    """Greedy one-to-one note matching.

    Returns ``(pairs, prf)`` where ``pairs`` contains ``(reference_index,
    estimate_index)``. Each estimate is matched to the closest still-unused
    reference with the same pitch (and program when requested) inside the
    onset tolerance. Offset matching additionally requires the offset
    tolerance when ``require_offset`` is true.
    """
    used_reference: set[int] = set()
    pairs: list[tuple[int, int]] = []

    ordered_reference = sorted(
        range(len(reference)),
        key=lambda idx: (reference[idx].onset, reference[idx].pitch),
    )

    for est_idx, est in enumerate(estimate):
        best_ref: int | None = None
        best_delta = float("inf")
        for ref_idx in ordered_reference:
            if ref_idx in used_reference:
                continue
            ref = reference[ref_idx]
            if ref.pitch != est.pitch:
                continue
            if require_program and not _same_program(ref, est):
                continue
            delta = abs(est.onset - ref.onset)
            if delta > onset_tolerance:
                continue
            if require_offset and abs(est.offset - ref.offset) > _offset_tolerance(ref):
                continue
            if delta < best_delta:
                best_delta = delta
                best_ref = ref_idx
        if best_ref is not None:
            used_reference.add(best_ref)
            pairs.append((best_ref, est_idx))

    tp = len(pairs)
    fp = len(estimate) - tp
    fn = len(reference) - tp
    return pairs, _prf(tp, fp, fn)


def note_metrics(
    reference: Sequence[GTNote],
    estimate: Sequence[GTNote],
    *,
    onset_tolerance: float = DEFAULT_ONSET_TOLERANCE_S,
) -> dict[str, object]:
    """Compute onset, offset, pitch, overlap, dynamics, and instrument scores."""
    pitch_pairs, pitch_prf = match_notes(
        reference, estimate, onset_tolerance=onset_tolerance
    )
    multi_pairs, multi_prf = match_notes(
        reference,
        estimate,
        onset_tolerance=onset_tolerance,
        require_program=True,
    )
    offset_pairs, offset_prf = match_notes(
        reference,
        estimate,
        onset_tolerance=onset_tolerance,
        require_offset=True,
        require_program=True,
    )

    overlaps = [
        _interval_iou(reference[ref_idx], estimate[est_idx])
        for ref_idx, est_idx in offset_pairs
    ]

    velocity_errors = [
        abs(float(reference[ref_idx].velocity) - float(estimate[est_idx].velocity))
        for ref_idx, est_idx in offset_pairs
        if reference[ref_idx].velocity is not None
        and estimate[est_idx].velocity is not None
    ]

    instrument_exact = sum(
        1
        for ref_idx, est_idx in multi_pairs
        if reference[ref_idx].program is not None
        and estimate[est_idx].program is not None
        and int(reference[ref_idx].program) == int(estimate[est_idx].program)
    )
    instrument_family = sum(
        1
        for ref_idx, est_idx in multi_pairs
        if _program_family(reference[ref_idx].program)
        == _program_family(estimate[est_idx].program)
    )

    return {
        "onset_pitch": pitch_prf.as_dict(),
        "onset_multi": multi_prf.as_dict(),
        "offset_multi": offset_prf.as_dict(),
        "overlap_mean": round(sum(overlaps) / len(overlaps), 6) if overlaps else 0.0,
        "dynamics_mae": (
            round(sum(velocity_errors) / len(velocity_errors), 6)
            if velocity_errors
            else None
        ),
        "dynamics_n": len(velocity_errors),
        "instrument_exact": (
            round(instrument_exact / len(multi_pairs), 6) if multi_pairs else None
        ),
        "instrument_family": (
            round(instrument_family / len(multi_pairs), 6) if multi_pairs else None
        ),
        "reference_notes": len(reference),
        "estimated_notes": len(estimate),
    }


def _interval_iou(reference: GTNote, estimate: GTNote) -> float:
    intersection = min(reference.offset, estimate.offset) - max(
        reference.onset, estimate.onset
    )
    if intersection <= 0.0:
        return 0.0
    union = max(reference.offset, estimate.offset) - min(
        reference.onset, estimate.onset
    )
    return intersection / union if union > 0.0 else 0.0


def _program_family(program: int | None) -> int | None:
    if program is None:
        return None
    # General MIDI families are groups of eight programs.
    return int(program) // 8


def _mirex_index(chord: str) -> int:
    return chord_to_mirex_index(chord)


def chord_frame_accuracy(
    reference: Sequence[GTChord],
    estimate: Sequence[GTChord],
    *,
    hop: float = DEFAULT_CHORD_HOP_S,
) -> dict[str, object]:
    """Duration-weighted frame accuracy on the 25-class MIREX vocabulary.

    Frames are sampled on a fixed hop from the union of both timelines.
    Predicted and reference chords are mapped through
    :func:`chord_to_mirex_index`; the reference is the chord covering the
    frame midpoint.
    """
    if not reference or not estimate:
        return {
            "frame_accuracy": 0.0 if reference else None,
            "frames": 0,
            "reference_events": len(reference),
            "estimated_events": len(estimate),
        }

    start = min(min(c.start for c in reference), min(c.start for c in estimate))
    end = max(max(c.end for c in reference), max(c.end for c in estimate))
    if end <= start:
        return {
            "frame_accuracy": 0.0,
            "frames": 0,
            "reference_events": len(reference),
            "estimated_events": len(estimate),
        }

    correct = 0
    total = 0
    frame = start + hop / 2.0
    while frame < end:
        ref_chord = _chord_at(reference, frame)
        est_chord = _chord_at(estimate, frame)
        if ref_chord is not None and est_chord is not None:
            total += 1
            if _mirex_index(ref_chord.chord) == _mirex_index(est_chord.chord):
                correct += 1
        frame += hop

    return {
        "frame_accuracy": round(correct / total, 6) if total else None,
        "frames": total,
        "reference_events": len(reference),
        "estimated_events": len(estimate),
    }


def _chord_at(chords: Sequence[GTChord], time_s: float) -> GTChord | None:
    for chord in chords:
        if chord.start <= time_s < chord.end:
            return chord
    return None


def chord_root(chord: str) -> str:
    """Return the pitch-class root of a chord label (``"N"`` for no chord)."""
    text = str(chord).strip()
    if not text or text.upper() in ("N", "NONE", "NO_CHORD"):
        return "N"
    return text.split(":", 1)[0]


def chord_root_accuracy(
    reference: Sequence[GTChord],
    estimate: Sequence[GTChord],
    *,
    hop: float = DEFAULT_CHORD_HOP_S,
) -> dict[str, object]:
    """Duration-weighted **root** accuracy (pitch class, quality ignored).

    This is the W3 G3 metric. It uses the same frame sampling as
    :func:`chord_frame_accuracy` but compares only the root, so extended
    qualities do not mask a correct root.
    """
    if not reference or not estimate:
        return {
            "root_accuracy": 0.0 if reference else None,
            "frames": 0,
            "reference_events": len(reference),
            "estimated_events": len(estimate),
        }

    start = min(min(c.start for c in reference), min(c.start for c in estimate))
    end = max(max(c.end for c in reference), max(c.end for c in estimate))
    if end <= start:
        return {
            "root_accuracy": 0.0,
            "frames": 0,
            "reference_events": len(reference),
            "estimated_events": len(estimate),
        }

    correct = 0
    total = 0
    frame = start + hop / 2.0
    while frame < end:
        ref_chord = _chord_at(reference, frame)
        est_chord = _chord_at(estimate, frame)
        if ref_chord is not None and est_chord is not None:
            total += 1
            if chord_root(ref_chord.chord) == chord_root(est_chord.chord):
                correct += 1
        frame += hop

    return {
        "root_accuracy": round(correct / total, 6) if total else None,
        "frames": total,
        "reference_events": len(reference),
        "estimated_events": len(estimate),
    }


def chord_event_prf(
    reference: Sequence[GTChord],
    estimate: Sequence[GTChord],
    *,
    min_overlap_ratio: float = 0.5,
) -> PRF:
    """Interval-level chord P/R/F1.

    A predicted chord is a true positive when it overlaps a reference
    chord with the same MIREX label by at least ``min_overlap_ratio`` of
    the reference duration. Matching is one-to-one, greedy by overlap.
    """
    used_reference: set[int] = set()
    tp = 0

    for est in sorted(estimate, key=lambda c: (c.start, c.end)):
        best_ref: int | None = None
        best_overlap = 0.0
        for ref_idx, ref in enumerate(reference):
            if ref_idx in used_reference:
                continue
            if _mirex_index(ref.chord) != _mirex_index(est.chord):
                continue
            overlap = min(ref.end, est.end) - max(ref.start, est.start)
            if overlap <= 0.0:
                continue
            ratio = overlap / max(ref.end - ref.start, 1e-9)
            if ratio >= min_overlap_ratio and overlap > best_overlap:
                best_overlap = overlap
                best_ref = ref_idx
        if best_ref is not None:
            used_reference.add(best_ref)
            tp += 1

    return _prf(tp, len(estimate) - tp, len(reference) - tp)


def calibration_samples(
    reference: Sequence[GTChord],
    estimate: Sequence[GTChord],
    *,
    audio_duration: float | None = None,
) -> list[tuple[float, float, float]]:
    """Build ``(confidence, correct, weight_seconds)`` samples for ECE.

    Matches :func:`app.scripts.measure_confidence_ece._build_samples`.
    """
    if not estimate:
        return []

    intervals = [
        (c.start, c.end, _mirex_index(c.chord))
        for c in reference
    ]
    samples: list[tuple[float, float, float]] = []

    for index, event in enumerate(estimate):
        start = float(event.start)
        if index + 1 < len(estimate):
            end = float(estimate[index + 1].start)
        else:
            end = (
                min(audio_duration, start + 1.0)
                if audio_duration is not None and audio_duration > start
                else start + 1.0
            )
        if end <= start:
            continue
        gt_index, overlap = majority_gt_index(intervals, start, end)
        if overlap <= 0.0:
            continue
        confidence = max(0.0, min(1.0, float(event.confidence or 0.0)))
        correct = 1.0 if _mirex_index(event.chord) == gt_index else 0.0
        samples.append((confidence, correct, end - start))
    return samples


def calibration_metrics(
    reference: Sequence[GTChord],
    estimate: Sequence[GTChord],
    *,
    bins: int = 10,
    audio_duration: float | None = None,
) -> dict[str, object]:
    """Compute ECE and the reliability bins for chord confidences."""
    samples = calibration_samples(
        reference, estimate, audio_duration=audio_duration
    )
    if not samples:
        return {
            "ece": None,
            "samples": 0,
            "total_weight_s": 0.0,
            "bins": [],
        }

    confidences = [sample[0] for sample in samples]
    correct = [sample[1] for sample in samples]
    weights = [sample[2] for sample in samples]
    total_weight = float(sum(weights))
    calibration_bins: list[CalibrationBin] = bin_calibration(
        confidences, correct, weights, num_bins=bins
    )
    ece = expected_calibration_error(
        calibration_bins, total_weight=total_weight
    )
    return {
        "ece": round(ece, 6),
        "samples": len(samples),
        "total_weight_s": round(total_weight, 6),
        "bins": [
            {
                "lower": round(item.lower, 6),
                "upper": round(item.upper, 6),
                "count": item.count,
                "weight": round(item.weight, 6),
                "avg_confidence": round(item.avg_confidence, 6),
                "accuracy": round(item.accuracy, 6),
                "gap": round(item.gap, 6),
            }
            for item in calibration_bins
        ],
    }
