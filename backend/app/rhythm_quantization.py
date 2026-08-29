"""Solo rhythm quantization & measure-level sanity (Commit 106).

Solo note durations arrive grid-snapped in seconds but carry no notation
semantics.  This module converts them into exact MusicXML rhythm values:

- wall-clock seconds → quarter-length fractions on the beat tick grid
  (``quantize_seconds_to_ql``)
- a quarter-length fraction → a standard note type, possibly dotted or a
  tuplet (3-in-2, 5-in-4, 6-in-4, 6-in-2), with exact fraction arithmetic
  (``quantize_to_note_type``)
- notes spanning a barline are split into per-measure segments that render
  as tied continuations (``split_note_into_measures``)

Everything here is pure and deterministic (no music21 dependency) so the
rhythm rules are unit-testable in isolation; ``musicxml_builder.py`` applies
the results when constructing the score.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from fractions import Fraction
from typing import Sequence

# Standard note types as fractions of a quarter note (quarterLength units).
STANDARD_TYPES: list[tuple[Fraction, str]] = [
    (Fraction(1, 16), "64th"),
    (Fraction(1, 8), "32nd"),
    (Fraction(1, 4), "16th"),
    (Fraction(1, 2), "eighth"),
    (Fraction(1, 1), "quarter"),
    (Fraction(2, 1), "half"),
    (Fraction(4, 1), "whole"),
]

# Tuplet shapes "n notes in the time of k" (e.g. 3-in-2 = triplet).
TUPLET_SHAPES: list[tuple[int, int]] = [(3, 2), (5, 4), (6, 4), (6, 2)]


@dataclass(frozen=True)
class QuantizedDuration:
    """A rhythm-valid duration for MusicXML emission.

    ``type``/``dots`` mirror music21 duration nomenclature; ``tuplet`` is
    ``(actual, normal)`` (e.g. ``(3, 2)`` = triplet); ``quarter_length`` is
    the exact quarter-length that the combination produces; ``base_type`` is
    the undotted non-tuplet type the tuplet is derived from (for building
    the music21 ``<time-modification>`` normal/actual elements).
    """

    type: str
    dots: int
    tuplet: tuple[int, int] | None
    quarter_length: Fraction
    base_type: str


def tick_to_quarter_fraction(tick_value: float) -> Fraction:
    """Convert a float beat-grid ``tick_value`` to an exact Fraction.

    ``tick_value`` is the fraction of a (quarter) beat represented by one
    grid tick (e.g. 0.25 → 1/4).  Converting via the decimal string keeps
    common binary floats exact (0.125, 0.25, 0.5); pathological floats fall
    back to a bounded rational approximation.
    """
    try:
        return Fraction(str(tick_value))
    except (ValueError, ZeroDivisionError):
        return Fraction(tick_value).limit_denominator(96)


def quantize_seconds_to_ql(
    seconds_s: float,
    quarter_note_duration_s: float,
    tick_ql: Fraction,
) -> Fraction:
    """Round wall-clock seconds to the nearest representable grid tick.

    ``quarter_note_duration_s`` is the length of one quarter note (60/bpm)
    and ``tick_ql`` the tick size in quarter lengths (from
    ``tick_to_quarter_fraction``).  This is the variable-resolution
    replacement for the hardcoded 1/8-note rounding in the MusicXML builder:
    the resolution tracks the beat grid instead of a fixed 8th-note grid.

    Tuplet positions are part of the grid: a duration of 1/3 quarter (a
    triplet eighth) cannot land on a plain 16th tick, so ``2/3``-of-tick
    (3-in-2), ``4/5`` (5-in-4) and ``2/3``-family (6-in-4, 6-in-2) offsets
    are also candidates and the nearest overall wins.  Plain ticks still
    win whenever the duration is plain-grid-aligned.
    """
    if quarter_note_duration_s <= 0 or tick_ql <= 0:
        return Fraction(0)
    seconds_per_quarter = Fraction(quarter_note_duration_s)
    target_ql = Fraction(seconds_s) / seconds_per_quarter
    candidates: list[Fraction] = [tick_ql * round(target_ql / tick_ql)]
    for actual, normal in TUPLET_SHAPES:
        tup_tick = tick_ql * Fraction(normal, actual)
        candidates.append(tup_tick * round(target_ql / tup_tick))
    return min(candidates, key=lambda c: abs(c - target_ql))


def _candidate_durations() -> list[QuantizedDuration]:
    """Every plain/dotted/tuplet combination a note can be quantized to."""
    out: list[QuantizedDuration] = []
    for ql, name in STANDARD_TYPES:
        out.append(QuantizedDuration(name, 0, None, ql, name))
        for dots in (1, 2):
            # Dotted multiplier: 3/2 single, 7/4 double (1 + 1/2 + 1/4)
            dotted_ql = ql * Fraction(2 ** (dots + 1) - 1, 2**dots)
            out.append(QuantizedDuration(name, dots, None, dotted_ql, name))
        for actual, normal in TUPLET_SHAPES:
            tup_ql = ql * Fraction(normal, actual)
            out.append(
                QuantizedDuration(name, 0, (actual, normal), tup_ql, name)
            )
    return out


_CANDIDATES = _candidate_durations()


def quantize_to_note_type(
    quarter_length: Fraction,
    *,
    tolerance_ql: Fraction | None = None,
) -> QuantizedDuration | None:
    """Map a quarter-length duration to the nearest valid rhythm.

    Candidates are all standard types (whole → 64th), their dotted variants,
    and the tuplet shapes (3-in-2, 5-in-4, 6-in-4, 6-in-2).  The nearest
    candidate by absolute quarter-length error wins; among equal-error
    candidates the simpler rhythm wins (fewer dots, then smaller tuplet
    numerator).  Without ``tolerance_ql`` an exact match is required.

    Returns None for non-positive or unmatchable durations.
    """
    if quarter_length is None or quarter_length <= 0:
        return None
    best: QuantizedDuration | None = None
    best_error: Fraction | None = None
    for cand in _CANDIDATES:
        error = abs(cand.quarter_length - quarter_length)
        if best_error is not None and error > best_error:
            continue
        if error == best_error and best is not None:
            if cand.dots > best.dots:
                continue
            if cand.dots == best.dots:
                cand_tup = cand.tuplet or (1 << 20, 1)
                best_tup = best.tuplet or (1 << 20, 1)
                if cand_tup[0] > best_tup[0]:
                    continue
        best = cand
        best_error = error
    if best_error is None or best is None:
        return None
    tolerance = tolerance_ql if tolerance_ql is not None else Fraction(0)
    if best_error > tolerance:
        return None
    return best


def decompose_rest_durations(
    quarter_length: Fraction,
    *,
    max_pieces: int = 8,
) -> list[QuantizedDuration]:
    """Split a rest duration into exact, notation-valid pieces.

    Rests cannot ride the nearest-rhythm tolerance the way notes can: a
    gap rest must land exactly on the next note attack and the
    measure-final rest must fill the measure exactly.  Tolerance-driven
    quantization can otherwise turn a 13/4 ql final rest into a 16/5 ql
    5-in-4 whole-tuplet rest, under-filling the measure and corrupting
    every subsequent element offset (Commit 107).

    Returns the shortest exact combination of candidate durations
    (plain/dotted types plus tuplet shapes) that sums to
    ``quarter_length``.  Falls back to a single raw piece (``type=""``)
    when no exact combination exists within ``max_pieces``.
    """
    if quarter_length is None or quarter_length <= 0:
        return []
    target = Fraction(quarter_length)

    candidates = [c for c in _CANDIDATES if c.quarter_length <= target]
    candidates.sort(key=lambda c: c.quarter_length, reverse=True)

    def _solve(
        remaining: Fraction,
        depth: int,
        seen: set[Fraction],
    ) -> list[QuantizedDuration] | None:
        if remaining == 0:
            return []
        if depth >= max_pieces:
            return None
        if remaining in seen:
            return None
        seen.add(remaining)
        for cand in candidates:
            if cand.quarter_length > remaining:
                continue
            rest = _solve(remaining - cand.quarter_length, depth + 1, seen)
            if rest is not None:
                return [cand] + rest
        return None

    pieces = _solve(target, 0, set())
    if pieces is not None:
        return pieces
    # No exact rhythm-valid combination exists (pathological fraction):
    # Greedy fallback: split into nearest valid pieces until remainder is
    # expressible, ensuring we never emit an inexpressible raw type that
    # would crash music21 (measure 10 regression).
    out: list[QuantizedDuration] = []
    remaining = target
    for _ in range(max_pieces):
        if remaining <= 0:
            break
        # Pick largest candidate <= remaining, or nearest if none
        cand = next((c for c in candidates if c.quarter_length <= remaining), None)
        if cand is None:
            cand = min(_CANDIDATES, key=lambda c: abs(c.quarter_length - remaining))
            # Clamp to remaining to avoid overshoot
            if cand.quarter_length > remaining:
                # Use the smallest valid duration and let the leftover be handled
                cand = min(_CANDIDATES, key=lambda c: c.quarter_length)
        out.append(cand)
        remaining -= cand.quarter_length
        if remaining == 0:
            break
        # Re-filter candidates for new remaining
        candidates = [c for c in _CANDIDATES if c.quarter_length <= remaining]
        if not candidates:
            candidates = _CANDIDATES
    if remaining != 0:
        # Last resort: add the remainder as a single quantized piece with large tolerance
        fallback = quantize_to_note_type(remaining, tolerance_ql=Fraction(1, 1))
        if fallback is not None:
            out.append(fallback)
        else:
            out.append(QuantizedDuration("quarter", 0, None, remaining, "quarter"))
    return out


def nearest_grid_index(time_s: float, grid: Sequence[float]) -> int:
    """Index of the nearest grid entry (closest tick for a wall-clock time)."""
    if not grid:
        return 0
    idx = bisect_left(grid, time_s)
    if idx == 0:
        return 0
    if idx == len(grid):
        return len(grid) - 1
    before = grid[idx - 1]
    after = grid[idx]
    if abs(time_s - before) <= abs(time_s - after):
        return idx - 1
    return idx


def split_note_into_measures(
    start_ql: Fraction,
    duration_ql: Fraction,
    measure_length_ql: Fraction,
) -> list[tuple[Fraction, Fraction]]:
    """Split a note across measure boundaries.

    Returns a list of ``(start_within_measure, duration_in_measure)``
    segments in quarter lengths.  A note fully inside one measure yields a
    single segment; a note spanning a barline yields one segment per measure,
    which the caller renders as tied segments.  Exact integer-free Fraction
    arithmetic — no float rounding.
    """
    if measure_length_ql <= 0 or duration_ql <= 0:
        return []
    segments: list[tuple[Fraction, Fraction]] = []
    cursor = start_ql
    remaining = duration_ql
    while remaining > 0:
        bar_index = int(
            (cursor.numerator * measure_length_ql.denominator)
            // (cursor.denominator * measure_length_ql.numerator)
        )
        bar_start = bar_index * measure_length_ql
        bar_end = bar_start + measure_length_ql
        seg_start = cursor - bar_start
        seg_dur = min(remaining, bar_end - cursor)
        segments.append((seg_start, seg_dur))
        cursor += seg_dur
        remaining -= seg_dur
    return segments