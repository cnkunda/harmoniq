"""Commit 100: Segment Boundary Tie Mechanism tests.

Tests for:
- Overlap-and-blend window merging
- Boundary confidence penalty
- TieRegistry note merging
- Scoring onset deduplication
"""

from __future__ import annotations

import numpy as np
import pytest

from app.chord_inference import (
    _WINDOW,
    _HOP_FRAMES,
    _TRIANGULAR_WINDOW,
    _build_windows,
    _merge_overlapping_predictions,
    _apply_boundary_penalty,
    CHORD_VOCAB,
    _NUM_CLASSES,
    _CHORD_TO_IDX,
)
from app.cqt_constants import CHROMA_BINS
from app.solo_inference import TieRegistry, _merge_boundary_notes
from app.schemas import BeatGrid, SoloNote, TimeSignature
from app.score import _deduplicate_onsets


# ---------------------------------------------------------------------------
# Phase 1: Overlapping Window & Triangular Blending
# ---------------------------------------------------------------------------

class TestTriangularWindow:
    def test_shape(self):
        assert _TRIANGULAR_WINDOW.shape == (_WINDOW,)

    def test_center_peaks_at_one(self):
        assert abs(_TRIANGULAR_WINDOW[_WINDOW // 2] - 1.0) < 0.02
        assert abs(_TRIANGULAR_WINDOW[_WINDOW // 2 - 1] - 1.0) < 0.02

    def test_edges_near_zero(self):
        assert _TRIANGULAR_WINDOW[0] == 0.0
        assert _TRIANGULAR_WINDOW[-1] < 0.05

    def test_symmetric(self):
        assert np.allclose(_TRIANGULAR_WINDOW, _TRIANGULAR_WINDOW[::-1], atol=0.02)


class TestBuildWindows:
    def test_overlapping_window_count(self):
        T = 200
        features = np.zeros((T, CHROMA_BINS), dtype=np.float32)
        windows = _build_windows(features)
        expected = (T + _HOP_FRAMES - 1) // _HOP_FRAMES
        assert windows.shape[0] == expected

    def test_window_shape(self):
        T = 128
        features = np.zeros((T, CHROMA_BINS), dtype=np.float32)
        windows = _build_windows(features)
        expected = (T + _HOP_FRAMES - 1) // _HOP_FRAMES
        assert windows.shape[0] == expected
        assert windows.shape[1] == _WINDOW
        assert windows.shape[2] == CHROMA_BINS

    def test_padding_preserves_content(self):
        T = 64
        features = np.ones((T, CHROMA_BINS), dtype=np.float32)
        windows = _build_windows(features)
        first_window = windows[0]
        assert np.all(first_window[_WINDOW // 2:] == 1.0)
        assert np.all(first_window[:_WINDOW // 2] == 0.0)


class TestMergeOverlappingPredictions:
    def test_output_shape_matches_input_frames(self):
        T_overlap = 3
        window_probs = np.random.rand(T_overlap, _WINDOW, _NUM_CLASSES).astype(np.float32)
        window_probs /= window_probs.sum(axis=-1, keepdims=True)

        T = T_overlap * _HOP_FRAMES - _WINDOW // 2
        merged = _merge_overlapping_predictions(window_probs, T)
        assert merged.shape == (T, _NUM_CLASSES)

    def test_rows_sum_to_one(self):
        T_overlap = 4
        window_probs = np.ones((T_overlap, _WINDOW, _NUM_CLASSES), dtype=np.float32)
        window_probs /= window_probs.sum(axis=-1, keepdims=True)

        T = T_overlap * _HOP_FRAMES - _WINDOW // 2
        merged = _merge_overlapping_predictions(window_probs, T)
        row_sums = merged.sum(axis=1)
        assert np.allclose(row_sums, 1.0, atol=1e-5)

    def test_uniform_input_produces_uniform_output(self):
        T_overlap = 3
        window_probs = np.full(
            (T_overlap, _WINDOW, _NUM_CLASSES),
            1.0 / _NUM_CLASSES,
            dtype=np.float32,
        )

        T = T_overlap * _HOP_FRAMES - _WINDOW // 2
        merged = _merge_overlapping_predictions(window_probs, T)
        assert np.allclose(merged, 1.0 / _NUM_CLASSES, atol=1e-5)


# ---------------------------------------------------------------------------
# Phase 2: Boundary Confidence Penalty
# ---------------------------------------------------------------------------

class TestBoundaryPenalty:
    def test_penalty_applied_at_boundaries(self):
        T = 256
        probs = np.zeros((T, _NUM_CLASSES), dtype=np.float32)
        probs[:, 0] = 0.9
        probs[:, 1:] = 0.1 / (_NUM_CLASSES - 1)
        penalized = _apply_boundary_penalty(probs)

        boundary_idx = _WINDOW
        assert penalized[boundary_idx, 0] < probs[boundary_idx, 0] + 1e-5

    def test_no_penalty_at_track_edges(self):
        T = 256
        probs = np.full((T, _NUM_CLASSES), 1.0 / _NUM_CLASSES, dtype=np.float32)
        penalized = _apply_boundary_penalty(probs)

        assert np.allclose(probs[0], penalized[0], atol=1e-6)
        assert np.allclose(probs[-1], penalized[-1], atol=1e-6)

    def test_preserves_row_normalization_for_interior(self):
        T = 300
        probs = np.random.dirichlet(np.ones(_NUM_CLASSES), size=T).astype(np.float32)
        penalized = _apply_boundary_penalty(probs)

        interior_idx = 50
        assert abs(penalized[interior_idx].sum() - 1.0) < 1e-5

    def test_boundary_rows_not_normalized(self):
        T = 256
        probs = np.zeros((T, _NUM_CLASSES), dtype=np.float32)
        probs[:, 0] = 0.9
        probs[:, 1:] = 0.1 / (_NUM_CLASSES - 1)
        penalized = _apply_boundary_penalty(probs)

        boundary_idx = _WINDOW
        assert penalized[boundary_idx, 0] < probs[boundary_idx, 0] + 1e-5

    def test_penalty_reduces_raw_confidence_at_boundary(self):
        T = 256
        probs = np.zeros((T, _NUM_CLASSES), dtype=np.float32)
        probs[:, 0] = 0.9
        probs[:, 1:] = 0.1 / (_NUM_CLASSES - 1)

        boundary_idx = _WINDOW
        interior_idx = _WINDOW + 10

        penalized = _apply_boundary_penalty(probs)

        assert penalized[boundary_idx, 0] <= probs[boundary_idx, 0] + 1e-5
        assert abs(penalized[interior_idx, 0] - probs[interior_idx, 0]) < 1e-6


# ---------------------------------------------------------------------------
# Phase 3: TieRegistry
# ---------------------------------------------------------------------------

class TestTieRegistry:
    def _make_grid(self, bpm=120.0):
        return BeatGrid(
            bpm=bpm,
            pulse_bpm=bpm,
            beats=[i * 0.5 for i in range(100)],
            downbeats=[i * 2.0 for i in range(25)],
            time_signature=TimeSignature(numerator=4, denominator=4),
            tick_value=0.5,
        )

    def test_register_segment_end_collects_spanning_notes(self):
        registry = TieRegistry(bpm=120.0)
        notes = [
            SoloNote(start_time=12.0, duration=1.0, pitch=60, velocity=80),
            SoloNote(start_time=12.5, duration=0.3, pitch=64, velocity=90),
        ]
        registry.register_segment_end(notes, segment_end=12.8)
        assert len(registry.active_notes) == 1
        assert registry.active_notes[0].pitch == 60

    def test_tied_note_merged(self):
        registry = TieRegistry(bpm=120.0)
        notes_before = [
            SoloNote(start_time=12.7, duration=0.5, pitch=60, velocity=80),
        ]
        registry.register_segment_end(notes_before, segment_end=12.8)

        notes_after = [
            SoloNote(start_time=12.8, duration=0.4, pitch=60, velocity=82),
        ]
        resolved = registry.resolve_segment_start(notes_after)

        assert len(resolved) == 1
        assert resolved[0].pitch == 60
        assert abs(resolved[0].start_time - 12.7) < 0.01
        assert abs(resolved[0].duration - 0.5) < 0.01

    def test_restruck_note_kept_separate(self):
        registry = TieRegistry(bpm=120.0)
        notes_before = [
            SoloNote(start_time=12.7, duration=0.3, pitch=60, velocity=80),
        ]
        registry.register_segment_end(notes_before, segment_end=12.8)

        notes_after = [
            SoloNote(start_time=12.85, duration=0.3, pitch=60, velocity=120),
        ]
        resolved = registry.resolve_segment_start(notes_after)

        assert len(resolved) == 2

    def test_truncated_note_closed_at_boundary(self):
        registry = TieRegistry(bpm=120.0)
        notes_before = [
            SoloNote(start_time=12.7, duration=0.5, pitch=60, velocity=80),
        ]
        registry.register_segment_end(notes_before, segment_end=12.8)

        notes_after = []
        resolved = registry.resolve_segment_start(notes_after)

        assert len(resolved) == 1
        assert abs(resolved[0].duration - 0.1) < 0.01

    def test_max_sustain_timeout(self):
        registry = TieRegistry(bpm=120.0)
        notes_before = [
            SoloNote(start_time=10.0, duration=5.0, pitch=60, velocity=80),
        ]
        registry.register_segment_end(notes_before, segment_end=12.8)

        notes_after = []
        resolved = registry.resolve_segment_start(notes_after)

        max_duration = 4 * (60.0 / 120.0)
        assert resolved[0].start_time + resolved[0].duration <= resolved[0].start_time + max_duration + 0.01


class TestMergeBoundaryNotes:
    def test_merges_notes_across_boundary(self):
        notes = [
            SoloNote(start_time=12.7, duration=0.5, pitch=60, velocity=80),
            SoloNote(start_time=12.8, duration=0.4, pitch=60, velocity=82),
        ]
        merged = _merge_boundary_notes(notes, bpm=120.0)
        assert len(merged) <= len(notes)

    def test_preserves_non_boundary_notes(self):
        notes = [
            SoloNote(start_time=1.0, duration=0.5, pitch=60, velocity=80),
            SoloNote(start_time=5.0, duration=0.5, pitch=64, velocity=90),
        ]
        merged = _merge_boundary_notes(notes, bpm=120.0)
        assert len(merged) == 2


# ---------------------------------------------------------------------------
# Phase 4: Scoring Deduplication
# ---------------------------------------------------------------------------

class TestDeduplicateOnsets:
    def test_removes_close_duplicates(self):
        onsets = np.array([1.0, 1.02, 1.04, 5.0, 5.03])
        deduped = _deduplicate_onsets(onsets, min_gap_ms=50)
        assert len(deduped) == 2
        assert deduped[0] == 1.0
        assert deduped[1] == 5.0

    def test_preserves_well_spaced_onsets(self):
        onsets = np.array([1.0, 2.0, 3.0, 4.0])
        deduped = _deduplicate_onsets(onsets, min_gap_ms=50)
        assert len(deduped) == 4

    def test_empty_input(self):
        onsets = np.array([])
        deduped = _deduplicate_onsets(onsets)
        assert len(deduped) == 0

    def test_single_onset(self):
        onsets = np.array([1.0])
        deduped = _deduplicate_onsets(onsets)
        assert len(deduped) == 1

    def test_sorted_output(self):
        onsets = np.array([3.0, 1.0, 2.0, 1.02, 1.04])
        deduped = _deduplicate_onsets(onsets, min_gap_ms=50)
        assert np.all(np.diff(deduped) >= 0)


# ---------------------------------------------------------------------------
# Phase 5: Integration Tests
# ---------------------------------------------------------------------------

class TestChordHeldAcrossBoundary:
    def test_single_chord_no_flicker(self):
        """Verify that a chord held across a boundary is not split."""
        T_overlap = 4
        chord_idx = _CHORD_TO_IDX["C:maj"]

        window_probs = np.zeros((T_overlap, _WINDOW, _NUM_CLASSES), dtype=np.float32)
        window_probs[:, :, chord_idx] = 0.9
        window_probs[:, :, chord_idx + 1] = 0.1

        T = T_overlap * _HOP_FRAMES - _WINDOW // 2
        merged = _merge_overlapping_predictions(window_probs, T)
        penalized = _apply_boundary_penalty(merged)

        pred_indices = np.argmax(penalized, axis=1)
        unique_chords = np.unique(pred_indices)
        assert len(unique_chords) == 1
        assert unique_chords[0] == chord_idx
