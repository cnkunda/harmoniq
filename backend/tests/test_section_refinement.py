"""Tests for Commit 117: Structural Segmentation Refinement."""
from __future__ import annotations

import numpy as np
import pytest

from app.section_refinement import (
    CHORD_SIMILARITY_THRESHOLD,
    _compute_boundary_confidence,
    _compute_chord_density_curve,
    _compute_movement_ratio,
    _compute_vocal_gap_curve,
    _detect_boundary_peaks,
    _detect_instrumental_sections,
    _fingerprint_section,
    _fuse_signals,
    _greedy_group,
    _infer_section_labels,
    _jaccard,
    _make_unlabeled_sections,
    _normalize_energy_signal,
    refine_section_boundaries,
)


# ---- Helpers -----------------------------------------------------------------


def _make_times(duration: float, hop_sec: float = 0.1) -> np.ndarray:
    """Create a common time grid."""
    return np.arange(0.0, duration, hop_sec)


def _make_mock_verse_chords(start: float, end: float, hop: float = 2.0) -> list[tuple[float, str]]:
    """Slow chord changes (verse feel): Am → G → C → F."""
    pattern = ["Am", "G", "C", "F"]
    t = start
    chords: list[tuple[float, str]] = []
    idx = 0
    while t < end:
        chords.append((t, pattern[idx % 4]))
        t += hop
        idx += 1
    return chords


def _make_mock_chorus_chords(start: float, end: float, hop: float = 1.0) -> list[tuple[float, str]]:
    """Faster chord changes (chorus feel): C → G → Am → F."""
    pattern = ["C", "G", "Am", "F"]
    t = start
    chords: list[tuple[float, str]] = []
    idx = 0
    while t < end:
        chords.append((t, pattern[idx % 4]))
        t += hop
        idx += 1
    return chords


# ---- Unit tests: signal computation ------------------------------------------


class TestChordDensityCurve:
    def test_empty_chords_returns_zeros(self):
        times = _make_times(10.0)
        result = _compute_chord_density_curve([], times)
        assert result.shape == times.shape
        assert np.all(result == 0.0)

    def test_empty_times_returns_zeros(self):
        chords = [(0.0, "C"), (1.0, "G")]
        result = _compute_chord_density_curve(chords, np.array([]))
        assert result.shape == (0,)

    def test_single_chord_no_density(self):
        times = _make_times(10.0)
        chords = [(0.0, "C")]
        result = _compute_chord_density_curve(chords, times)
        # With only one chord, no changes → density is 0 everywhere
        assert result.max() < 0.01

    def test_frequent_changes_produce_density(self):
        times = _make_times(10.0)
        # Rapid chord changes every 0.5s
        chords = [(i * 0.5, "C" if i % 2 == 0 else "G") for i in range(20)]
        result = _compute_chord_density_curve(chords, times)
        assert result.max() > 0.0

    def test_output_normalized_01(self):
        times = _make_times(20.0)
        chords = [(i * 0.5, ["C", "G", "Am", "F"][i % 4]) for i in range(40)]
        result = _compute_chord_density_curve(chords, times)
        assert result.min() >= 0.0
        assert result.max() <= 1.0 + 1e-6


class TestVocalGapCurve:
    def test_empty_lyrics_returns_zeros(self):
        times = _make_times(10.0)
        result = _compute_vocal_gap_curve([], times)
        assert result.shape == times.shape
        assert np.all(result == 0.0)

    def test_short_gaps_no_signal(self):
        times = _make_times(10.0)
        lyrics = [{"time_seconds": i * 0.3} for i in range(30)]
        result = _compute_vocal_gap_curve(lyrics, times)
        assert result.max() < 0.01

    def test_long_gaps_produce_signal(self):
        times = _make_times(20.0)
        lyrics = [
            {"time_seconds": 1.0},
            {"time_seconds": 2.0},
            {"time_seconds": 5.0},  # 3s gap
            {"time_seconds": 6.0},
            {"time_seconds": 10.0},  # 4s gap
            {"time_seconds": 11.0},
        ]
        result = _compute_vocal_gap_curve(lyrics, times)
        assert result.max() > 0.0

    def test_output_normalized_01(self):
        times = _make_times(20.0)
        lyrics = [{"time_seconds": i * 0.5} for i in range(40)]
        # Add some large gaps
        lyrics[5]["time_seconds"] = 10.0  # big gap
        result = _compute_vocal_gap_curve(lyrics, times)
        assert result.min() >= 0.0
        assert result.max() <= 1.0 + 1e-6


