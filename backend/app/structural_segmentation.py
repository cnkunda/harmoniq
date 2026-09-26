"""
Structural segmentation refinement (Commit 115).

Fuses three boundary signals — chord change density, Whisper word-cluster
(vocal phrase) gaps, and the existing librosa energy/onset novelty — into a
single boundary-likelihood curve, then labels the resulting sections with
music-structure heuristics (Intro / Verse / Chorus / Bridge / Outro).

Pure numpy functions: no librosa, no audio I/O, so the module is fully unit
testable. The energy novelty curve is produced upstream by
``pipeline_proof.librosa_summarize``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

# Fusion weights from PRIORITIES Commit 115 scope.
_W_CHORD = 0.4
_W_VOCAL = 0.3
_W_ENERGY = 0.3

# Refinement confidence floor: below this the caller falls back to the
# baseline (unlabeled) RMS boundaries.
MIN_REFINEMENT_CONFIDENCE = 0.6

# Boundary candidates must clear this fused-signal floor to be considered.
_BOUNDARY_THRESHOLD = 0.12


@dataclass
class SectionBoundary:
    """One refined structural section."""

    start_s: float
    end_s: float
    label: str
    label_confidence: float


def _event_field(ev: Any, name: str, default: Any = None) -> Any:
    """Read a field from either a pydantic model or a plain dict."""
    if isinstance(ev, dict):
        return ev.get(name, default)
    return getattr(ev, name, default)


def _extract_chord_events(chord_timeline: Any) -> list[Any]:
    """Normalize a ChordTimeline (model, dict, or list) into a list of events."""
    if chord_timeline is None:
        return []
    if isinstance(chord_timeline, dict):
        raw = chord_timeline.get("events") or []
    elif hasattr(chord_timeline, "events"):
        raw = chord_timeline.events
    else:
        raw = chord_timeline
    return list(raw or [])


def _extract_word_times(lyrics_aligned: Any) -> list[float]:
    """Extract sorted word start times from aligned lyric rows."""
    if not lyrics_aligned:
        return []
    times: list[float] = []
    for row in lyrics_aligned:
        if not isinstance(row, dict):
            continue
        t = row.get("time_seconds")
        if t is None:
            t = row.get("start_s")
        if t is None:
            continue
        try:
            times.append(float(t))
        except (TypeError, ValueError):
            continue
    times.sort()
    return times


def _norm(a: np.ndarray) -> np.ndarray:
    """Min-max normalize to [0, 1]; returns zeros for a flat/empty array."""
    a = np.asarray(a, dtype=float)
    if a.size == 0:
        return a
    mn = float(np.nanmin(a))
    mx = float(np.nanmax(a))
    if mx - mn < 1e-9:
        return np.zeros_like(a)
    return (a - mn) / (mx - mn)


def _median_dt(times: np.ndarray, default: float = 0.1) -> float:
    if times.size < 2:
        return default
    dt = np.diff(times)
    dt = dt[dt > 0]
    if dt.size == 0:
        return default
    return float(np.median(dt))


def chord_change_density(
    chord_timeline: Any,
    *,
    times: Sequence[float],
    window_s: float = 2.0,
) -> np.ndarray:
    """Chord-change density curve evaluated at ``times``.

    A chord change (impulse) is placed at every adjacent pair of events whose
    chord symbol differs (``"N"`` / no-chord events are ignored). The impulse
    train is smoothed by a triangular window of width ``window_s``, producing a
    density curve whose peaks mark regions of rapid harmonic movement.
    """
    times_np = np.asarray(times, dtype=float)
    if times_np.size == 0:
        return np.zeros(0, dtype=float)
    density = np.zeros_like(times_np)

    events = _extract_chord_events(chord_timeline)
    if len(events) < 2:
        return density

    changes: list[float] = []
    prev_chord: str | None = None
    for ev in events:
        chord = _event_field(ev, "chord")
        if not isinstance(chord, str) or chord in ("", "N"):
            # No-chord event: break the "previous chord" chain so the next real
            # chord reads as a fresh harmonic context (not a spurious change).
            prev_chord = None
            continue
        ts = _event_field(ev, "timestamp")
        if ts is None:
            continue
        if prev_chord is not None and chord != prev_chord:
            changes.append(float(ts))
        prev_chord = chord

    if not changes:
        return density

    # Place impulses on the nearest grid index.
    dt = _median_dt(times_np)
    half_width = max(1, int(round(window_s / 2.0 / dt)))
    impulse = np.zeros_like(times_np)
    idx = np.searchsorted(times_np, changes, side="left")
    idx = np.clip(idx, 0, times_np.size - 1)
    for i in idx:
        impulse[int(i)] += 1.0

    # Triangular smoothing kernel.
    kernel = np.arange(1, half_width + 1, dtype=float)
    kernel = np.concatenate([kernel, [half_width], kernel[::-1]])
    kernel = kernel / kernel.sum()
    smoothed = np.convolve(impulse, kernel, mode="same")
    return _norm(smoothed)


def vocal_gap_novelty(
    lyrics_aligned: Any,
    *,
    times: Sequence[float],
    gap_threshold_s: float = 1.5,
) -> np.ndarray:
    """Vocal phrase-gap curve evaluated at ``times``.

    Large gaps between consecutive word timestamps (silence between vocal
    phrases) suggest a section boundary. Each such gap places an impulse at its
    midpoint with magnitude proportional to the gap length.
    """
    times_np = np.asarray(times, dtype=float)
    if times_np.size == 0:
        return np.zeros(0, dtype=float)
    novelty = np.zeros_like(times_np)

    words = _extract_word_times(lyrics_aligned)
    if len(words) < 2:
        return novelty

    gaps: list[tuple[float, float]] = []
    for i in range(1, len(words)):
        gap = words[i] - words[i - 1]
        if gap >= gap_threshold_s:
            gaps.append((words[i - 1] + gap / 2.0, gap))
    if not gaps:
        return novelty

    max_gap = max(g for _, g in gaps)
    impulse = np.zeros_like(times_np)
    for mid, gap in gaps:
        i = int(np.searchsorted(times_np, mid, side="left"))
        i = int(np.clip(i, 0, times_np.size - 1))
        impulse[i] = max(impulse[i], gap / max_gap)

    dt = _median_dt(times_np)
    half_width = max(1, int(round((gap_threshold_s / 2.0) / dt)))
    kernel = np.arange(1, half_width + 1, dtype=float)
    kernel = np.concatenate([kernel, [half_width], kernel[::-1]])
    kernel = kernel / kernel.sum()
    smoothed = np.convolve(impulse, kernel, mode="same")
    return _norm(smoothed)


def fuse_boundary_signals(
    chord: np.ndarray,
    vocal: np.ndarray,
    energy: np.ndarray,
) -> np.ndarray:
    """Weighted average of the three normalized boundary signals."""
    length = max(chord.size, vocal.size, energy.size)
    c = _resize(chord, length)
    v = _resize(vocal, length)
    e = _resize(energy, length)
    return _W_CHORD * c + _W_VOCAL * v + _W_ENERGY * e


def _resize(a: np.ndarray, length: int) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    if a.size == length:
        return a
    if a.size == 0:
        return np.zeros(length, dtype=float)
    # Linear resample to the target length (uniform time grid assumption).
    x = np.linspace(0.0, 1.0, num=a.size)
    xp = np.linspace(0.0, 1.0, num=length)
    return np.interp(xp, x, a)


def detect_boundaries(
    fused: np.ndarray,
    times: Sequence[float],
    *,
    n_boundaries: int,
    min_gap_s: float,
) -> tuple[list[float], float]:
    """Peak-pick the top ``n_boundaries`` fused-signal maxima.

    Returns (boundary_times, refinement_confidence). Confidence reflects both
    *detection completeness* (how many of the expected boundaries were found)
    and *relative strength* (how clearly the chosen peaks stand out against the
    strongest peak in the whole curve), so a boundary driven by a single signal
    (e.g. energy novelty alone) still scores high when it is a distinct, obvious
    peak. Confidence is 0.0 when no candidates are found.
    """
    fused = np.asarray(fused, dtype=float)
    times_np = np.asarray(times, dtype=float)
    if n_boundaries <= 0 or fused.size < 3 or times_np.size != fused.size:
        return [], 0.0

    # Local maxima above the threshold.
    peaks: list[tuple[float, float]] = []
    for i in range(1, fused.size - 1):
        v = fused[i]
        if v < _BOUNDARY_THRESHOLD:
            continue
        if v >= fused[i - 1] and v >= fused[i + 1]:
            peaks.append((float(times_np[i]), float(v)))

    if not peaks:
        return [], 0.0

    # Sort by magnitude descending; greedily keep candidates respecting min gap.
    peaks.sort(key=lambda p: p[1], reverse=True)
    chosen: list[tuple[float, float]] = []
    for t, v in peaks:
        if any(abs(t - c[0]) < min_gap_s for c in chosen):
            continue
        chosen.append((t, v))
        if len(chosen) >= n_boundaries:
            break

    chosen.sort(key=lambda p: p[0])
    if not chosen:
        return [], 0.0
    max_v = float(np.max(fused)) if fused.size else 0.0
    if max_v <= 1e-9:
        return [t for t, _ in chosen], 0.0
    relative = float(np.mean([v / max_v for _, v in chosen]))
    completeness = min(1.0, len(chosen) / n_boundaries)
    confidence = min(1.0, max(0.0, relative * completeness))
    return [t for t, _ in chosen], confidence


def _section_energy(energy_novelty: np.ndarray, times: np.ndarray, start: float, end: float) -> float:
    if energy_novelty.size == 0 or times.size != energy_novelty.size:
        return 0.0
    mask = (times >= start) & (times < end)
    if not np.any(mask):
        return 0.0
    return float(np.mean(energy_novelty[mask]))


def _section_fingerprint(chord_timeline: Any, start: float, end: float) -> tuple[str, ...]:
    """Collapse a section's chords into a (root:quality) progression tuple."""
    events = _extract_chord_events(chord_timeline)
    prog: list[str] = []
    for ev in events:
        ts = _event_field(ev, "timestamp")
        if ts is None or not (start <= float(ts) < end):
            continue
        chord = _event_field(ev, "chord")
        if not isinstance(chord, str) or chord in ("", "N"):
            continue
        if not prog or prog[-1] != chord:
            prog.append(chord)
    return tuple(prog)


