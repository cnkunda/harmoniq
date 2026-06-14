"""Chord quality metrics for Viterbi-decoded chord timelines (Commit 99).

Computes flicker rate, beat-alignment percentage, chord-change histograms,
and duration-filtering statistics for analysis quality reporting.
"""

from __future__ import annotations

import logging

import numpy as np

from app.schemas import BeatGrid, ChordEvent

logger = logging.getLogger("harmoniq.inference.metrics")


def compute_flicker_rate(events: list[ChordEvent]) -> float:
    """Compute the rate of isolated single-beat chord changes (flicker).

    Flicker = a chord that differs from both its predecessor and successor.
    Excludes 'N' (no-chord) events from flicker counting.

    Returns:
        Float in [0, 1]. Target: < 0.05.
    """
    if len(events) < 3:
        return 0.0

    flicker_count = 0
    for i in range(1, len(events) - 1):
        curr = events[i].chord
        if curr == "N":
            continue
        if curr != events[i - 1].chord and curr != events[i + 1].chord:
            flicker_count += 1

    non_n_count = len(events) - 2
    return flicker_count / max(non_n_count, 1)


def compute_beat_alignment(
    events: list[ChordEvent],
    beat_grid: BeatGrid,
    measure: str = "any",
    tolerance_sec: float = 0.05,
) -> float:
    """Compute the percentage of chord changes aligned with beat boundaries.

    Args:
        events: Chord timeline events.
        beat_grid: The beat grid used for pooling.
        measure: "any" for any beat, "downbeat" for downbeats only.
        tolerance_sec: Timestamp tolerance for alignment matching.

    Returns:
        Float in [0, 1]. Target: > 0.90 for "any", > 0.60 for "downbeat".
    """
    if measure == "downbeat":
        boundary_set = set(round(db, 3) for db in beat_grid.downbeats)
    else:
        boundary_set = set(round(b, 3) for b in beat_grid.beats)

    if not boundary_set:
        return 1.0  # no beats to check against

    chord_changes = 0
    aligned_changes = 0

    for i in range(1, len(events)):
        if events[i].chord != events[i - 1].chord:
            chord_changes += 1
            ts = round(events[i].timestamp, 3)
            if any(abs(ts - b) < tolerance_sec for b in boundary_set):
                aligned_changes += 1

    if chord_changes == 0:
        return 1.0  # no changes means perfect alignment

    return aligned_changes / chord_changes


def compute_chord_change_histogram(
    events: list[ChordEvent],
    beat_grid: BeatGrid,
) -> dict:
    """Build a histogram of inter-chord-change intervals in beat units.

    Bins:
        "<0.5": sub-beat flicker
        "0.5-1": half-beat changes
        "1-2":   typical fast changes
        "2-4":   common pop/rock duration
        "4+":    sustained chords

    Returns:
        Dict with bins, counts, total_changes, flicker_pct, median_duration_beats.
    """
    beat_duration = 60.0 / beat_grid.bpm if beat_grid.bpm > 0 else 0.5

    change_indices = [
        i for i in range(1, len(events)) if events[i].chord != events[i - 1].chord
    ]

    if len(change_indices) < 2:
        return {
            "bins": ["<0.5", "0.5-1", "1-2", "2-4", "4+"],
            "counts": [0, 0, 0, 0, 0],
            "total_changes": len(change_indices),
            "flicker_pct": 0.0,
            "median_duration_beats": 0.0,
        }

    intervals_beats = []
    for i in range(1, len(change_indices)):
        dt = events[change_indices[i]].timestamp - events[change_indices[i - 1]].timestamp
        intervals_beats.append(dt / beat_duration)

    bins = ["<0.5", "0.5-1", "1-2", "2-4", "4+"]
    bin_edges = [0, 0.5, 1, 2, 4, float("inf")]
    counts = [0] * 5

    for interval in intervals_beats:
        for b_idx in range(len(bin_edges) - 1):
            if bin_edges[b_idx] <= interval < bin_edges[b_idx + 1]:
                counts[b_idx] += 1
                break

    total = len(change_indices)
    return {
        "bins": bins,
        "counts": counts,
        "total_changes": total,
        "flicker_pct": round(counts[0] / max(total, 1) * 100, 1),
        "median_duration_beats": round(
            float(np.median(intervals_beats)), 2
        ) if intervals_beats else 0.0,
    }


def compute_duration_filtering_stats(
    events: list[ChordEvent],
    beat_grid: BeatGrid,
) -> dict:
    """Identify sub-beat chord events that may be spurious.

    Returns:
        Dict with sub_beat_count, total_chord_events, sub_beat_ratio,
        and up to 10 example sub-beat events.
    """
    beat_duration = 60.0 / beat_grid.bpm if beat_grid.bpm > 0 else 0.5

    sub_beat_events = []
    for i in range(len(events) - 1):
        dur = events[i + 1].timestamp - events[i].timestamp
        if dur < beat_duration and events[i].chord != "N":
            sub_beat_events.append({
                "chord": events[i].chord,
                "duration_beats": round(dur / beat_duration, 2),
                "confidence": events[i].confidence,
                "timestamp": events[i].timestamp,
            })

    total_chords = len([e for e in events if e.chord != "N"])

    return {
        "sub_beat_count": len(sub_beat_events),
        "total_chord_events": total_chords,
        "sub_beat_ratio": round(
            len(sub_beat_events) / max(total_chords, 1) * 100, 1
        ),
        "sub_beat_events": sub_beat_events[:10],
    }


def assemble_chord_metrics(
    events: list[ChordEvent],
    beat_grid: BeatGrid,
) -> dict:
    """Aggregate all chord quality metrics into a single metadata dict.

    Returns:
        Dict suitable for ChordTimeline.metadata field.
    """
    return {
        "flicker_rate": round(compute_flicker_rate(events), 4),
        "beat_alignment_pct": round(compute_beat_alignment(events, beat_grid, measure="any"), 4),
        "downbeat_alignment_pct": round(
            compute_beat_alignment(events, beat_grid, measure="downbeat"), 4
        ),
        "chord_change_histogram": compute_chord_change_histogram(events, beat_grid),
        "duration_filtering": compute_duration_filtering_stats(events, beat_grid),
        "total_events": len(events),
        "unique_chords": len(set(e.chord for e in events if e.chord != "N")),
    }
