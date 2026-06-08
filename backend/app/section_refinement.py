"""
Commit 117: Structural Segmentation Refinement.

Fuses three signals — chord change density, vocal gap detection, and energy
envelope novelty — to refine section boundaries beyond RMS-only detection.
Adds heuristic section label inference (Intro/Verse/Chorus/Bridge/Outro).
"""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

logger = logging.getLogger("harmoniq.section_refinement")
logger.setLevel(logging.INFO)

# ---- Tunable constants -------------------------------------------------------

CHORD_DENSITY_WINDOW_SEC: float = 4.0
VOCAL_MIN_GAP_SEC: float = 0.8
NOVELTY_GAUSSIAN_SIGMA_SEC: float = 1.0
FUSION_WEIGHTS: tuple[float, float, float] = (0.4, 0.3, 0.3)  # chord, vocal, energy
MIN_SECTION_SEC: float = 10.0
PEAK_HEIGHT_THRESHOLD: float = 0.35
PEAK_PROMINENCE: float = 0.08
CONFIDENCE_THRESHOLD: float = 0.6
CHORD_SIMILARITY_THRESHOLD: float = 0.6
MOVEMENT_TOLERANCE_SEC: float = 2.0
CHORD_NGRAM_SIZE: int = 3


# ---- Signal computation ------------------------------------------------------


def _compute_chord_density_curve(
    chord_events: list[tuple[float, str]],
    times: np.ndarray,
    window_sec: float = CHORD_DENSITY_WINDOW_SEC,
) -> np.ndarray:
    """Sliding-window chord change density → novelty curve on common time grid.

    Returns a normalized [0, 1] array aligned to *times*.  The novelty of the
    density curve (first difference) is used so that boundaries correspond to
    *transitions* in chord activity rather than raw density peaks.
    """
    if len(times) < 2 or not chord_events:
        return np.zeros(len(times))

    hop = float(times[1] - times[0])
    density = np.zeros(len(times))

    # Sort chord events by timestamp for efficient windowing
    sorted_events = sorted(chord_events, key=lambda x: x[0])
    event_times = np.array([t for t, _ in sorted_events])
    event_labels = [c for _, c in sorted_events]

    for i, t in enumerate(times):
        lo = t - window_sec / 2.0
        hi = t + window_sec / 2.0
        # Binary search for window bounds
        left = int(np.searchsorted(event_times, lo, side="left"))
        right = int(np.searchsorted(event_times, hi, side="left"))
        window_chords = event_labels[left:right]
        # Count chord *changes* (not just events)
        changes = sum(
            1 for j in range(1, len(window_chords))
            if window_chords[j] != window_chords[j - 1]
        )
        density[i] = changes

    # Novelty of the density curve (captures transitions in chord activity)
    novelty = np.abs(np.gradient(density))

    # Gaussian smoothing
    sigma_frames = max(1, int(NOVELTY_GAUSSIAN_SIGMA_SEC / hop))
    from scipy.ndimage import gaussian_filter1d
    novelty = gaussian_filter1d(novelty, sigma_frames)

    mx = float(novelty.max())
    if mx > 1e-8:
        novelty = novelty / mx
    return novelty


def _compute_vocal_gap_curve(
    lyrics_aligned: list[dict[str, Any]],
    times: np.ndarray,
    min_gap_sec: float = VOCAL_MIN_GAP_SEC,
) -> np.ndarray:
    """Detect silences between vocal phrases from beat-snapped word timestamps.

    Returns a normalized [0, 1] array aligned to *times*.  Large gaps between
    consecutive words produce spikes weighted by gap duration.
    """
    if len(times) < 2 or len(lyrics_aligned) < 2:
        return np.zeros(len(times))

    signal = np.zeros(len(times))

    for i in range(1, len(lyrics_aligned)):
        prev_time = float(lyrics_aligned[i - 1].get("time_seconds", 0.0))
        curr_time = float(lyrics_aligned[i].get("time_seconds", 0.0))
        gap = curr_time - prev_time

        if gap < min_gap_sec:
            continue

        midpoint = (prev_time + curr_time) / 2.0
        idx = int(np.searchsorted(times, midpoint))
        idx = min(idx, len(times) - 1)
        # Weight by gap duration (longer gap = stronger signal)
        signal[idx] += gap

    # Gaussian smoothing
    hop = float(times[1] - times[0])
    sigma_frames = max(1, int(0.5 / hop))
    from scipy.ndimage import gaussian_filter1d
    signal = gaussian_filter1d(signal, sigma_frames)

    mx = float(signal.max())
    if mx > 1e-8:
        signal = signal / mx
    return signal