def infer_section_labels(
    boundary_times: Sequence[float],
    *,
    duration_s: float,
    chord_timeline: Any,
    energy_curve: Sequence[float] | None = None,
    energy_times: Sequence[float] | None = None,
) -> list[SectionBoundary]:
    """Label refined sections using repetition + energy + position heuristics."""
    bounds = sorted(float(t) for t in boundary_times)
    if len(bounds) < 2:
        return []

    energy_np = np.asarray(energy_curve if energy_curve is not None else [], dtype=float)
    times_np = np.asarray(energy_times if energy_times is not None else [], dtype=float)

    sections: list[SectionBoundary] = []
    fingerprints: list[tuple[str, ...]] = []
    energies: list[float] = []
    for i in range(len(bounds) - 1):
        start = bounds[i]
        end = bounds[i + 1]
        if end - start < 0.2:
            continue
        fingerprints.append(_section_fingerprint(chord_timeline, start, end))
        energies.append(_section_energy(energy_np, times_np, start, end))
        sections.append(SectionBoundary(start_s=start, end_s=end, label="", label_confidence=0.0))

    if not sections:
        return []

    # Repetition analysis: a fingerprint appearing >= 2 times is "repeated".
    counts: dict[tuple[str, ...], int] = {}
    for fp in fingerprints:
        if fp:
            counts[fp] = counts.get(fp, 0) + 1
    repeated = {fp for fp, n in counts.items() if n >= 2}

    # Chorus = the repeated fingerprint whose sections carry the highest energy.
    chorus_fp: tuple[str, ...] | None = None
    if repeated:
        best_energy = -1.0
        for fp in repeated:
            fp_energy = max(
                (energies[i] for i, f in enumerate(fingerprints) if f == fp),
                default=-1.0,
            )
            if fp_energy > best_energy:
                best_energy = fp_energy
                chorus_fp = fp

    n = len(sections)
    labels: list[str] = []
    confidences: list[float] = []
    for i, fp in enumerate(fingerprints):
        label = ""
        conf = 0.5
        is_first = i == 0
        is_last = i == n - 1

        if fp and fp in repeated:
            if chorus_fp is not None and fp == chorus_fp:
                label = "Chorus"
                conf = 0.85
            else:
                label = "Verse"
                conf = 0.8
        elif is_first and (bounds[1] - bounds[0]) < 15.0:
            label = "Intro"
            conf = 0.7
        elif is_last and i >= 1 and energies[i] < energies[i - 1] * 0.85:
            label = "Outro"
            conf = 0.7
        elif not is_first and not is_last and fp and fp not in repeated:
            label = "Bridge"
            conf = 0.6

        labels.append(label)
        confidences.append(conf)

    # Fill remaining (unlabeled) sections with alternating Verse/Chorus.
    for i in range(n):
        if labels[i]:
            continue
        if i == 0:
            labels[i] = "Verse"
        elif i == n - 1:
            labels[i] = "Outro"
        else:
            labels[i] = "Verse" if (i % 2 == 0) else "Chorus"

    for sec, label, conf in zip(sections, labels, confidences):
        sec.label = label
        sec.label_confidence = conf

    return sections


