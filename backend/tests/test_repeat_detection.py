"""Tests for Commit 118: Repetition-Aware Section Detection."""
from __future__ import annotations

import numpy as np
import pytest

from app.repeat_detection import (
    MIN_SEGMENT_FRAMES,
    SIMILARITY_THRESHOLD,
    _assign_consistent_labels,
    _group_by_connected_components,
    _segment_frame_ranges,
    _segment_similarity_matrix,
    detect_repeated_sections,
    librosa_segment_recurrence,
)


# ---- Helpers -----------------------------------------------------------------


def _make_times(duration: float, hop_sec: float = 0.1) -> np.ndarray:
    """Create a common time grid."""
    return np.arange(0.0, duration, hop_sec)


def _make_repeated_chroma(
    n_frames_per_section: int = 250,
    n_sections: int = 4,
    pattern_seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Create chroma with repeated patterns.

    Sections 0 and 2 share pattern A (verse), sections 1 and 3 share pattern B (chorus).
    Uses one-hot-like pitch profiles so cosine similarity clearly distinguishes sections.
    """
    rng = np.random.RandomState(pattern_seed)
    noise_scale = 0.05  # small noise so sections are clearly different

    # Pattern A: verse — emphasize C, E, G (C major triad)
    pattern_a = np.full((12, n_frames_per_section), noise_scale)
    pattern_a[0, :] = 0.8  # C
    pattern_a[4, :] = 0.7  # E
    pattern_a[7, :] = 0.6  # G

    # Pattern B: chorus — emphasize D, F#, A (D major triad, different key area)
    pattern_b = np.full((12, n_frames_per_section), noise_scale)
    pattern_b[2, :] = 0.8  # D
    pattern_b[6, :] = 0.7  # F#
    pattern_b[9, :] = 0.6  # A

    sections = []
    for i in range(n_sections):
        if i % 2 == 0:
            sections.append(pattern_a.copy())
        else:
            sections.append(pattern_b.copy())

    chroma = np.hstack(sections)
    total_frames = chroma.shape[1]
    times = np.arange(total_frames) * 512 / 22050  # assuming hop_length=512, sr=22050
    return chroma, times


def _make_unique_chroma(n_sections: int = 4, n_frames: int = 250) -> tuple[np.ndarray, np.ndarray]:
    """Create chroma where every section is unique (no repeats).

    Each section emphasizes a different single pitch class, ensuring low
    cross-similarity.
    """
    sections = []
    for i in range(n_sections):
        sec = np.full((12, n_frames), 0.05)
        sec[i % 12, :] = 0.9  # each section emphasizes a unique pitch class
        sections.append(sec)
    chroma = np.hstack(sections)
    total_frames = chroma.shape[1]
    times = np.arange(total_frames) * 512 / 22050
    return chroma, times


# ---- Unit tests: _segment_frame_ranges --------------------------------------


class TestSegmentFrameRanges:
    def test_basic_conversion(self):
        times = np.arange(0.0, 10.0, 0.1)
        boundaries = [0.0, 3.0, 7.0, 10.0]
        ranges = _segment_frame_ranges(boundaries, times)
        assert len(ranges) == 3
        assert ranges[0] == (0, 30)
        assert ranges[1] == (30, 70)
        assert ranges[2] == (70, 100)

    def test_single_segment(self):
        times = np.arange(0.0, 5.0, 0.1)
        boundaries = [0.0, 5.0]
        ranges = _segment_frame_ranges(boundaries, times)
        assert len(ranges) == 1
        assert ranges[0][0] == 0
        assert ranges[0][1] == len(times)

    def test_short_segment_gets_min_frame(self):
        """Segments shorter than one hop still get at least one frame."""
        times = np.arange(0.0, 10.0, 0.1)
        boundaries = [0.0, 0.05, 10.0]  # first segment is 0.05s < one hop
        ranges = _segment_frame_ranges(boundaries, times)
        assert len(ranges) == 2
        # First segment should have at least 1 frame
        assert ranges[0][1] > ranges[0][0] or ranges[0][1] == ranges[0][0] + 1


# ---- Unit tests: _segment_similarity_matrix ----------------------------------


class TestSegmentSimilarityMatrix:
    def test_diagonal_is_self_similarity(self):
        """Each segment should have high self-similarity relative to cross-similarity."""
        recurrence = np.eye(100)
        frame_ranges = [(0, 50), (50, 100)]
        sim = _segment_similarity_matrix(recurrence, frame_ranges)
        assert sim.shape == (2, 2)
        # Self-similarity: mean of identity block = 1/N = 0.02
        # Cross-similarity: mean of zeros = 0.0
        # Self-similarity should be strictly greater than cross-similarity
        assert sim[0, 0] > sim[0, 1]
        assert sim[1, 1] > sim[0, 1]

    def test_identical_segments_high_similarity(self):
        """Two identical segment blocks should have high similarity."""
        block = np.ones((10, 10)) * 0.9
        recurrence = np.block([
            [block, block],
            [block, block],
        ])
        frame_ranges = [(0, 10), (10, 20)]
        sim = _segment_similarity_matrix(recurrence, frame_ranges)
        # Cross-similarity should be high
        assert sim[0, 1] == pytest.approx(0.9, abs=0.01)
        assert sim[1, 0] == pytest.approx(0.9, abs=0.01)

    def test_different_segments_low_similarity(self):
        """Two different segment blocks should have low similarity."""
        block_a = np.ones((10, 10)) * 0.1
        block_b = np.ones((10, 10)) * 0.9
        recurrence = np.block([
            [block_a, np.zeros((10, 10))],
            [np.zeros((10, 10)), block_b],
        ])
        frame_ranges = [(0, 10), (10, 20)]
        sim = _segment_similarity_matrix(recurrence, frame_ranges)
        assert sim[0, 1] == pytest.approx(0.0, abs=0.01)


# ---- Unit tests: _group_by_connected_components ------------------------------


class TestGroupByConnectedComponents:
    def test_two_groups(self):
        sim = np.array([
            [0.0, 0.9, 0.1, 0.05],
            [0.9, 0.0, 0.05, 0.1],
            [0.1, 0.05, 0.0, 0.85],
            [0.05, 0.1, 0.85, 0.0],
        ])
        groups = _group_by_connected_components(sim, threshold=0.5)
        assert len(groups) == 2
        # Verify grouping: {0,1} and {2,3}
        group_sets = [set(g) for g in groups]
        assert {0, 1} in group_sets
        assert {2, 3} in group_sets

    def test_all_unique(self):
        sim = np.array([
            [0.0, 0.2, 0.1],
            [0.2, 0.0, 0.15],
            [0.1, 0.15, 0.0],
        ])
        groups = _group_by_connected_components(sim, threshold=0.5)
        assert len(groups) == 3

    def test_all_same_group(self):
        sim = np.array([
            [0.0, 0.8, 0.7],
            [0.8, 0.0, 0.9],
            [0.7, 0.9, 0.0],
        ])
        groups = _group_by_connected_components(sim, threshold=0.5)
        assert len(groups) == 1
        assert set(groups[0]) == {0, 1, 2}


# ---- Unit tests: _assign_consistent_labels -----------------------------------


class TestAssignConsistentLabels:
    def test_single_occurrence_no_suffix(self):
        labels = ["Intro", "Verse", "Chorus", "Bridge"]
        groups = [[0], [1], [2], [3]]
        results = _assign_consistent_labels(labels, groups)
        assert len(results) == 4
        for r in results:
            assert r["is_repeated"] is False
            assert r["repeat_count"] == 1

    def test_repeated_section_gets_suffix(self):
        labels = ["Verse", "Chorus", "Verse", "Chorus"]
        groups = [[0, 2], [1, 3]]
        results = _assign_consistent_labels(labels, groups)
        # Verse group: index 0 first (no suffix), index 2 second (with suffix)
        assert results[0]["label"] == "Verse"
        assert results[0]["repeat_index"] == 1
        assert results[0]["repeat_count"] == 2
        assert results[0]["is_repeated"] is True
        assert results[2]["label"] == "Verse (2 of 2)"
        assert results[2]["repeat_index"] == 2

    def test_three_repeated_sections(self):
        labels = ["Chorus", "Verse", "Chorus", "Bridge", "Chorus"]
        groups = [[0, 2, 4], [1], [3]]
        results = _assign_consistent_labels(labels, groups)
        # Chorus group: indices 0, 2, 4
        assert results[0]["label"] == "Chorus"
        assert results[0]["repeat_index"] == 1
        assert results[0]["repeat_count"] == 3
        assert results[2]["label"] == "Chorus (2 of 3)"
        assert results[2]["repeat_index"] == 2
        assert results[4]["label"] == "Chorus (3 of 3)"
        assert results[4]["repeat_index"] == 3

    def test_group_ids_are_consistent(self):
        labels = ["A", "B", "A", "C", "B"]
        groups = [[0, 2], [1, 4], [3]]
        results = _assign_consistent_labels(labels, groups)
        # Same group should have same repeat_group_id
        assert results[0]["repeat_group_id"] == results[2]["repeat_group_id"]
        assert results[1]["repeat_group_id"] == results[4]["repeat_group_id"]
        # Different groups should have different IDs
        assert results[0]["repeat_group_id"] != results[1]["repeat_group_id"]
        assert results[0]["repeat_group_id"] != results[3]["repeat_group_id"]


# ---- Integration tests: detect_repeated_sections -----------------------------


class TestDetectRepeatedSections:
    def test_verse_chorus_verse_chorus(self):
        """Verse-Chorus-Verse-Chorus should group verses together and choruses together."""
        chroma, times = _make_repeated_chroma(n_frames_per_section=250, n_sections=4)
        boundaries = [0.0, times[250], times[500], times[750], times[999]]
        existing_labels = ["Verse", "Chorus", "Verse", "Chorus"]

        results = detect_repeated_sections(
            chroma=chroma,
            times=times,
            boundaries=boundaries,
            existing_labels=existing_labels,
        )

        assert results is not None
        assert len(results) == 4

        # Verify grouping
        verse_group = results[0]["repeat_group_id"]
        chorus_group = results[1]["repeat_group_id"]
        assert verse_group != chorus_group
        assert results[2]["repeat_group_id"] == verse_group
        assert results[3]["repeat_group_id"] == chorus_group

        # Verify labels
        assert results[0]["label"] == "Verse"
        assert results[2]["label"] == "Verse (2 of 2)"
        assert results[1]["label"] == "Chorus"
        assert results[3]["label"] == "Chorus (2 of 2)"

    def test_three_choruses(self):
        """Three chorus sections should all be in the same group."""
        chroma, times = _make_repeated_chroma(n_frames_per_section=200, n_sections=6)
        boundaries = [0.0, times[200], times[400], times[600], times[800], times[1000], times[1199]]
        # Sections: V, C, V, C, V, C (indices 1, 3, 5 are choruses)
        existing_labels = ["Verse", "Chorus", "Verse", "Chorus", "Verse", "Chorus"]

        results = detect_repeated_sections(
            chroma=chroma,
            times=times,
            boundaries=boundaries,
            existing_labels=existing_labels,
        )

        assert results is not None
        # All choruses should be in the same group
        chorus_groups = {results[i]["repeat_group_id"] for i in [1, 3, 5]}
        assert len(chorus_groups) == 1
        # All verses should be in the same group
        verse_groups = {results[i]["repeat_group_id"] for i in [0, 2, 4]}
        assert len(verse_groups) == 1

    def test_single_section_no_repeat(self):
        """One section should not be marked as repeated."""
        chroma, times = _make_repeated_chroma(n_frames_per_section=100, n_sections=1)
        boundaries = [0.0, times[99]]
        existing_labels = ["Intro"]

        results = detect_repeated_sections(
            chroma=chroma,
            times=times,
            boundaries=boundaries,
            existing_labels=existing_labels,
        )

        # < 2 sections returns None
        assert results is None

    def test_unique_sections_no_grouping(self):
        """Four unique sections should each be in their own group."""
        chroma, times = _make_unique_chroma(n_sections=4, n_frames=300)
        boundaries = [0.0, times[300], times[600], times[900], times[1199]]
        existing_labels = ["Intro", "Verse", "Chorus", "Outro"]

        results = detect_repeated_sections(
            chroma=chroma,
            times=times,
            boundaries=boundaries,
            existing_labels=existing_labels,
            similarity_threshold=0.8,  # high threshold = harder to group
        )

        assert results is not None
        # Each section should be unique (not repeated)
        for r in results:
            assert r["is_repeated"] is False

    def test_invalid_chroma_returns_none(self):
        """None chroma should return None gracefully."""
        times = np.arange(0.0, 10.0, 0.1)
        results = detect_repeated_sections(
            chroma=None,  # type: ignore[arg-type]
            times=times,
            boundaries=[0.0, 5.0, 10.0],
            existing_labels=["A", "B"],
        )
        assert results is None

    def test_label_suffix_format(self):
        """Verify the exact label suffix format 'Label (N of M)'."""
        chroma, times = _make_repeated_chroma(n_frames_per_section=250, n_sections=4)
        boundaries = [0.0, times[250], times[500], times[750], times[999]]
        existing_labels = ["Chorus", "Verse", "Chorus", "Verse"]

        results = detect_repeated_sections(
            chroma=chroma,
            times=times,
            boundaries=boundaries,
            existing_labels=existing_labels,
        )

        assert results is not None
        # Check format: first occurrence has no suffix
        assert "(" not in results[0]["label"]
        assert results[0]["label"] == "Chorus"
        # Second occurrence of Chorus (index 2) has suffix
        assert results[2]["label"] == "Chorus (2 of 2)"
        # Verse (index 1) is first occurrence, no suffix
        assert results[1]["label"] == "Verse"
        assert results[3]["label"] == "Verse (2 of 2)"

    def test_bridge_unaffected(self):
        """A unique bridge section should not be grouped with anything."""
        chroma, times = _make_repeated_chroma(n_frames_per_section=200, n_sections=4)
        # Add a unique bridge section in the middle — emphasize a different pitch class
        bridge_chroma = np.full((12, 200), 0.05)
        bridge_chroma[5, :] = 0.9  # F — unique pitch class not in verse/chorus patterns
        full_chroma = np.hstack([
            chroma[:, :200],     # Verse 1 (C, E, G)
            bridge_chroma,       # Bridge (F — unique)
            chroma[:, 200:400],  # Chorus 1 (D, F#, A)
            chroma[:, 400:600],  # Verse 2 (C, E, G)
        ])
        total = full_chroma.shape[1]
        times_full = np.arange(total) * 512 / 22050
        boundaries = [0.0, times_full[200], times_full[400], times_full[600], times_full[min(total - 1, 799)]]
        existing_labels = ["Verse", "Bridge", "Chorus", "Verse"]

        results = detect_repeated_sections(
            chroma=full_chroma,
            times=times_full,
            boundaries=boundaries,
            existing_labels=existing_labels,
        )

        assert results is not None
        # Bridge should be in its own group
        bridge_result = results[1]
        assert bridge_result["is_repeated"] is False
        assert bridge_result["label"] == "Bridge"
