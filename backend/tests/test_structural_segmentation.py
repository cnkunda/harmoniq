"""Tests for structural segmentation refinement (Commit 115)."""

from __future__ import annotations

import numpy as np
import pytest

from app.schemas import ChordEvent, ChordTimeline
from app.structural_segmentation import (
    boundary_stability,
    chord_change_density,
    detect_boundaries,
    fuse_boundary_signals,
    infer_section_labels,
    refine_section_boundaries,
    vocal_gap_novelty,
)


# --- Synthetic fixtures -----------------------------------------------------

VERSE = ["C", "Am", "F", "G"]
CHORUS = ["F", "C", "G", "C"]


def _chord_timeline_verse_chorus() -> ChordTimeline:
    """Four sections (10s each): verse / chorus / verse / chorus."""
    events: list[ChordEvent] = []

    def add(start: float, prog: list[str]) -> None:
        for j, ch in enumerate(prog):
            events.append(ChordEvent(timestamp=start + j * 2.5, chord=ch, confidence=0.9))

    add(0.0, VERSE)
    add(10.0, CHORUS)
    add(20.0, VERSE)
    add(30.0, CHORUS)
    return ChordTimeline(events=events)


def _times() -> np.ndarray:
    return np.arange(0.0, 40.0, 0.5)


def _novelty_curve(times: np.ndarray) -> np.ndarray:
    """Energy/onset novelty with peaks at the three interior boundaries."""
    novelty = np.zeros_like(times)
    for t0 in (10.0, 20.0, 30.0):
        novelty += np.exp(-((times - t0) ** 2) / (2 * 0.8**2))
    return novelty


def _loudness_curve(times: np.ndarray) -> np.ndarray:
    """Chorus sections louder than verse sections."""
    energy = np.where((times >= 10.0) & (times < 20.0), 0.6, 0.2)
    energy = np.where((times >= 30.0) & (times < 40.0), 0.6, energy)
    return energy


def _lyrics() -> list[dict]:
    """Words every 0.5s with 2.5s vocal gaps centered on the boundaries."""
    rows: list[dict] = []
    for t in np.arange(0.25, 40.0, 0.5):
        t = float(t)
        if any(abs(t - c) < 1.25 for c in (10.0, 20.0, 30.0)):
            continue
        rows.append({"word": "w", "time_seconds": t})
    return rows


# --- Unit tests: signals ----------------------------------------------------


def test_chord_change_density_peaks_at_dense_changes():
    times = np.arange(0.0, 10.0, 0.1)
    events = [
        ChordEvent(timestamp=0.0, chord="C", confidence=0.9),
        ChordEvent(timestamp=4.0, chord="G", confidence=0.9),
        ChordEvent(timestamp=4.3, chord="Am", confidence=0.9),
        ChordEvent(timestamp=4.6, chord="F", confidence=0.9),
        ChordEvent(timestamp=4.9, chord="Dm", confidence=0.9),
        ChordEvent(timestamp=5.2, chord="E", confidence=0.9),
        ChordEvent(timestamp=9.0, chord="G", confidence=0.9),
    ]
    density = chord_change_density(ChordTimeline(events=events), times=times, window_s=1.0)
    peak_time = times[int(np.argmax(density))]
    assert 4.0 < peak_time < 6.0


def test_chord_change_density_ignores_no_chord():
    times = np.arange(0.0, 5.0, 0.1)
    events = [
        ChordEvent(timestamp=0.0, chord="C", confidence=0.9),
        ChordEvent(timestamp=1.0, chord="N", confidence=1.0),
        ChordEvent(timestamp=2.0, chord="G", confidence=0.9),
    ]
    density = chord_change_density(ChordTimeline(events=events), times=times)
    assert float(np.nanmax(density)) <= 1.0
    assert density.shape == times.shape


def test_vocal_gap_novelty_peaks_at_large_gaps():
    times = np.arange(0.0, 10.0, 0.1)
    words = [
        {"word": "a", "time_seconds": 1.0},
        {"word": "b", "time_seconds": 1.5},
        {"word": "c", "time_seconds": 4.5},  # 3s gap after 1.5
        {"word": "d", "time_seconds": 5.0},
    ]
    novelty = vocal_gap_novelty(words, times=times, gap_threshold_s=1.5)
    peak_time = times[int(np.argmax(novelty))]
    # Midpoint of the 1.5 -> 4.5 gap is 3.0.
    assert 2.5 < peak_time < 3.5


def test_vocal_gap_novelty_empty_returns_zeros():
    times = np.arange(0.0, 5.0, 0.1)
    novelty = vocal_gap_novelty([], times=times)
    assert np.all(novelty == 0.0)


def test_fuse_boundary_signals_weights():
    c = np.ones(10)
    v = np.zeros(10)
    e = np.zeros(10)
    fused = fuse_boundary_signals(c, v, e)
    assert np.allclose(fused, 0.4)
    assert np.allclose(fuse_boundary_signals(np.zeros(10), np.ones(10), np.zeros(10)), 0.3)
    assert np.allclose(fuse_boundary_signals(np.zeros(10), np.zeros(10), np.ones(10)), 0.3)


# --- Unit tests: boundary detection ----------------------------------------


def test_detect_boundaries_returns_top_peaks_and_confidence():
    times = np.arange(0.0, 40.0, 0.5)
    fused = _novelty_curve(times) * 0.6
    boundaries, confidence = detect_boundaries(fused, times, n_boundaries=3, min_gap_s=3.0)
    assert len(boundaries) == 3
    assert all(abs(b - t) < 1.5 for b, t in zip(sorted(boundaries), (10.0, 20.0, 30.0)))
    assert confidence > 0.5


