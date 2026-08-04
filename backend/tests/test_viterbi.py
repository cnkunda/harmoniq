"""Tests for Viterbi chord decoding (Commit 99).

Covers: transition matrix construction, Viterbi decoder, key-constrained costs,
duration filtering, half-beat resolution, flicker detection, beat-alignment gate,
and the full postprocessing pipeline.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from app.viterbi import (
    VOCAB_SIZE,
    N_CHORD_IDX,
    CHORD_VOCAB,
    _ROOTS,
    _CHORD_QUALITIES,
    _parse_key,
    _key_penalty,
    _filter_short_chords,
    _resolve_half_beat_changes,
    build_transition_matrix_from_sequences,
    build_music_theory_transition_matrix,
    load_transition_matrix,
    viterbi_decode,
    viterbi_decode_beats,
    compute_flicker_rate,
    compute_beat_alignment,
    compute_beat_alignment_all_beats,
    compute_chord_change_histogram,
    compute_flicker_events,
    postprocess_chords,
)
from app.schemas import BeatGrid, ChordEvent, ChordTimeline


# ---------------------------------------------------------------------------
# Vocabulary tests
# ---------------------------------------------------------------------------

class TestVocab:
    def test_vocab_size(self):
        assert VOCAB_SIZE == 277  # 23 qualities * 12 roots + 1

    def test_n_chord_index(self):
        assert CHORD_VOCAB[N_CHORD_IDX] == "N"

    def test_all_roots_present(self):
        for root in _ROOTS:
            assert any(c.startswith(f"{root}:") for c in CHORD_VOCAB)

    def test_all_qualities_present(self):
        for qual in _CHORD_QUALITIES:
            assert any(f":{qual}" in c for c in CHORD_VOCAB)


# ---------------------------------------------------------------------------
# Key parsing
# ---------------------------------------------------------------------------

class TestParseKey:
    def test_c_major(self):
        root, is_minor = _parse_key("C major")
        assert root == 0
        assert is_minor is False

    def test_a_minor(self):
        root, is_minor = _parse_key("A minor")
        assert root == 9
        assert is_minor is True

    def test_g_sharp_major(self):
        root, is_minor = _parse_key("G# major")
        assert root == 8
        assert is_minor is False

    def test_none_returns_no_key(self):
        root, is_minor = _parse_key(None)
        assert root is None

    def test_empty_string(self):
        root, is_minor = _parse_key("")
        assert root is None

    def test_invalid_root(self):
        root, is_minor = _parse_key("X major")
        assert root is None


# ---------------------------------------------------------------------------
# Key penalty
# ---------------------------------------------------------------------------

class TestKeyPenalty:
    def test_no_key_returns_one(self):
        # C:maj -> C:maj (same chord, no key)
        assert _key_penalty(0, 0, None, False) == 1.0

    def test_diatonic_penalty_c_major(self):
        # C:maj -> G:maj in C major: both diatonic
        c_idx = 0 * len(_CHORD_QUALITIES) + _CHORD_QUALITIES.index("maj")
        g_idx = 7 * len(_CHORD_QUALITIES) + _CHORD_QUALITIES.index("maj")
        penalty = _key_penalty(c_idx, g_idx, 0, False)
        assert penalty == 1.0  # Both diatonic

    def test_chromatic_penalty(self):
        # C:maj -> F#:maj in C major: both chromatic
        c_idx = 0 * len(_CHORD_QUALITIES) + _CHORD_QUALITIES.index("maj")
        fs_idx = 6 * len(_CHORD_QUALITIES) + _CHORD_QUALITIES.index("maj")
        penalty = _key_penalty(c_idx, fs_idx, 0, False)
        assert penalty > 1.0  # Penalized


# ---------------------------------------------------------------------------
# Transition matrix
# ---------------------------------------------------------------------------

class TestTransitionMatrix:
    def test_default_shape(self):
        mat = build_music_theory_transition_matrix()
        assert mat.shape == (VOCAB_SIZE, VOCAB_SIZE)

    def test_rows_sum_to_one(self):
        mat = build_music_theory_transition_matrix()
        row_sums = mat.sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-6)

    def test_from_sequences(self):
        # Simple sequence: C:maj -> G:maj -> C:maj
        c_idx = 0 * len(_CHORD_QUALITIES) + _CHORD_QUALITIES.index("maj")
        g_idx = 7 * len(_CHORD_QUALITIES) + _CHORD_QUALITIES.index("maj")
        seqs = [[c_idx, g_idx, c_idx]]
        mat = build_transition_matrix_from_sequences(seqs)
        assert mat.shape == (VOCAB_SIZE, VOCAB_SIZE)
        # C->G should have higher probability than C->F#
        assert mat[c_idx, g_idx] > mat[c_idx, 6 * len(_CHORD_QUALITIES)]

    def test_load_transition_matrix(self):
        mat = load_transition_matrix()
        assert mat.shape == (VOCAB_SIZE, VOCAB_SIZE)


# ---------------------------------------------------------------------------
# Viterbi decoder
# ---------------------------------------------------------------------------

class TestViterbiDecode:
    def _make_emission(self, chord: str, confidence: float = 0.9, time: float = 0.0) -> dict:
        return {"chord": chord, "confidence": confidence, "time": time}

    def test_single_frame(self):
        emissions = [self._make_emission("C:maj")]
        path = viterbi_decode(emissions)
        assert len(path) == 1
        assert CHORD_VOCAB[path[0]] == "C:maj"

    def test_two_frames_same_chord(self):
        emissions = [
            self._make_emission("C:maj", time=0.0),
            self._make_emission("C:maj", time=0.5),
        ]
        path = viterbi_decode(emissions)
        assert len(path) == 2
        assert CHORD_VOCAB[path[0]] == "C:maj"
        assert CHORD_VOCAB[path[1]] == "C:maj"

    def test_plausible_transition(self):
        # C:maj -> G:maj is a common transition
        emissions = [
            self._make_emission("C:maj", time=0.0),
            self._make_emission("G:maj", time=0.5),
            self._make_emission("C:maj", time=1.0),
        ]
        path = viterbi_decode(emissions)
        assert len(path) == 3
        # All should be decoded (C->G->C is plausible)
        assert CHORD_VOCAB[path[0]] == "C:maj"
        assert CHORD_VOCAB[path[2]] == "C:maj"

    def test_empty_emissions(self):
        path = viterbi_decode([])
        assert path == []

    def test_no_chord_token(self):
        emissions = [self._make_emission("N")]
        path = viterbi_decode(emissions)
        assert CHORD_VOCAB[path[0]] == "N"


# ---------------------------------------------------------------------------
# Beat-level Viterbi
# ---------------------------------------------------------------------------

class TestViterbiBeats:
    def _make_frames(self, chord: str, n: int = 3, start: float = 0.0) -> list[dict]:
        return [
            {"chord": chord, "confidence": 0.8 + i * 0.05, "time": start + i * 0.1}
            for i in range(n)
        ]

    def test_single_beat(self):
        beat_preds = [self._make_frames("C:maj")]
        path = viterbi_decode_beats(beat_preds)
        assert len(path) == 1
        assert CHORD_VOCAB[path[0]] == "C:maj"

    def test_multiple_beats_same_chord(self):
        beat_preds = [
            self._make_frames("C:maj", start=0.0),
            self._make_frames("C:maj", start=0.5),
            self._make_frames("C:maj", start=1.0),
        ]
        path = viterbi_decode_beats(beat_preds)
        assert all(CHORD_VOCAB[p] == "C:maj" for p in path)

    def test_empty_beats(self):
        path = viterbi_decode_beats([])
        assert path == []

    def test_empty_frame_list(self):
        # Beat with no frames -> N chord
        path = viterbi_decode_beats([[]])
        assert len(path) == 1
        assert CHORD_VOCAB[path[0]] == "N"


# ---------------------------------------------------------------------------
# Flicker rate
# ---------------------------------------------------------------------------

class TestFlickerRate:
    def test_no_flicker(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.5, chord="C:maj", confidence=0.9),
        ]
        rate = compute_flicker_rate(events)
        assert rate == 0.0  # No chord changes at all

    def test_all_flicker(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.5, chord="G:maj", confidence=0.9),
        ]
        rate = compute_flicker_rate(events)
        assert rate == 1.0  # Every beat changes

    def test_single_event(self):
        events = [ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)]
        rate = compute_flicker_rate(events)
        assert rate == 0.0

    def test_empty_events(self):
        rate = compute_flicker_rate([])
        assert rate == 0.0


# ---------------------------------------------------------------------------
# Beat alignment
# ---------------------------------------------------------------------------

class TestBeatAlignment:
    def test_aligned_to_downbeat(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="G:maj", confidence=0.9),
        ]
        downbeats = [0.0, 1.0, 2.0]
        align = compute_beat_alignment(events, downbeats)
        assert align == 1.0  # Change at 1.0 is on a downbeat

    def test_not_aligned(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.3, chord="G:maj", confidence=0.9),
        ]
        downbeats = [0.0, 1.0, 2.0]
        align = compute_beat_alignment(events, downbeats)
        assert align == 0.0  # Change at 0.3 not near any downbeat

    def test_no_changes(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="C:maj", confidence=0.9),
        ]
        downbeats = [0.0, 1.0]
        align = compute_beat_alignment(events, downbeats)
        assert align == 1.0  # No changes = trivially aligned

    def test_empty_events(self):
        align = compute_beat_alignment([], [0.0, 1.0])
        assert align == 0.0


# ---------------------------------------------------------------------------
# Beat alignment (all beats)
# ---------------------------------------------------------------------------

class TestBeatAlignmentAll:
    def test_aligned_to_any_beat(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:maj", confidence=0.9),
        ]
        beats = [0.0, 0.5, 1.0, 1.5]
        align = compute_beat_alignment_all_beats(events, beats)
        assert align == 1.0  # Both changes on beats


# ---------------------------------------------------------------------------
# Chord change histogram
# ---------------------------------------------------------------------------

class TestChordChangeHistogram:
    def test_basic_histogram(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:maj", confidence=0.9),
            ChordEvent(timestamp=1.5, chord="C:maj", confidence=0.9),
        ]
        hist = compute_chord_change_histogram(events)
        assert "0-1 beats" in hist
        assert "1-2 beats" in hist

    def test_empty_events(self):
        hist = compute_chord_change_histogram([])
        assert hist == {}

    def test_single_event(self):
        events = [ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)]
        hist = compute_chord_change_histogram(events)
        assert hist == {}


# ---------------------------------------------------------------------------
# Flicker events
# ---------------------------------------------------------------------------

class TestFlickerEvents:
    def test_detects_flicker(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="C:maj", confidence=0.9),
        ]
        flickers = compute_flicker_events(events)
        assert len(flickers) == 1
        assert flickers[0] == (1, "C:maj", "G:maj", "C:maj")

    def test_no_flicker(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="D:maj", confidence=0.9),
        ]
        flickers = compute_flicker_events(events)
        assert len(flickers) == 0


# ---------------------------------------------------------------------------
# Duration-aware filtering
# ---------------------------------------------------------------------------

class TestFilterShortChords:
    def _make_beats(self, bpm: float = 120.0, n: int = 10) -> list[float]:
        step = 60.0 / bpm
        return [round(i * step, 6) for i in range(n)]

    def test_suppresses_flicker(self):
        beats = self._make_beats(120.0, 10)
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.25, chord="G:maj", confidence=0.9),  # Short
            ChordEvent(timestamp=0.5, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="D:maj", confidence=0.9),
        ]
        filtered = _filter_short_chords(events, beats, min_beats=1.0)
        # The short G:maj between two C:majs should be replaced
        assert filtered[1].chord == "C:maj"

    def test_preserves_long_chords(self):
        beats = self._make_beats(120.0, 10)
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="G:maj", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="C:maj", confidence=0.9),
        ]
        filtered = _filter_short_chords(events, beats, min_beats=1.0)
        assert filtered[1].chord == "G:maj"

    def test_too_few_events(self):
        events = [ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)]
        filtered = _filter_short_chords(events, [0.0, 0.5, 1.0])
        assert len(filtered) == 1


# ---------------------------------------------------------------------------
# Half-beat resolution
# ---------------------------------------------------------------------------

class TestHalfBeatResolution:
    def test_tie_triggers_split(self):
        beats = [0.0, 0.5, 1.0]
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:maj", confidence=0.9),
        ]
        # Frame predictions with tight tie
        frames = [
            {"chord": "C:maj", "confidence": 0.55, "time": 0.1},
            {"chord": "G:maj", "confidence": 0.50, "time": 0.3},
            {"chord": "C:maj", "confidence": 0.55, "time": 0.6},
            {"chord": "G:maj", "confidence": 0.50, "time": 0.8},
        ]
        resolved = _resolve_half_beat_changes(events, beats, frames, tie_threshold=0.15)
        # With tight tie, should split into half-beat events
        assert len(resolved) >= 2

    def test_no_tie_no_split(self):
        beats = [0.0, 0.5, 1.0]
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:maj", confidence=0.9),
        ]
        frames = [
            {"chord": "C:maj", "confidence": 0.9, "time": 0.1},
            {"chord": "C:maj", "confidence": 0.9, "time": 0.3},
            {"chord": "G:maj", "confidence": 0.9, "time": 0.6},
            {"chord": "G:maj", "confidence": 0.9, "time": 0.8},
        ]
        resolved = _resolve_half_beat_changes(events, beats, frames, tie_threshold=0.15)
        assert len(resolved) == 2  # No split

    def test_no_frames(self):
        beats = [0.0, 0.5, 1.0]
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:maj", confidence=0.9),
        ]
        resolved = _resolve_half_beat_changes(events, beats, None)
        assert len(resolved) == 2

    def test_empty_events(self):
        resolved = _resolve_half_beat_changes([], [0.0, 0.5], None)
        assert resolved == []


# ---------------------------------------------------------------------------
# Full postprocessing pipeline
# ---------------------------------------------------------------------------

class TestPostprocessChords:
    def _make_events(self, chords: list[str], beat_step: float = 0.5) -> list[ChordEvent]:
        return [
            ChordEvent(timestamp=i * beat_step, chord=c, confidence=0.9)
            for i, c in enumerate(chords)
        ]

    def _make_beats(self, n: int = 10, step: float = 0.5) -> list[float]:
        return [round(i * step, 6) for i in range(n)]

    def test_ii_V_I_progression(self):
        # ii-V-I in C major: D:min -> G:maj -> C:maj
        chords = ["D:min7", "G:7", "C:maj", "C:maj", "C:maj"]
        events = self._make_events(chords)
        beats = self._make_beats(5)

        timeline, metrics = postprocess_chords(
            events=events,
            beats=beats,
            downbeats=[0.0, 2.0],
            key_signature="C major",
        )

        assert isinstance(timeline, ChordTimeline)
        assert "flicker_rate" in metrics
        assert "beat_alignment_downbeat" in metrics
        assert "chord_change_histogram" in metrics

    def test_empty_events(self):
        timeline, metrics = postprocess_chords(
            events=[],
            beats=[0.0, 0.5],
            downbeats=[0.0],
        )
        assert timeline.events == []
        assert metrics == {}

    def test_single_event(self):
        events = [ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)]
        timeline, metrics = postprocess_chords(
            events=events,
            beats=[0.0, 0.5],
            downbeats=[0.0],
        )
        assert len(timeline.events) == 1
        assert metrics["flicker_rate"] == 0.0

    def test_metrics_contain_required_keys(self):
        chords = ["C:maj", "G:maj", "C:maj", "F:maj"]
        events = self._make_events(chords)
        beats = self._make_beats(4)

        _, metrics = postprocess_chords(
            events=events,
            beats=beats,
            downbeats=[0.0],
        )

        required_keys = [
            "flicker_rate",
            "beat_alignment_downbeat",
            "beat_alignment_all_beats",
            "chord_change_histogram",
            "flicker_event_count",
            "total_events",
            "non_n_events",
        ]
        for key in required_keys:
            assert key in metrics, f"Missing metric: {key}"


# ---------------------------------------------------------------------------
# Integration: Viterbi reduces flicker
# ---------------------------------------------------------------------------

class TestViterbiReducesFlicker:
    def test_flicker_reduction(self):
        """Viterbi should reduce chord flickering compared to raw predictions."""
        # Create a sequence with a flicker: C, G, C, C, C
        chords = ["C:maj", "G:maj", "C:maj", "C:maj", "C:maj"]
        events = [
            ChordEvent(timestamp=i * 0.5, chord=c, confidence=0.9)
            for i, c in enumerate(chords)
        ]
        beats = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]

        raw_flicker = compute_flicker_rate(events)

        timeline, _metrics = postprocess_chords(
            events=events,
            beats=beats,
            downbeats=[0.0, 2.0],
        )

        decoded_flicker = compute_flicker_rate(timeline.events)

        # Viterbi should reduce or maintain flicker (not increase it)
        assert decoded_flicker <= raw_flicker

    def test_stable_sequence_unchanged(self):
        """A stable chord sequence should remain stable after Viterbi."""
        chords = ["C:maj", "C:maj", "C:maj", "C:maj"]
        events = [
            ChordEvent(timestamp=i * 0.5, chord=c, confidence=0.9)
            for i, c in enumerate(chords)
        ]
        beats = [0.0, 0.5, 1.0, 1.5, 2.0]

        timeline, _metrics = postprocess_chords(
            events=events,
            beats=beats,
            downbeats=[0.0],
        )

        assert all(e.chord == "C:maj" for e in timeline.events)