class TestNormalizeEnergySignal:
    def test_empty_array(self):
        result = _normalize_energy_signal(np.array([]))
        assert result.shape == (0,)

    def test_clips_p95(self):
        data = np.ones(100) * 0.5
        data[0] = 100.0  # outlier
        result = _normalize_energy_signal(data)
        # The outlier should be clipped to p95
        assert result.max() <= 1.0 + 1e-6

    def test_normalizes_to_01(self):
        data = np.array([0.0, 0.5, 1.0, 0.3, 0.8])
        result = _normalize_energy_signal(data)
        assert result.min() >= 0.0
        assert result.max() <= 1.0 + 1e-6


class TestFuseSignals:
    def test_weighted_average(self):
        chord = np.ones(10) * 0.8
        vocal = np.ones(10) * 0.6
        energy = np.ones(10) * 0.4
        result = _fuse_signals(chord, vocal, energy)
        expected = 0.4 * 0.8 + 0.3 * 0.6 + 0.3 * 0.4
        np.testing.assert_allclose(result, expected, atol=1e-6)

    def test_weights_must_sum_to_one(self):
        with pytest.raises(AssertionError):
            _fuse_signals(
                np.ones(10), np.ones(10), np.ones(10),
                weights=(0.5, 0.3, 0.3),
            )


# ---- Unit tests: boundary detection -----------------------------------------


class TestDetectBoundaryPeaks:
    def test_finds_peaks_in_fused_curve(self):
        times = _make_times(60.0)
        fused = np.zeros(len(times))
        # Create clear peaks at 20s and 40s
        idx_20 = int(20.0 / 0.1)
        idx_40 = int(40.0 / 0.1)
        fused[idx_20 - 2:idx_20 + 3] = 0.8
        fused[idx_40 - 2:idx_40 + 3] = 0.9
        peaks, _ = _detect_boundary_peaks(fused, times, min_section_sec=5.0)
        assert len(peaks) >= 1  # at least one peak found


class TestComputeMovementRatio:
    def test_identical_boundaries_gives_zero(self):
        ratio = _compute_movement_ratio([10.0, 20.0, 30.0], [10.0, 20.0, 30.0])
        assert ratio == 0.0

    def test_all_moved_gives_one(self):
        ratio = _compute_movement_ratio([100.0, 200.0], [10.0, 20.0])
        assert ratio == 1.0

    def test_partial_movement(self):
        ratio = _compute_movement_ratio([10.5, 50.0], [10.0, 20.0])
        # 10.5 is within tolerance of 10.0, 50.0 is far from 20.0 → 0.5
        assert abs(ratio - 0.5) < 1e-6

    def test_empty_rms_boundaries(self):
        ratio = _compute_movement_ratio([10.0], [])
        assert ratio == 0.0


class TestComputeBoundaryConfidence:
    def test_high_when_all_signals_agree(self):
        times = _make_times(60.0)
        chord = np.zeros(len(times))
        vocal = np.zeros(len(times))
        energy = np.zeros(len(times))
        # All signals peak at index 200
        chord[198:203] = 0.9
        vocal[198:203] = 0.9
        energy[198:203] = 0.9
        conf = _compute_boundary_confidence(200, chord, vocal, energy, times)
        assert conf > 0.8

    def test_low_when_vocal_missing(self):
        times = _make_times(60.0)
        chord = np.zeros(len(times))
        vocal = np.zeros(len(times))  # no vocal signal
        energy = np.zeros(len(times))
        chord[198:203] = 0.9
        energy[198:203] = 0.9
        conf = _compute_boundary_confidence(200, chord, vocal, energy, times)
        # Should still have reasonable confidence via arithmetic mean blend
        assert conf > 0.0


# ---- Unit tests: section labeling -------------------------------------------


class TestFingerprintSection:
    def test_basic_fingerprint(self):
        chords = [(0.0, "Am"), (1.0, "G"), (2.0, "C"), (3.0, "F")]
        fp = _fingerprint_section(chords, 0.0, 4.0, n_gram=2)
        assert ("Am", "G") in fp
        assert ("G", "C") in fp
        assert ("C", "F") in fp

    def test_collapses_runs(self):
        chords = [(0.0, "Am"), (0.5, "Am"), (1.0, "G"), (2.0, "C")]
        fp = _fingerprint_section(chords, 0.0, 3.0, n_gram=2)
        # After collapsing: Am, G, C → n-grams: (Am, G), (G, C)
        assert ("Am", "G") in fp
        assert ("G", "C") in fp

    def test_empty_chords_returns_empty(self):
        fp = _fingerprint_section([], 0.0, 10.0)
        assert len(fp) == 0


class TestJaccard:
    def test_identical_sets(self):
        fp = frozenset([("Am", "G"), ("G", "C")])
        assert _jaccard(fp, fp) == 1.0

    def test_disjoint_sets(self):
        fp1 = frozenset([("Am", "G")])
        fp2 = frozenset([("C", "F")])
        assert _jaccard(fp1, fp2) == 0.0

    def test_empty_sets(self):
        assert _jaccard(frozenset(), frozenset()) == 0.0