def test_detect_boundaries_no_peaks_returns_empty():
    times = np.arange(0.0, 10.0, 0.5)
    fused = np.zeros_like(times)
    boundaries, confidence = detect_boundaries(fused, times, n_boundaries=3, min_gap_s=2.0)
    assert boundaries == []
    assert confidence == 0.0


def test_detect_boundaries_partial_yields_low_confidence():
    # Only one strong peak out of three expected -> completeness drags confidence
    # below the 0.6 refinement floor (so the caller falls back).
    times = np.arange(0.0, 40.0, 0.5)
    fused = np.zeros_like(times)
    fused[int(np.searchsorted(times, 10.0))] = 1.0
    boundaries, confidence = detect_boundaries(fused, times, n_boundaries=3, min_gap_s=3.0)
    assert len(boundaries) == 1
    assert confidence < 0.6


# --- Unit tests: label inference -------------------------------------------


def test_infer_section_labels_repetition_and_energy():
    times = _times()
    edges = [0.0, 10.0, 20.0, 30.0, 40.0]
    sections = infer_section_labels(
        edges,
        duration_s=40.0,
        chord_timeline=_chord_timeline_verse_chorus(),
        energy_curve=_loudness_curve(times),
        energy_times=times,
    )
    labels = [s.label for s in sections]
    assert labels == ["Verse", "Chorus", "Verse", "Chorus"]
    assert all(s.label_confidence > 0.5 for s in sections)


def test_infer_section_labels_intro_and_outro():
    times = np.arange(0.0, 30.0, 0.5)
    # Short first section (intro), declining energy into a short outro.
    edges = [0.0, 8.0, 22.0, 30.0]
    energy = np.where(times < 8.0, 0.2, 0.6)
    energy = np.where(times >= 22.0, 0.1, energy)
    # Unique progressions per section -> no repetition.
    events = [
        ChordEvent(timestamp=0.0, chord="C", confidence=0.9),
        ChordEvent(timestamp=8.0, chord="F", confidence=0.9),
        ChordEvent(timestamp=22.0, chord="G", confidence=0.9),
    ]
    sections = infer_section_labels(
        edges,
        duration_s=30.0,
        chord_timeline=ChordTimeline(events=events),
        energy_curve=energy,
        energy_times=times,
    )
    labels = [s.label for s in sections]
    assert labels[0] == "Intro"
    assert labels[-1] == "Outro"


def test_infer_section_labels_empty_returns_empty():
    assert infer_section_labels([], duration_s=10.0, chord_timeline=None) == []


# --- Unit test: boundary stability -----------------------------------------


def test_boundary_stability():
    baseline = [0.0, 10.0, 20.0, 30.0, 40.0]
    near = [0.0, 10.5, 20.5, 30.5, 40.0]
    assert boundary_stability(near, baseline, tol_s=2.0) < 0.5
    far = [0.0, 15.0, 25.0, 35.0, 40.0]
    assert boundary_stability(far, baseline, tol_s=2.0) >= 0.5


# --- Integration: full refine ----------------------------------------------


def test_integration_verse_chorus_segmentation():
    baseline = [
        {"label": "S0", "start_s": 0.0, "end_s": 10.0},
        {"label": "S1", "start_s": 10.0, "end_s": 20.0},
        {"label": "S2", "start_s": 20.0, "end_s": 30.0},
        {"label": "S3", "start_s": 30.0, "end_s": 40.0},
    ]
    times = _times()
    sections, confidence = refine_section_boundaries(
        baseline_segments=baseline,
        duration_s=40.0,
        chord_timeline=_chord_timeline_verse_chorus(),
        lyrics_aligned=_lyrics(),
        energy_novelty=_novelty_curve(times),
        energy_times=times,
        energy_curve=_loudness_curve(times),
    )
    assert len(sections) == 4
    assert [s.label for s in sections] == ["Verse", "Chorus", "Verse", "Chorus"]
    assert confidence >= 0.55
    refined_edges = [s.start_s for s in sections] + [sections[-1].end_s]
    assert boundary_stability(refined_edges, [0.0, 10.0, 20.0, 30.0, 40.0], tol_s=2.0) < 0.5


def test_refine_section_boundaries_no_signals_returns_empty():
    baseline = [
        {"label": "S0", "start_s": 0.0, "end_s": 20.0},
        {"label": "S1", "start_s": 20.0, "end_s": 40.0},
    ]
    sections, confidence = refine_section_boundaries(baseline_segments=baseline, duration_s=40.0)
    assert sections == []
    assert confidence == 0.0


def test_refine_section_boundaries_single_section_returns_empty():
    baseline = [{"label": "S0", "start_s": 0.0, "end_s": 12.0}]
    sections, confidence = refine_section_boundaries(baseline_segments=baseline, duration_s=12.0)
    assert sections == []
    assert confidence == 0.0


def test_refine_energy_only_boundaries_still_confident():
    # A boundary driven purely by energy novelty (no chords, no lyrics) must
    # still clear the confidence floor: energy is the baseline signal.
    baseline = [
        {"label": "S0", "start_s": 0.0, "end_s": 10.0},
        {"label": "S1", "start_s": 10.0, "end_s": 20.0},
        {"label": "S2", "start_s": 20.0, "end_s": 30.0},
        {"label": "S3", "start_s": 30.0, "end_s": 40.0},
    ]
    times = _times()
    sections, confidence = refine_section_boundaries(
        baseline_segments=baseline,
        duration_s=40.0,
        chord_timeline=None,
        lyrics_aligned=None,
        energy_novelty=_novelty_curve(times),
        energy_times=times,
    )
    assert len(sections) == 4
    assert confidence >= 0.6
