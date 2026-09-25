"""Tests for Commit 99: Chord quality metrics computation."""

from __future__ import annotations

import numpy as np
import pytest

from app.chord_metrics import (
    assemble_chord_metrics,
    compute_beat_alignment,
    compute_chord_change_histogram,
    compute_duration_filtering_stats,
    compute_flicker_rate,
)
from app.schemas import BeatGrid, ChordEvent


@pytest.fixture
def simple_grid():
    return BeatGrid(
        bpm=120.0,
        beats=[i * 0.5 for i in range(9)],
        downbeats=[0.0, 2.0, 4.0],
        time_signature={"numerator": 4, "denominator": 4},
        tick_value=0.25,
    )


@pytest.fixture
def chord_events_simple():
    return [
        ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ChordEvent(timestamp=0.5, chord="C:maj", confidence=0.9),
        ChordEvent(timestamp=1.0, chord="C:maj", confidence=0.9),
        ChordEvent(timestamp=1.5, chord="G:maj", confidence=0.8),
        ChordEvent(timestamp=2.0, chord="G:maj", confidence=0.8),
        ChordEvent(timestamp=2.5, chord="G:maj", confidence=0.8),
        ChordEvent(timestamp=3.0, chord="C:maj", confidence=0.9),
        ChordEvent(timestamp=3.5, chord="C:maj", confidence=0.9),
        ChordEvent(timestamp=4.0, chord="C:maj", confidence=0.9),
    ]


class TestFlickerRate:
    def test_no_flicker(self, chord_events_simple):
        rate = compute_flicker_rate(chord_events_simple)
        assert rate == 0.0

    def test_single_flicker(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=1.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.5, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="C:maj", confidence=0.9),
        ]
        rate = compute_flicker_rate(events)
        assert rate > 0.0

    def test_all_flicker(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=1.0, chord="F:maj", confidence=0.7),
            ChordEvent(timestamp=1.5, chord="D:min", confidence=0.6),
            ChordEvent(timestamp=2.0, chord="A:min", confidence=0.5),
        ]
        rate = compute_flicker_rate(events)
        assert rate == 1.0

    def test_n_chords_excluded(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="N", confidence=1.0),
            ChordEvent(timestamp=1.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.5, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="C:maj", confidence=0.9),
        ]
        rate = compute_flicker_rate(events)
        assert rate == 0.0

    def test_fewer_than_3_events(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:maj", confidence=0.8),
        ]
        assert compute_flicker_rate(events) == 0.0


class TestBeatAlignment:
    def test_all_changes_on_beats(self, chord_events_simple, simple_grid):
        alignment = compute_beat_alignment(chord_events_simple, simple_grid, measure="any")
        assert alignment == 1.0

    def test_downbeat_only_alignment(self, simple_grid):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=4.0, chord="C:maj", confidence=0.9),
        ]
        alignment = compute_beat_alignment(events, simple_grid, measure="downbeat")
        assert alignment == 1.0

    def test_off_beat_change(self, simple_grid):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.25, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=1.0, chord="C:maj", confidence=0.9),
        ]
        alignment = compute_beat_alignment(events, simple_grid, measure="any")
        assert alignment < 1.0

    def test_no_changes(self, simple_grid):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="C:maj", confidence=0.9),
        ]
        alignment = compute_beat_alignment(events, simple_grid, measure="any")
        assert alignment == 1.0

    def test_empty_beat_grid(self):
        grid = BeatGrid(
            bpm=120.0,
            beats=[],
            downbeats=[],
            time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="G:maj", confidence=0.8),
        ]
        alignment = compute_beat_alignment(events, grid, measure="any")
        assert alignment == 1.0


class TestChordChangeHistogram:
    def test_regular_changes(self, simple_grid):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=4.0, chord="C:maj", confidence=0.9),
        ]
        hist = compute_chord_change_histogram(events, simple_grid)
        assert hist["total_changes"] == 2
        assert hist["bins"] == ["<0.5", "0.5-1", "1-2", "2-4", "4+"]
        assert len(hist["counts"]) == 5

    def test_few_changes(self, simple_grid):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:maj", confidence=0.8),
        ]
        hist = compute_chord_change_histogram(events, simple_grid)
        assert hist["total_changes"] == 1
        assert hist["counts"] == [0, 0, 0, 0, 0]

    def test_flicker_pct_calculation(self, simple_grid):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.1, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=0.2, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.3, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=1.0, chord="C:maj", confidence=0.9),
        ]
        hist = compute_chord_change_histogram(events, simple_grid)
        assert hist["flicker_pct"] > 0


class TestDurationFiltering:
    def test_identifies_sub_beat_events(self, simple_grid):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.25, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=0.5, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.5, chord="C:maj", confidence=0.9),
        ]
        stats = compute_duration_filtering_stats(events, simple_grid)
        assert stats["sub_beat_count"] >= 1
        assert stats["total_chord_events"] > 0

    def test_no_sub_beat_events(self, simple_grid):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=1.5, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=2.0, chord="C:maj", confidence=0.9),
        ]
        stats = compute_duration_filtering_stats(events, simple_grid)
        assert stats["sub_beat_count"] == 0

    def test_n_chords_excluded(self, simple_grid):
        events = [
            ChordEvent(timestamp=0.0, chord="N", confidence=1.0),
            ChordEvent(timestamp=0.25, chord="N", confidence=1.0),
            ChordEvent(timestamp=0.5, chord="C:maj", confidence=0.9),
        ]
        stats = compute_duration_filtering_stats(events, simple_grid)
        assert stats["sub_beat_count"] == 0


class TestAssembly:
    def test_all_fields_present(self, chord_events_simple, simple_grid):
        metadata = assemble_chord_metrics(chord_events_simple, simple_grid)
        required_keys = {
            "flicker_rate",
            "beat_alignment_pct",
            "downbeat_alignment_pct",
            "chord_change_histogram",
            "duration_filtering",
            "total_events",
            "unique_chords",
        }
        assert required_keys.issubset(metadata.keys())

    def test_unique_chords_count(self, simple_grid):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="G:maj", confidence=0.8),
            ChordEvent(timestamp=2.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=3.0, chord="N", confidence=1.0),
        ]
        metadata = assemble_chord_metrics(events, simple_grid)
        assert metadata["unique_chords"] == 2

    def test_total_events_count(self, chord_events_simple, simple_grid):
        metadata = assemble_chord_metrics(chord_events_simple, simple_grid)
        assert metadata["total_events"] == len(chord_events_simple)