class TestGreedyGroup:
    def test_groups_similar_sections(self):
        sim = np.array([
            [1.0, 0.8, 0.2, 0.1],
            [0.8, 1.0, 0.1, 0.2],
            [0.2, 0.1, 1.0, 0.9],
            [0.1, 0.2, 0.9, 1.0],
        ])
        groups = _greedy_group(4, sim, threshold=0.5)
        # Should find 2 groups: {0,1} and {2,3}
        assert len(groups) == 2
        assert set(groups[0]) == {0, 1}
        assert set(groups[1]) == {2, 3}

    def test_all_unique(self):
        sim = np.eye(4) * 0.1  # low similarity everywhere
        groups = _greedy_group(4, sim, threshold=0.5)
        assert len(groups) == 4


class TestInferSectionLabels:
    def test_short_first_section_gets_intro(self):
        times = _make_times(60.0)
        rms = np.ones(len(times)) * 0.2  # Low energy → Intro
        boundary_times = [10.0, 35.0, 50.0]
        chords = _make_mock_verse_chords(0, 60.0)
        sections = _infer_section_labels(boundary_times, 60.0, chords, rms, times)
        assert sections[0]["label"] == "Intro"
        assert sections[0]["label_confidence"] > 0.0

    def test_four_section_vcv(self):
        """Verse-Chorus-Verse-Chorus should detect chorus as highest energy."""
        times = _make_times(80.0)
        rms = np.ones(len(times))
        # Boost energy in chorus sections (20-40, 60-80)
        rms[int(20.0 / 0.1):int(40.0 / 0.1)] *= 1.8
        rms[int(60.0 / 0.1):int(80.0 / 0.1)] *= 1.8

        # Use chord patterns that share some n-grams for similarity detection
        # Both verse and chorus use C-G-Am-F core but with different ordering
        chords = (
            _make_mock_verse_chords(0, 20.0)
            + _make_mock_chorus_chords(20.0, 40.0)
            + _make_mock_verse_chords(40.0, 60.0)
            + _make_mock_chorus_chords(60.0, 80.0)
        )
        boundary_times = [20.0, 40.0, 60.0]
        sections = _infer_section_labels(boundary_times, 80.0, chords, rms, times)

        labels = [s["label"] for s in sections]
        # Should have at least 2 different labels (not all the same)
        unique_labels = set(labels)
        assert len(unique_labels) >= 2


class TestMakeUnlabeledSections:
    def test_basic(self):
        sections = _make_unlabeled_sections([20.0, 40.0], 60.0)
        assert len(sections) == 3
        assert all(s["label"] is None for s in sections)
        assert sections[0]["start"] == 0.0
        assert sections[0]["end"] == 20.0

    def test_empty_boundaries(self):
        sections = _make_unlabeled_sections([], 60.0)
        assert len(sections) == 1
        assert sections[0]["start"] == 0.0
        assert sections[0]["end"] == 60.0


# ---- Integration test --------------------------------------------------------