def _normalize_energy_signal(energy_novelty: np.ndarray) -> np.ndarray:
    """Normalize energy novelty to [0, 1] with p95 clipping to suppress outlier onsets."""
    if len(energy_novelty) == 0:
        return energy_novelty

    normalized = energy_novelty.copy().astype(float)
    p95 = float(np.percentile(normalized, 95))
    normalized = np.clip(normalized, 0.0, p95)
    mx = float(normalized.max())
    if mx > 1e-8:
        normalized = normalized / mx
    return normalized


def _fuse_signals(
    chord_sig: np.ndarray,
    vocal_sig: np.ndarray,
    energy_sig: np.ndarray,
    weights: tuple[float, float, float] = FUSION_WEIGHTS,
) -> np.ndarray:
    """Weighted average of three normalized signals."""
    assert abs(sum(weights) - 1.0) < 1e-6, f"Weights must sum to 1.0, got {sum(weights)}"
    return weights[0] * chord_sig + weights[1] * vocal_sig + weights[2] * energy_sig


# ---- Boundary detection ------------------------------------------------------


def _detect_boundary_peaks(
    fused: np.ndarray,
    times: np.ndarray,
    min_section_sec: float = MIN_SECTION_SEC,
    height_threshold: float = PEAK_HEIGHT_THRESHOLD,
    prominence: float = PEAK_PROMINENCE,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Peak detection on the fused novelty curve using scipy.signal.find_peaks."""
    from scipy.signal import find_peaks

    hop = float(times[1] - times[0])
    min_distance_frames = max(1, int(min_section_sec / hop))

    peaks, props = find_peaks(
        fused,
        distance=min_distance_frames,
        height=height_threshold,
        prominence=prominence,
    )
    return peaks, props  # type: ignore[return-value]


def _compute_movement_ratio(
    new_boundaries: list[float],
    rms_boundaries: list[float],
    tolerance_sec: float = MOVEMENT_TOLERANCE_SEC,
) -> float:
    """Fraction of RMS boundaries with no corresponding refined boundary nearby.

    Intentionally asymmetric: we care whether the refinement *abandoned* an
    existing boundary, not whether it added new ones.
    """
    if not rms_boundaries:
        return 0.0

    moved = 0
    for rms_t in rms_boundaries:
        has_match = any(
            abs(new_t - rms_t) <= tolerance_sec for new_t in new_boundaries
        )
        if not has_match:
            moved += 1

    return moved / len(rms_boundaries)


def _compute_boundary_confidence(
    idx: int,
    chord_sig: np.ndarray,
    vocal_sig: np.ndarray,
    energy_sig: np.ndarray,
    times: np.ndarray,
    agreement_window_sec: float = 2.0,
) -> float:
    """Per-boundary confidence based on agreement of all three signals.

    Blends geometric mean (punishes missing signals) with arithmetic mean
    (lenient for instrumental tracks where vocal signal is structurally weak).
    """
    hop = float(times[1] - times[0])
    half_w = max(1, int(agreement_window_sec / 2.0 / hop))

    lo = max(0, idx - half_w)
    hi = min(len(times), idx + half_w + 1)

    c = float(chord_sig[lo:hi].max())
    v = float(vocal_sig[lo:hi].max())
    e = float(energy_sig[lo:hi].max())

    # Geometric mean — any signal near-zero tanks the score
    geo_mean = (c * v * e) ** (1.0 / 3.0) if (c > 0 and v > 0 and e > 0) else 0.0

    # Arithmetic mean — more lenient
    arith_mean = (c + v + e) / 3.0

    # Blend: weight geo_mean more when vocal signal is non-trivial
    vocal_weight = min(1.0, v * 3.0)  # 0 for instrumental, 1 for vocal
    confidence = vocal_weight * geo_mean + (1.0 - vocal_weight) * arith_mean

    return float(np.clip(confidence, 0.0, 1.0))


# ---- Section labeling --------------------------------------------------------


def _fingerprint_section(
    chord_events: list[tuple[float, str]],
    start_t: float,
    end_t: float,
    n_gram: int = CHORD_NGRAM_SIZE,
) -> frozenset[tuple[str, ...]]:
    """Build chord n-gram fingerprint for a section (used for similarity comparison)."""
    section_chords = [c for t, c in chord_events if start_t <= t < end_t]
    # Collapse runs (Am Am Am → Am)
    deduped = [
        c for i, c in enumerate(section_chords)
        if i == 0 or c != section_chords[i - 1]
    ]
    if len(deduped) < n_gram:
        return frozenset([tuple(deduped)]) if deduped else frozenset()
    return frozenset(
        tuple(deduped[i:i + n_gram]) for i in range(len(deduped) - n_gram + 1)
    )


def _jaccard(fp1: frozenset[tuple[str, ...]], fp2: frozenset[tuple[str, ...]]) -> float:
    """Jaccard similarity between two chord fingerprint sets."""
    if not fp1 or not fp2:
        return 0.0
    return len(fp1 & fp2) / len(fp1 | fp2)


def _greedy_group(
    n: int,
    sim_matrix: np.ndarray,
    threshold: float = CHORD_SIMILARITY_THRESHOLD,
) -> list[list[int]]:
    """Greedy grouping of sections by similarity (no sklearn dependency).

    Returns list of groups, each group is a list of section indices.
    """
    assigned = [False] * n
    groups: list[list[int]] = []

    for i in range(n):
        if assigned[i]:
            continue
        group = [i]
        assigned[i] = True
        for j in range(i + 1, n):
            if assigned[j]:
                continue
            if sim_matrix[i][j] >= threshold:
                group.append(j)
                assigned[j] = True
        groups.append(group)

    return groups


def _mean_section_energy(
    rms_curve: np.ndarray, times: np.ndarray, start_t: float, end_t: float
) -> float:
    """Mean RMS energy within a section's time range."""
    mask = (times >= start_t) & (times < end_t)
    if not mask.any():
        return 0.0
    return float(rms_curve[mask].mean())


def _is_energy_declining(
    rms_curve: np.ndarray,
    times: np.ndarray,
    start_t: float,
    end_t: float,
    window_sec: float = 10.0,
) -> bool:
    """True if the last *window_sec* of this section trend downward."""
    mask = (times >= max(start_t, end_t - window_sec)) & (times < end_t)
    if mask.sum() < 4:
        return False
    slope = np.polyfit(times[mask], rms_curve[mask], 1)[0]
    return slope < 0


def _infer_section_labels(
    boundary_times: list[float],
    song_duration: float,
    chord_events: list[tuple[float, str]],
    rms_curve: np.ndarray,
    times: np.ndarray,
) -> list[dict[str, Any]]:
    """Assign labels (Intro/Verse/Chorus/Bridge/Outro) via heuristic rules."""
    all_times = [0.0] + sorted(boundary_times) + [song_duration]
    sections: list[dict[str, Any]] = []

    for i in range(len(all_times) - 1):
        start, end = all_times[i], all_times[i + 1]
        sections.append({
            "start": start,
            "end": end,
            "duration": end - start,
            "fingerprint": _fingerprint_section(chord_events, start, end),
            "energy": _mean_section_energy(rms_curve, times, start, end),
            "label": None,
            "label_confidence": 0.0,
        })

    n = len(sections)
    if n == 0:
        return sections

    # Rule 1: Intro — first section if short and low energy
    start_idx = 0
    if sections[0]["duration"] < 15.0:
        sections[0]["label"] = "Intro"
        sections[0]["label_confidence"] = 0.8
        start_idx = 1

    # Rule 2: Outro — final section with declining energy
    end_idx = n
    if n > 1 and _is_energy_declining(rms_curve, times, sections[-1]["start"], sections[-1]["end"]):
        sections[-1]["label"] = "Outro"
        sections[-1]["label_confidence"] = 0.7
        end_idx = n - 1

    # Rule 3: Chord progression fingerprinting for interior sections
    interior = sections[start_idx:end_idx]
    if len(interior) >= 2:
        sim_matrix = np.zeros((len(interior), len(interior)))
        for i, si in enumerate(interior):
            for j, sj in enumerate(interior):
                sim_matrix[i][j] = _jaccard(si["fingerprint"], sj["fingerprint"])

        groups = _greedy_group(len(interior), sim_matrix)

        # Rule 4: Highest-energy repeated group → Chorus
        repeated_groups = [g for g in groups if len(g) > 1]
        chorus_group: list[int] | None = None
        if repeated_groups:
            chorus_group = max(
                repeated_groups,
                key=lambda g: np.mean([interior[i]["energy"] for i in g]),
            )
            for i in chorus_group:
                interior[i]["label"] = "Chorus"
                interior[i]["label_confidence"] = 0.75

        # Rule 5: Other repeated groups → Verse
        for group in repeated_groups:
            if group is not chorus_group:
                for i in group:
                    interior[i]["label"] = "Verse"
                    interior[i]["label_confidence"] = 0.7

        # Rule 6: Unique single-occurrence sections → Bridge
        unique_groups = [g for g in groups if len(g) == 1]
        for group in unique_groups:
            for i in group:
                if interior[i]["label"] is None:
                    interior[i]["label"] = "Bridge"
                    interior[i]["label_confidence"] = 0.6

    # Rule 7: Remaining unlabeled — alternate Verse/Chorus
    unlabeled = [s for s in sections if s["label"] is None]
    for k, s in enumerate(unlabeled):
        s["label"] = "Verse" if k % 2 == 0 else "Chorus"
        s["label_confidence"] = 0.5

    # Safety: ensure every section has a label
    for s in sections:
        if s["label"] is None:
            s["label"] = "Verse"
            s["label_confidence"] = 0.3

    return sections


def _estimate_label_confidence(section: dict[str, Any]) -> float:
    """Derive final label confidence from section metadata."""
    return float(np.clip(section.get("label_confidence", 0.5), 0.0, 1.0))


# ---- Public entry point ------------------------------------------------------


def refine_section_boundaries(
    rms_boundaries: list[float],
    chord_events: list[tuple[float, str]],
    lyrics_aligned: list[dict[str, Any]],
    onset_novelty: np.ndarray,
    rms_curve: np.ndarray,
    times: np.ndarray,
    song_duration: float,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> list[dict[str, Any]]:
    """Refine section boundaries by fusing chord density, vocal gaps, and energy.

    Returns a list of section dicts with keys:
        start, end, label, label_confidence, boundary_confidence

    Falls back to unlabeled RMS-derived boundaries when refinement confidence
    is low or when the refinement moves too many boundaries.
    """
    if len(times) < 2:
        logger.info("refine_section_boundaries: insufficient time frames, using RMS fallback")
        return _make_unlabeled_sections(rms_boundaries, song_duration)

    try:
        chord_sig = _compute_chord_density_curve(chord_events, times)
        vocal_sig = _compute_vocal_gap_curve(lyrics_aligned, times)
        energy_sig = _normalize_energy_signal(onset_novelty)

        fused = _fuse_signals(chord_sig, vocal_sig, energy_sig)

        peak_indices, _ = _detect_boundary_peaks(fused, times)
        boundary_times = times[peak_indices].tolist()

        # Stability gate: if refinement moved >50% of RMS boundaries, fall back
        movement_ratio = _compute_movement_ratio(boundary_times, rms_boundaries)
        if movement_ratio > 0.5:
            logger.warning(
                "refine_section_boundaries: moved %.1f%% of RMS boundaries (>50%%), "
                "falling back to RMS boundaries",
                movement_ratio * 100,
            )
            return _make_unlabeled_sections(rms_boundaries, song_duration)

        # Per-boundary confidence
        confidences = [
            _compute_boundary_confidence(idx, chord_sig, vocal_sig, energy_sig, times)
            for idx in peak_indices
        ]

        # Only keep high-confidence boundaries
        kept = [
            (t, c) for t, c in zip(boundary_times, confidences) if c >= confidence_threshold
        ]

        if not kept:
            logger.info(
                "refine_section_boundaries: no high-confidence boundaries found, "
                "falling back to RMS boundaries"
            )
            return _make_unlabeled_sections(rms_boundaries, song_duration)

        kept_times = [t for t, _ in kept]
        kept_confs = [c for _, c in kept]
        conf_map = dict(zip(kept_times, kept_confs))

        # Infer labels
        sections = _infer_section_labels(
            kept_times, song_duration, chord_events, rms_curve, times
        )

        # Attach boundary confidence to each section
        for s in sections:
            s["boundary_confidence"] = conf_map.get(s["start"], 1.0)
            # Final label_confidence blends label inference confidence with
            # boundary placement confidence
            s["label_confidence"] = _estimate_label_confidence(s) * s["boundary_confidence"]

        logger.info(
            "refine_section_boundaries: %d sections, labels=%s",
            len(sections),
            [s["label"] for s in sections],
        )
        return sections

    except Exception:
        logger.exception(
            "refine_section_boundaries failed — falling back to RMS boundaries"
        )
        return _make_unlabeled_sections(rms_boundaries, song_duration)


def _make_unlabeled_sections(
    rms_boundaries: list[float], song_duration: float
) -> list[dict[str, Any]]:
    """Build section dicts from raw RMS boundaries with no labels."""
    all_times = [0.0] + sorted(rms_boundaries) + [song_duration]
    sections: list[dict[str, Any]] = []
    for i in range(len(all_times) - 1):
        start, end = all_times[i], all_times[i + 1]
        if end - start < 0.2:
            continue
        sections.append({
            "start": start,
            "end": end,
            "label": None,
            "label_confidence": 0.0,
            "boundary_confidence": 0.0,
        })
    return sections if sections else [{"start": 0.0, "end": song_duration, "label": None, "label_confidence": 0.0, "boundary_confidence": 0.0}]