def boundary_stability(
    refined_edges: Sequence[float],
    baseline_edges: Sequence[float],
    *,
    tol_s: float = 2.0,
) -> float:
    """Fraction of refined boundaries moved > ``tol_s`` from the nearest baseline edge.

    Returns 0.0 (stable) when every refined boundary sits within ``tol_s`` of a
    baseline boundary; 1.0 when none do. Used to assert "<50% of boundaries
    moved from the librosa baseline".
    """
    refined = sorted(float(t) for t in refined_edges)
    baseline = sorted(float(t) for t in baseline_edges)
    # Ignore the shared t=0 and duration endpoints.
    interior = [t for t in refined if t > 0.0 and (not baseline or t < max(baseline) - 1e-6)]
    if not interior:
        return 0.0
    moved = 0
    for t in interior:
        if not baseline:
            moved += 1
            continue
        nearest = min(abs(t - b) for b in baseline)
        if nearest > tol_s:
            moved += 1
    return float(moved / len(interior))


def refine_section_boundaries(
    *,
    baseline_segments: Sequence[dict[str, Any]],
    duration_s: float,
    chord_timeline: Any = None,
    lyrics_aligned: Any = None,
    energy_novelty: Sequence[float] | None = None,
    energy_times: Sequence[float] | None = None,
    energy_curve: Sequence[float] | None = None,
    min_gap_s: float | None = None,
) -> tuple[list[SectionBoundary], float]:
    """Fuse the three boundary signals, re-segment, and label sections.

    ``energy_novelty`` is the boundary-likelihood curve (librosa onset+energy
    novelty) fused with chord density and vocal gaps. ``energy_curve`` is the
    raw loudness (RMS) curve used for section label heuristics (e.g. chorus =
    repetition + high energy). Both share ``energy_times``.

    Returns ``(sections, refinement_confidence)``. When fewer than two baseline
    sections exist, or no signals are available, confidence is 0.0 and the
    caller should fall back to the baseline segmentation.
    """
    duration = max(0.0, float(duration_s))
    baseline = [s for s in baseline_segments if isinstance(s, dict)]
    n_segments = len(baseline)
    if n_segments < 2 or duration <= 0.0:
        return [], 0.0

    times_np = np.asarray(energy_times if energy_times is not None else [], dtype=float)
    if times_np.size == 0:
        # Uniform fallback grid over the duration.
        n_grid = max(64, int(duration * 10))
        times_np = np.linspace(0.0, duration, num=n_grid)

    energy_np = np.asarray(energy_novelty if energy_novelty is not None else [], dtype=float)
    if energy_np.size != times_np.size:
        energy_np = np.zeros_like(times_np)

    chord = chord_change_density(chord_timeline, times=times_np)
    vocal = vocal_gap_novelty(lyrics_aligned, times=times_np)
    energy = _norm(energy_np)

    fused = fuse_boundary_signals(chord, vocal, energy)

    n_boundaries = n_segments - 1
    gap = min_gap_s if min_gap_s is not None else max(2.0, duration / 12.0)

    boundary_times, confidence = detect_boundaries(
        fused, times_np, n_boundaries=n_boundaries, min_gap_s=gap
    )

    if not boundary_times:
        return [], 0.0

    edges = [0.0] + boundary_times + [duration]
    edges = sorted(set(round(float(t), 3) for t in edges if 0.0 <= t <= duration + 1e-6))
    if len(edges) < 2:
        return [], 0.0

    sections = infer_section_labels(
        edges,
        duration_s=duration,
        chord_timeline=chord_timeline,
        energy_curve=energy_curve if energy_curve is not None else energy_np,
        energy_times=times_np,
    )
    return sections, confidence