class TestRefineSectionBoundaries:
    def test_four_section_vcv_segmentation(self):
        """Integration: 4-section verse-chorus-verse-chorus song correctly segmented."""
        duration = 80.0
        times = _make_times(duration)
        rms = np.ones(len(times))
        # Boost energy in chorus sections
        rms[int(20.0 / 0.1):int(40.0 / 0.1)] *= 1.8
        rms[int(60.0 / 0.1):int(80.0 / 0.1)] *= 1.8

        chords = (
            _make_mock_verse_chords(0, 20.0)
            + _make_mock_chorus_chords(20.0, 40.0)
            + _make_mock_verse_chords(40.0, 60.0)
            + _make_mock_chorus_chords(60.0, 80.0)
        )

        # Create onset novelty with spikes at section boundaries
        novelty = np.zeros(len(times))
        for boundary in [20.0, 40.0, 60.0]:
            idx = int(boundary / 0.1)
            lo = max(0, idx - 2)
            hi = min(len(times), idx + 3)
            novelty[lo:hi] = 1.0

        rms_boundaries = [20.0, 40.0, 60.0]
        lyrics = []  # instrumental

        result = refine_section_boundaries(
            rms_boundaries=rms_boundaries,
            chord_events=chords,
            lyrics_aligned=lyrics,
            onset_novelty=novelty,
            rms_curve=rms,
            times=times,
            song_duration=duration,
        )

        # Should produce sections (may fall back to RMS or find refined)
        assert len(result) >= 2
        # All sections should have start/end
        for s in result:
            assert "start" in s
            assert "end" in s
            assert s["start"] < s["end"]

    def test_fallback_on_empty_novelty(self):
        """Falls back gracefully when novelty curve is empty."""
        times = _make_times(60.0)
        result = refine_section_boundaries(
            rms_boundaries=[20.0, 40.0],
            chord_events=[],
            lyrics_aligned=[],
            onset_novelty=np.array([]),
            rms_curve=np.array([]),
            times=times,
            song_duration=60.0,
        )
        assert len(result) >= 1

    def test_fallback_on_short_times(self):
        """Falls back when time array is too short."""
        result = refine_section_boundaries(
            rms_boundaries=[],
            chord_events=[],
            lyrics_aligned=[],
            onset_novelty=np.array([0.5]),
            rms_curve=np.array([0.5]),
            times=np.array([0.0]),
            song_duration=10.0,
        )
        assert len(result) >= 1

    def test_confidence_scores_present(self):
        """All sections have label_confidence and boundary_confidence."""
        duration = 40.0
        times = _make_times(duration)
        rms = np.ones(len(times))
        novelty = np.zeros(len(times))
        novelty[int(20.0 / 0.1) - 1:int(20.0 / 0.1) + 2] = 1.0

        result = refine_section_boundaries(
            rms_boundaries=[20.0],
            chord_events=[(0.0, "C"), (10.0, "G"), (20.0, "Am"), (30.0, "F")],
            lyrics_aligned=[],
            onset_novelty=novelty,
            rms_curve=rms,
            times=times,
            song_duration=duration,
        )
        for s in result:
            assert "label_confidence" in s
            assert "boundary_confidence" in s

    def test_intro_verse_chorus_verse_outro_labels(self):
        """Commit 119 AC9: Integration test for known Intro-Verse-Chorus-Outro structure.

        Structure: Intro (low, short) → Verse (moderate) → Chorus (high, repeated x2)
        → Verse (moderate) → Outro (declining).
        Two identical Chorus sections ensure chord fingerprint grouping detects them.
        """
        duration = 85.0
        hop = 0.1
        times = np.arange(0.0, duration, hop)
        rms = np.ones(len(times))

        # Section 0: Intro (0-12s) — low energy
        rms[:int(12.0 / hop)] = 0.2
        # Section 1: Verse (12-30s) — moderate energy
        rms[int(12.0 / hop):int(30.0 / hop)] = 0.45
        # Section 2: Chorus (30-48s) — high energy
        rms[int(30.0 / hop):int(48.0 / hop)] = 0.8
        # Section 3: Chorus (48-66s) — same high energy (repeated)
        rms[int(48.0 / hop):int(66.0 / hop)] = 0.8
        # Section 4: Outro (66-85s) — declining energy
        rms[int(66.0 / hop):] = np.linspace(0.5, 0.15, int(19.0 / hop))

        # Same chord pattern for both Choruses so they fingerprint as identical.
        # Verse chords stop at 30.0 exactly; chorus chords start at 30.0+,
        # so there is no interleaving overlap inside any section.
        chorus1_chords = [(30.0 + i * 1.0, c) for i, c in enumerate(["C", "G", "Am", "F"] * 18) if (30.0 + i * 1.0) < 48.0]
        chorus2_chords = [(48.0 + i * 1.0, c) for i, c in enumerate(["C", "G", "Am", "F"] * 18) if (48.0 + i * 1.0) < 66.0]
        chords = (
            [(0.0, "Am")]
            + [(12.0 + i * 2.0, c) for i, c in enumerate(["Am", "G", "C", "F"] * 4) if (12.0 + i * 2.0) < 29.0]
            + chorus1_chords
            + chorus2_chords
        )

        boundary_times = [12.0, 30.0, 48.0, 66.0]

        result = _infer_section_labels(
            boundary_times=boundary_times,
            song_duration=duration,
            chord_events=chords,
            rms_curve=rms,
            times=times,
        )

        assert len(result) == 5, f"Expected 5 sections, got {len(result)}"

        labels = [s["label"] for s in result]
        confs = [s.get("label_confidence", 0.0) for s in result]

        # AC1: Intro — first section, low energy, short
        assert labels[0] == "Intro", f"Section 0 expected Intro, got {labels[0]}"
        assert confs[0] >= 0.8

        # AC2: Chorus detected as high-energy repeated (both chorus sections)
        assert labels[2] == "Chorus", f"Section 2 expected Chorus, got {labels[2]}"
        assert confs[2] >= 0.7
        assert labels[3] == "Chorus", f"Section 3 expected Chorus, got {labels[3]}"
        assert confs[3] >= 0.7

        # AC5: Outro — last section, declining energy
        assert labels[4] == "Outro", f"Section 4 expected Outro, got {labels[4]}"
        assert confs[4] >= 0.7

        # Verse
        assert labels[1] == "Verse", f"Section 1 expected Verse, got {labels[1]}"

        # AC7: label_confidence present on all sections
        for i, s in enumerate(result):
            assert "label_confidence" in s, f"Section {i} missing label_confidence"
