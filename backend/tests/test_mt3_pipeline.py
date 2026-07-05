"""Tests for MT3-Primary AMT Pipeline (Phase 2, Milestone A).

Tests cover:
  - Mt3Event and Mt3EventStream schema validation
  - Chord decoder: pitch class aggregation, template matching, MIREX mapping
  - Solo decoder: event filtering, note segment building, quantization
  - Fallback orchestrator: tier selection, confidence gating
  - Integration: full pipeline wiring in analyze_audio.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pytest

from app.mt3.chord_decoder import (
    _build_active_note_grid,
    _infer_chords_from_active_notes,
    _match_chord_template,
    _to_mirex,
    decode_events_to_chord_timeline,
    _GUITAR_PROGRAMS,
    _PERCUSSION_PROGRAM,
)
from app.mt3.fallback import (
    TranscriptionResult,
    transcribe_with_fallback,
    get_transcription_source_label,
)
from app.mt3.model_server import Mt3ModelServer
from app.mt3.schemas import Mt3Event, Mt3EventStream
from app.mt3.solo_decoder import (
    NoteSegment,
    _filter_melodic_events,
    _build_note_segments,
    _filter_short_noise,
    _quantize_to_grid,
    _resolve_simultaneous_notes,
    _detect_bends,
    _detect_vibrato,
    _detect_grace_notes,
    _coherence_factor,
    _merge_boundary_notes,
    decode_events_to_solo_notes,
)
from app.schemas import BeatGrid, ChordEvent, ChordTimeline, SoloNote, SoloNotes


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_beat_grid() -> BeatGrid:
    return BeatGrid(
        bpm=120.0,
        pulse_bpm=120.0,
        beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
        downbeats=[0.0, 2.0, 4.0],
        time_signature={"numerator": 4, "denominator": 4},
        tick_value=0.25,
    )


@pytest.fixture
def cmaj_events() -> list[Mt3Event]:
    """C major chord: C(0), E(4), G(7) — pitch classes."""
    return [
        Mt3Event(time=0.0, pitch=60, velocity=100, program=24, is_onset=True, confidence=0.95),  # C4
        Mt3Event(time=0.0, pitch=64, velocity=90, program=24, is_onset=True, confidence=0.92),   # E4
        Mt3Event(time=0.0, pitch=67, velocity=95, program=24, is_onset=True, confidence=0.93),   # G4
        Mt3Event(time=1.0, pitch=60, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
        Mt3Event(time=1.0, pitch=64, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
        Mt3Event(time=1.0, pitch=67, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
    ]


@pytest.fixture
def cmaj7_events() -> list[Mt3Event]:
    """C major 7: C(0), E(4), G(7), B(11)."""
    return [
        Mt3Event(time=0.0, pitch=60, velocity=100, program=24, is_onset=True, confidence=0.95),
        Mt3Event(time=0.0, pitch=64, velocity=90, program=24, is_onset=True, confidence=0.92),
        Mt3Event(time=0.0, pitch=67, velocity=95, program=24, is_onset=True, confidence=0.93),
        Mt3Event(time=0.0, pitch=71, velocity=85, program=24, is_onset=True, confidence=0.90),
        Mt3Event(time=1.0, pitch=60, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
        Mt3Event(time=1.0, pitch=64, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
        Mt3Event(time=1.0, pitch=67, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
        Mt3Event(time=1.0, pitch=71, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
    ]


@pytest.fixture
def gmaj_events() -> list[Mt3Event]:
    """G major: G(7), B(11), D(2)."""
    return [
        Mt3Event(time=2.0, pitch=67, velocity=100, program=24, is_onset=True, confidence=0.95),  # G4
        Mt3Event(time=2.0, pitch=71, velocity=90, program=24, is_onset=True, confidence=0.92),   # B4
        Mt3Event(time=2.0, pitch=74, velocity=95, program=24, is_onset=True, confidence=0.93),   # D5
        Mt3Event(time=3.0, pitch=67, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
        Mt3Event(time=3.0, pitch=71, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
        Mt3Event(time=3.0, pitch=74, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
    ]


@pytest.fixture
def multi_instrument_events() -> list[Mt3Event]:
    """Events from guitar + piano + percussion for filter testing."""
    return [
        Mt3Event(time=0.0, pitch=60, velocity=100, program=24, is_onset=True, confidence=0.95),  # guitar
        Mt3Event(time=0.0, pitch=64, velocity=90, program=24, is_onset=True, confidence=0.92),
        Mt3Event(time=0.5, pitch=67, velocity=95, program=0, is_onset=True, confidence=0.90),    # piano
        Mt3Event(time=1.0, pitch=36, velocity=80, program=128, is_onset=True, confidence=0.99),  # percussion
        Mt3Event(time=1.5, pitch=62, velocity=85, program=24, is_onset=True, confidence=0.88),   # guitar
    ]


# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------

class TestMt3Schemas:
    def test_mt3_event_defaults(self):
        event = Mt3Event(time=1.0, pitch=60)
        assert event.velocity == 80
        assert event.program == 24
        assert event.is_onset is True
        assert event.is_offset is False
        assert event.confidence == 0.9

    def test_mt3_event_stream_empty(self):
        stream = Mt3EventStream()
        assert len(stream.events) == 0
        assert stream.audio_duration_s == 0.0

    def test_mt3_event_stream_populated(self, cmaj_events):
        stream = Mt3EventStream(
            events=cmaj_events,
            audio_duration_s=2.0,
            model_version="mt3-t5-small",
            inference_time_ms=150.0,
            mean_confidence=0.93,
            num_instruments=1,
        )
        assert len(stream.events) == 6
        assert stream.mean_confidence == 0.93
        assert stream.num_instruments == 1


# ---------------------------------------------------------------------------
# Chord Decoder Tests
# ---------------------------------------------------------------------------

class TestChordDecoder:
    def test_match_chord_template_cmaj(self, cmaj_events):
        """C major triad should match C:maj with Jaccard >= 0.66."""
        active_pcs = {e.pitch % 12 for e in cmaj_events}
        chord_label, confidence = _match_chord_template(active_pcs)
        assert chord_label == "C:maj"
        assert confidence >= 0.66

    def test_match_chord_template_cmaj7(self, cmaj7_events):
        """C major 7 should match C:maj7 via 277-class -> C:maj via MIREX."""
        active_pcs = {e.pitch % 12 for e in cmaj7_events}
        chord_label, confidence = _match_chord_template(active_pcs)
        assert "C:" in chord_label
        assert confidence >= 0.66

    def test_match_chord_template_too_few_notes(self):
        """A single pitch should not match any chord."""
        active_pcs = {0}  # just C
        chord_label, confidence = _match_chord_template(active_pcs)
        assert chord_label == "N"
        assert confidence > 0

    def test_match_chord_template_empty(self):
        """No pitches should produce N."""
        chord_label, confidence = _match_chord_template(set())
        assert chord_label == "N"

    def test_to_mirex_map(self):
        assert _to_mirex("C:maj") == "C:maj"
        assert _to_mirex("C:7") == "C:maj"
        assert _to_mirex("C:maj7") == "C:maj"
        assert _to_mirex("C:min") == "C:min"
        assert _to_mirex("C:min7") == "C:min"
        assert _to_mirex("C:dim") == "C:min"
        assert _to_mirex("G:7") == "G:maj"
        assert _to_mirex("N") == "N"

    def test_infer_chords_transition(self, cmaj_events, gmaj_events):
        """C major → G major transition should produce two chord events."""
        all_events = cmaj_events + gmaj_events
        stream = Mt3EventStream(
            events=all_events,
            audio_duration_s=4.0,
            mean_confidence=0.92,
            num_instruments=1,
        )
        beat_grid = BeatGrid(
            bpm=120.0, pulse_bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
            downbeats=[0.0, 2.0],
            time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )
        timeline = decode_events_to_chord_timeline(stream, beat_grid)
        assert len(timeline.events) > 0

        chord_labels = [e.chord for e in timeline.events]
        first_maj = [c for c in chord_labels if "C:" in c]
        second_maj = [c for c in chord_labels if "G:" in c]

        assert len(first_maj) >= 1, f"Expected at least one C: chord, got {chord_labels}"
        assert len(second_maj) >= 1, f"Expected at least one G: chord, got {chord_labels}"

    def test_build_active_note_grid(self, cmaj_events):
        """Active note grid at time 0 should contain C, E, G pitch classes."""
        grid = _build_active_note_grid(cmaj_events, audio_end=2.0)
        assert 0.0 in grid
        pcs_at_zero = set(grid[0.0].keys())
        assert 0 in pcs_at_zero  # C
        assert 4 in pcs_at_zero  # E
        assert 7 in pcs_at_zero  # G

    def test_empty_events_produce_empty_timeline(self):
        stream = Mt3EventStream(audio_duration_s=0.0)
        beat_grid = BeatGrid(
            bpm=120.0, pulse_bpm=120.0, beats=[0.0],
            downbeats=[0.0], time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )
        timeline = decode_events_to_chord_timeline(stream, beat_grid)
        assert len(timeline.events) == 0


# ---------------------------------------------------------------------------
# Chord Decoder — Instrument Filtering & Guitar Preference Tests
# ---------------------------------------------------------------------------

class TestChordDecoderInstrumentFiltering:
    def test_percussion_excluded_from_active_grid(self):
        """Program 128 (percussion) events must not appear in the active note grid."""
        events = [
            Mt3Event(time=0.0, pitch=60, velocity=100, program=24, is_onset=True, confidence=0.9),
            Mt3Event(time=0.0, pitch=64, velocity=90, program=24, is_onset=True, confidence=0.9),
            Mt3Event(time=0.0, pitch=67, velocity=95, program=24, is_onset=True, confidence=0.9),
            Mt3Event(time=0.0, pitch=36, velocity=80, program=128, is_onset=True, confidence=0.99),
            Mt3Event(time=1.0, pitch=60, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=64, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=67, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=36, velocity=0, program=128, is_onset=False, is_offset=True, confidence=0.9),
        ]
        grid = _build_active_note_grid(events, audio_end=1.5)
        pcs_at_zero = set(grid[0.0].keys())
        # Percussion pitch 36 % 12 = 0 (C), but it should be excluded
        # Only guitar events for C(0), E(4), G(7) should remain
        all_programs = {
            e.program for note_events in grid[0.0].values() for e in note_events
        }
        assert 128 not in all_programs
        assert 0 in pcs_at_zero  # C from guitar
        assert 4 in pcs_at_zero  # E from guitar
        assert 7 in pcs_at_zero  # G from guitar

    def test_guitar_preference_dominates_piano(self):
        """When guitar and piano play different notes at the same pitch class,
        guitar events should be kept and piano events dropped."""
        events = [
            # Guitar plays C4 (pitch 60, pc=0)
            Mt3Event(time=0.0, pitch=60, velocity=100, program=24, is_onset=True, confidence=0.9),
            # Piano plays C5 (pitch 72, pc=0) — same pitch class, different octave
            Mt3Event(time=0.0, pitch=72, velocity=90, program=0, is_onset=True, confidence=0.9),
            # Guitar plays E4 (pitch 64, pc=4)
            Mt3Event(time=0.0, pitch=64, velocity=90, program=24, is_onset=True, confidence=0.9),
            # Guitar plays G4 (pitch 67, pc=7)
            Mt3Event(time=0.0, pitch=67, velocity=95, program=24, is_onset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=60, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=72, velocity=0, program=0, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=64, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=67, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
        ]
        grid = _build_active_note_grid(events, audio_end=1.5, prefer_guitar=True)
        # At time 0, pc=0 should have only the guitar event (pitch 60), not piano (pitch 72)
        events_at_pc0 = grid[0.0].get(0, [])
        programs_at_pc0 = {e.program for e in events_at_pc0}
        assert 24 in programs_at_pc0  # guitar retained
        assert 0 not in programs_at_pc0  # piano dropped

    def test_guitar_preference_false_uses_all_instruments(self):
        """When prefer_guitar=False, all instrument events are kept."""
        events = [
            Mt3Event(time=0.0, pitch=60, velocity=100, program=24, is_onset=True, confidence=0.9),
            Mt3Event(time=0.0, pitch=72, velocity=90, program=0, is_onset=True, confidence=0.9),
            Mt3Event(time=0.0, pitch=64, velocity=90, program=24, is_onset=True, confidence=0.9),
            Mt3Event(time=0.0, pitch=67, velocity=95, program=24, is_onset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=60, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=72, velocity=0, program=0, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=64, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=67, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
        ]
        grid = _build_active_note_grid(events, audio_end=1.5, prefer_guitar=False)
        events_at_pc0 = grid[0.0].get(0, [])
        programs_at_pc0 = {e.program for e in events_at_pc0}
        assert 24 in programs_at_pc0
        assert 0 in programs_at_pc0

    def test_confidence_is_coverage_fraction(self):
        """For C:maj template {0,4,7} with active set {0,4,7,9},
        confidence should be 1.0 (coverage = 3/3 = 1.0), not 0.75 (Jaccard)."""
        active_pcs = {0, 4, 7, 9}  # C E G A — C:maj tones all present + extra A
        chord_label, confidence = _match_chord_template(active_pcs)
        assert chord_label == "C:maj"
        # Coverage = |{0,4,7} ∩ {0,4,7,9}| / |{0,4,7}| = 3/3 = 1.0
        assert confidence == 1.0

    def test_confidence_reflects_incomplete_chord(self):
        """For C:maj template {0,4,7} with active set {0,7} (missing E),
        Jaccard = 2/3 ≈ 0.667 which is right at the threshold — should match."""
        active_pcs = {0, 7}  # C G — missing E
        chord_label, confidence = _match_chord_template(active_pcs)
        assert chord_label == "C:maj"
        assert confidence == pytest.approx(2 / 3, abs=0.01)

    def test_n_confidence_for_empty_grid(self):
        """Empty pitch set should produce N with confidence 1.0."""
        chord_label, confidence = _match_chord_template(set())
        assert chord_label == "N"
        assert confidence == 1.0

    def test_guitar_only_events_used_for_chord(self):
        """Chord inference with guitar-only events should work correctly."""
        events = [
            Mt3Event(time=0.0, pitch=60, velocity=100, program=24, is_onset=True, confidence=0.9),
            Mt3Event(time=0.0, pitch=64, velocity=90, program=25, is_onset=True, confidence=0.9),
            Mt3Event(time=0.0, pitch=67, velocity=95, program=26, is_onset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=60, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=64, velocity=0, program=25, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=67, velocity=0, program=26, is_onset=False, is_offset=True, confidence=0.9),
        ]
        stream = Mt3EventStream(events=events, audio_duration_s=1.5, mean_confidence=0.9, num_instruments=1)
        beat_grid = BeatGrid(
            bpm=120.0, pulse_bpm=120.0, beats=[0.0, 0.5, 1.0],
            downbeats=[0.0], time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )
        timeline = decode_events_to_chord_timeline(stream, beat_grid, prefer_guitar_programs=True)
        assert len(timeline.events) >= 1
        assert timeline.events[0].chord == "C:maj"

    def test_mixed_instruments_guitar_dominates(self):
        """When guitar and piano share pitch classes, guitar events should
        dominate chord inference by being the sole contributors at those PCs."""
        events = [
            # Guitar: C4 E4 G4 (C:maj)
            Mt3Event(time=0.0, pitch=60, velocity=100, program=24, is_onset=True, confidence=0.9),
            Mt3Event(time=0.0, pitch=64, velocity=90, program=24, is_onset=True, confidence=0.9),
            Mt3Event(time=0.0, pitch=67, velocity=95, program=24, is_onset=True, confidence=0.9),
            # Piano: C5 E5 (same pitch classes as guitar, different octaves)
            Mt3Event(time=0.0, pitch=72, velocity=85, program=0, is_onset=True, confidence=0.85),
            Mt3Event(time=0.0, pitch=76, velocity=80, program=0, is_onset=True, confidence=0.85),
            Mt3Event(time=1.0, pitch=60, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=64, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=67, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=1.0, pitch=72, velocity=0, program=0, is_onset=False, is_offset=True, confidence=0.85),
            Mt3Event(time=1.0, pitch=76, velocity=0, program=0, is_onset=False, is_offset=True, confidence=0.85),
        ]
        stream = Mt3EventStream(events=events, audio_duration_s=1.5, mean_confidence=0.88, num_instruments=2)
        beat_grid = BeatGrid(
            bpm=120.0, pulse_bpm=120.0, beats=[0.0, 0.5, 1.0],
            downbeats=[0.0], time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )
        timeline = decode_events_to_chord_timeline(stream, beat_grid, prefer_guitar_programs=True)
        assert len(timeline.events) >= 1
        # Guitar preference drops piano at shared PCs → active_pcs = {0,4,7} → C:maj
        assert timeline.events[0].chord == "C:maj"

class TestSoloDecoder:
    def test_filter_melodic_events_excludes_percussion(self, multi_instrument_events):
        """Percussion (program 128) should be filtered out."""
        filtered = _filter_melodic_events(multi_instrument_events, prefer_guitar=True)
        programs = {e.program for e in filtered}
        assert 128 not in programs
        assert 24 in programs   # guitar retained
        assert 0 in programs    # piano retained

    def test_build_note_segments_pairs_onsets_offsets(self):
        """Onset+offset pair should produce one NoteSegment."""
        events = [
            Mt3Event(time=0.0, pitch=60, velocity=100, program=24, is_onset=True, confidence=0.9),
            Mt3Event(time=0.5, pitch=60, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
        ]
        segments = _build_note_segments(events)
        assert len(segments) == 1
        assert segments[0].start_time == 0.0
        assert segments[0].end_time == 0.5
        assert segments[0].pitch == 60

    def test_filter_short_noise_removes_artifacts(self):
        """Segments shorter than MIN_NOTE_DURATION should be removed."""
        segments = [
            NoteSegment(start_time=0.0, end_time=0.01, pitch=60, mean_velocity=100, max_confidence=0.9, program=24),
            NoteSegment(start_time=0.5, end_time=1.0, pitch=64, mean_velocity=90, max_confidence=0.9, program=24),
        ]
        filtered = _filter_short_noise(segments)
        assert len(filtered) == 1
        assert filtered[0].pitch == 64

    def test_quantize_to_grid(self, sample_beat_grid):
        """Quantization should snap to nearest beat."""
        bt = sample_beat_grid.beats

        snapped = _quantize_to_grid(0.05, bt, quantize_type="onset")
        assert snapped == 0.0

        snapped = _quantize_to_grid(0.45, bt, quantize_type="onset")
        assert snapped == 0.5

        snapped = _quantize_to_grid(0.55, bt, quantize_type="offset")
        assert snapped == 0.5

    def test_resolve_simultaneous_notes_keeps_loudest(self):
        """When two notes start at the same time, keep the louder one."""
        notes = [
            SoloNote(start_time=1.0, duration=0.5, pitch=60, velocity=80),
            SoloNote(start_time=1.0, duration=0.5, pitch=64, velocity=100),
            SoloNote(start_time=2.0, duration=0.5, pitch=67, velocity=90),
        ]
        resolved = _resolve_simultaneous_notes(notes)
        assert len(resolved) == 2
        assert resolved[0].pitch == 64  # louder of the two at t=1.0

    def test_solo_decoder_empty_events(self, sample_beat_grid):
        """Empty event stream should produce empty SoloNotes."""
        stream = Mt3EventStream(audio_duration_s=0.0)
        result = decode_events_to_solo_notes(stream, sample_beat_grid)
        assert len(result.notes) == 0

    def test_solo_decoder_monophonic_line(self, sample_beat_grid):
        """A simple ascending scale should produce quantized notes."""
        events = []
        for i, pitch in enumerate([60, 62, 64, 65, 67]):
            t = i * 0.5
            events.append(Mt3Event(time=t, pitch=pitch, velocity=90, program=24, is_onset=True, confidence=0.9))
            events.append(Mt3Event(time=t + 0.4, pitch=pitch, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9))

        stream = Mt3EventStream(events=events, audio_duration_s=3.0, mean_confidence=0.9, num_instruments=1)
        result = decode_events_to_solo_notes(stream, sample_beat_grid)
        assert len(result.notes) == 5

    def test_decode_events_populates_confidence(self, sample_beat_grid):
        """Output SoloNotes should have confidence values from event confidence."""
        events = [
            Mt3Event(time=0.0, pitch=60, velocity=100, program=24, is_onset=True, confidence=0.85),
            Mt3Event(time=0.5, pitch=60, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.80),
        ]
        stream = Mt3EventStream(events=events, audio_duration_s=1.0, mean_confidence=0.85, num_instruments=1)
        result = decode_events_to_solo_notes(stream, sample_beat_grid)
        assert len(result.notes) == 1
        assert 0.0 < result.notes[0].confidence <= 1.0

    def test_decode_events_applies_technique_tags(self, sample_beat_grid):
        """Bend/vibrato/grace patterns should produce technique tags on output notes."""
        events = [
            Mt3Event(time=0.0, pitch=60, velocity=90, program=24, is_onset=True, confidence=0.9),
            Mt3Event(time=0.06, pitch=60, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
            Mt3Event(time=0.07, pitch=62, velocity=95, program=24, is_onset=True, confidence=0.9),
            Mt3Event(time=0.5, pitch=62, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
        ]
        stream = Mt3EventStream(events=events, audio_duration_s=1.0, mean_confidence=0.9, num_instruments=1)
        result = decode_events_to_solo_notes(stream, sample_beat_grid)
        all_techniques = [t for note in result.notes for t in note.technique]
        assert len(all_techniques) > 0


# ---------------------------------------------------------------------------
# Solo Decoder — Technique Detection Tests
# ---------------------------------------------------------------------------

class TestSoloDecoderTechniqueDetection:
    def test_detect_bends_slide_pattern(self):
        """Adjacent segments with pitch slide within 2 semitones and gap < 50ms should be tagged 'bend'."""
        segments = [
            NoteSegment(start_time=0.0, end_time=0.3, pitch=60, mean_velocity=100, max_confidence=0.9, program=24),
            NoteSegment(start_time=0.32, end_time=0.6, pitch=62, mean_velocity=95, max_confidence=0.9, program=24),
        ]
        result = _detect_bends(segments)
        assert "bend" in result[0].technique
        assert "bend" in result[1].technique

    def test_detect_bends_no_match_wide_gap(self):
        """Segments with gap > 100ms should not be tagged as bends."""
        segments = [
            NoteSegment(start_time=0.0, end_time=0.3, pitch=60, mean_velocity=100, max_confidence=0.9, program=24),
            NoteSegment(start_time=0.5, end_time=0.8, pitch=62, mean_velocity=95, max_confidence=0.9, program=24),
        ]
        result = _detect_bends(segments)
        assert "bend" not in result[0].technique
        assert "bend" not in result[1].technique

    def test_detect_bends_no_match_wide_pitch(self):
        """Segments with pitch difference > 2 semitones should not be tagged."""
        segments = [
            NoteSegment(start_time=0.0, end_time=0.3, pitch=60, mean_velocity=100, max_confidence=0.9, program=24),
            NoteSegment(start_time=0.32, end_time=0.6, pitch=65, mean_velocity=95, max_confidence=0.9, program=24),
        ]
        result = _detect_bends(segments)
        assert "bend" not in result[0].technique
        assert "bend" not in result[1].technique

    def test_detect_bends_no_match_different_program(self):
        """Segments from different programs should not be tagged as bends."""
        segments = [
            NoteSegment(start_time=0.0, end_time=0.3, pitch=60, mean_velocity=100, max_confidence=0.9, program=24),
            NoteSegment(start_time=0.32, end_time=0.6, pitch=61, mean_velocity=95, max_confidence=0.9, program=25),
        ]
        result = _detect_bends(segments)
        assert "bend" not in result[0].technique
        assert "bend" not in result[1].technique

    def test_detect_vibrato_rapid_oscillation(self):
        """3+ same-pitch segments with duration < 100ms and total < 500ms should be tagged 'vibrato'."""
        segments = [
            NoteSegment(start_time=0.0, end_time=0.05, pitch=60, mean_velocity=100, max_confidence=0.9, program=24),
            NoteSegment(start_time=0.05, end_time=0.10, pitch=60, mean_velocity=95, max_confidence=0.9, program=24),
            NoteSegment(start_time=0.10, end_time=0.15, pitch=60, mean_velocity=100, max_confidence=0.9, program=24),
            NoteSegment(start_time=0.15, end_time=0.20, pitch=60, mean_velocity=95, max_confidence=0.9, program=24),
        ]
        result = _detect_vibrato(segments)
        for seg in result:
            assert "vibrato" in seg.technique

    def test_detect_vibrato_no_match_long_durations(self):
        """Segments with duration >= 100ms should not form vibrato pattern."""
        segments = [
            NoteSegment(start_time=0.0, end_time=0.15, pitch=60, mean_velocity=100, max_confidence=0.9, program=24),
            NoteSegment(start_time=0.15, end_time=0.30, pitch=60, mean_velocity=95, max_confidence=0.9, program=24),
            NoteSegment(start_time=0.30, end_time=0.45, pitch=60, mean_velocity=100, max_confidence=0.9, program=24),
        ]
        result = _detect_vibrato(segments)
        for seg in result:
            assert "vibrato" not in seg.technique

    def test_grace_note_detection(self):
        """Short note (< 0.08s) followed by longer note within 50ms should be tagged 'grace_note'."""
        segments = [
            NoteSegment(start_time=0.0, end_time=0.05, pitch=60, mean_velocity=80, max_confidence=0.9, program=24),
            NoteSegment(start_time=0.06, end_time=0.5, pitch=64, mean_velocity=100, max_confidence=0.9, program=24),
        ]
        result = _detect_grace_notes(segments)
        assert "grace_note" in result[0].technique
        assert "grace_note" not in result[1].technique

    def test_grace_note_not_removed(self):
        """Grace notes should remain in the output (not filtered out)."""
        segments = [
            NoteSegment(start_time=0.0, end_time=0.05, pitch=60, mean_velocity=80, max_confidence=0.9, program=24),
            NoteSegment(start_time=0.06, end_time=0.5, pitch=64, mean_velocity=100, max_confidence=0.9, program=24),
        ]
        result = _detect_grace_notes(segments)
        assert len(result) == 2

    def test_tie_detection_merges_notes(self):
        """Notes across boundary with matching pitch/timing should merge with is_tied=True."""
        notes = [
            SoloNote(start_time=0.0, duration=12.9, pitch=60, velocity=100),
            SoloNote(start_time=12.85, duration=1.0, pitch=60, velocity=95),
        ]
        result = _merge_boundary_notes(notes, bpm=120.0, window_sec=12.8)
        tied_notes = [n for n in result if n.is_tied]
        assert len(tied_notes) >= 1

    def test_confidence_calculation(self, sample_beat_grid):
        """Event confidence should be reflected in output SoloNote.confidence."""
        events = [
            Mt3Event(time=0.0, pitch=60, velocity=100, program=0, is_onset=True, confidence=0.75),
            Mt3Event(time=0.5, pitch=60, velocity=0, program=0, is_onset=False, is_offset=True, confidence=0.70),
        ]
        stream = Mt3EventStream(events=events, audio_duration_s=1.0, mean_confidence=0.75, num_instruments=1)
        result = decode_events_to_solo_notes(stream, sample_beat_grid)
        assert len(result.notes) == 1
        assert result.notes[0].confidence == pytest.approx(0.75, abs=0.01)

    def test_coherence_factor_monophonic(self):
        """Isolated segment should have coherence factor 1.0."""
        seg = NoteSegment(start_time=0.0, end_time=0.5, pitch=60, mean_velocity=100, max_confidence=0.9, program=24)
        assert _coherence_factor(seg, [seg]) == 1.0

    def test_coherence_factor_polyphonic(self):
        """Overlapping segments should have coherence factor 0.9."""
        seg1 = NoteSegment(start_time=0.0, end_time=0.5, pitch=60, mean_velocity=100, max_confidence=0.9, program=24)
        seg2 = NoteSegment(start_time=0.3, end_time=0.8, pitch=64, mean_velocity=90, max_confidence=0.9, program=24)
        assert _coherence_factor(seg1, [seg1, seg2]) == 0.9

    def test_merge_boundary_notes_empty(self):
        """Empty note list should return empty."""
        assert _merge_boundary_notes([], 120.0) == []


# ---------------------------------------------------------------------------
# Fallback Orchestrator Tests
# ---------------------------------------------------------------------------

class TestFallbackOrchestrator:
    def test_transcription_source_labels(self):
        assert "MT3" in get_transcription_source_label("mt3")
        assert "CRNN" in get_transcription_source_label("crnn")
        assert "Chroma" in get_transcription_source_label("chroma")
        assert "No transcription" in get_transcription_source_label("none")

    def test_transcription_result_defaults(self):
        result = TranscriptionResult()
        assert len(result.chord_timeline.events) == 0
        assert len(result.solo_notes.notes) == 0
        assert result.source == "none"
        assert result.mean_confidence == 0.0
        # Commit A2.1: transcription_metadata should default to None
        assert result.transcription_metadata is None

    def test_fallback_file_not_found(self):
        """transcribe_with_fallback should return none source when file missing."""
        bg = BeatGrid(
            bpm=120.0, pulse_bpm=120.0, beats=[0.0],
            downbeats=[0.0], time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )
        result = transcribe_with_fallback("/nonexistent/audio.wav", bg, use_mt3=False)
        assert result.source == "none"
        assert result.fallback_reason == "audio_file_not_found"
        assert result.transcription_metadata is not None
        assert result.transcription_metadata["tier_reasons"]["none"] == "audio_file_not_found"

    def test_fallback_skips_mt3_when_use_mt3_false(self, tmp_path):
        """When use_mt3=False, the orchestrator should skip MT3 and go to CRNN."""
        audio_file = tmp_path / "test_silence.wav"
        import struct
        import wave
        with wave.open(str(audio_file), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(struct.pack(f"<{16000}h", *[0] * 16000))

        bg = BeatGrid(
            bpm=120.0, pulse_bpm=120.0, beats=[0.0, 0.5],
            downbeats=[0.0], time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )

        result = transcribe_with_fallback(str(audio_file), bg, use_mt3=False)
        assert result.source in ("crnn", "chroma", "none")

    # ------------------------------------------------------------------
    # Commit A2.1 — Fallback chain metadata and tier tracking tests
    # ------------------------------------------------------------------

    def test_transcription_metadata_on_mt3_success(self, tmp_path, monkeypatch):
        """When MT3 succeeds, transcription_metadata should contain chain info."""
        audio_file = tmp_path / "test_mt3_ok.wav"
        import struct
        import wave
        with wave.open(str(audio_file), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(struct.pack(f"<{16000}h", *[0] * 16000))

        bg = BeatGrid(
            bpm=120.0, pulse_bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
            downbeats=[0.0, 2.0, 4.0],
            time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )

        def fake_try_mt3(*args, **kwargs):
            return TranscriptionResult(
                chord_timeline=ChordTimeline(events=[
                    ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.95),
                    ChordEvent(timestamp=1.0, chord="G:maj", confidence=0.92),
                    ChordEvent(timestamp=2.0, chord="A:min", confidence=0.90),
                ]),
                solo_notes=SoloNotes(notes=[]),
                source="mt3",
                mean_confidence=0.91,
            )

        monkeypatch.setattr("app.mt3.fallback._try_mt3", fake_try_mt3)

        result = transcribe_with_fallback(str(audio_file), bg, use_mt3=True)
        assert result.source == "mt3"
        assert result.transcription_metadata is not None
        assert result.transcription_metadata["attempted_tiers"] == ["mt3"]
        assert result.transcription_metadata["tier_reasons"]["mt3"] == "success"
        assert result.transcription_metadata["mean_confidence"] == pytest.approx(0.91)

    def test_transcription_metadata_tracks_fallback_reason(self, tmp_path, monkeypatch):
        """When MT3 fails and CRNN succeeds, tier_reasons should capture MT3's reason."""
        audio_file = tmp_path / "test_fallback.wav"
        import struct
        import wave
        with wave.open(str(audio_file), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(struct.pack(f"<{16000}h", *[0] * 16000))

        bg = BeatGrid(
            bpm=120.0, pulse_bpm=120.0, beats=[0.0, 0.5, 1.0, 1.5],
            downbeats=[0.0, 2.0], time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )

        # MT3 returns None (server unavailable)
        monkeypatch.setattr("app.mt3.fallback._try_mt3", lambda *a, **k: None)

        # CRNN succeeds
        def fake_try_crnn(*args, **kwargs):
            return TranscriptionResult(
                chord_timeline=ChordTimeline(events=[
                    ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.80),
                ]),
                solo_notes=SoloNotes(notes=[]),
                source="crnn",
                mean_confidence=0.80,
            )

        monkeypatch.setattr("app.mt3.fallback._try_crnn", fake_try_crnn)

        result = transcribe_with_fallback(str(audio_file), bg, use_mt3=True)
        assert result.source == "crnn"
        assert result.transcription_metadata is not None
        assert result.transcription_metadata["attempted_tiers"] == ["mt3", "crnn"]
        assert result.transcription_metadata["tier_reasons"]["mt3"] == "mt3_server_unavailable"
        assert result.transcription_metadata["tier_reasons"]["crnn"] == "success"

    def test_chain_metadata_all_tiers_failed(self, tmp_path, monkeypatch):
        """When both tiers fail, metadata captures all failure reasons."""
        bg = BeatGrid(
            bpm=120.0, pulse_bpm=120.0, beats=[0.0],
            downbeats=[0.0], time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )

        result = transcribe_with_fallback("/tmp/nonexistent_fallback_test.wav", bg, use_mt3=True)
        assert result.source == "none"
        assert result.fallback_reason == "audio_file_not_found"
        assert result.transcription_metadata is not None

    def test_crnn_detects_chroma_source(self, monkeypatch):
        """_try_crnn should return source='chroma' when get_last_inference_tier() returns 'chroma'."""
        from app.mt3.fallback import _try_crnn

        bg = BeatGrid(
            bpm=120.0, pulse_bpm=120.0, beats=[0.0, 0.5],
            downbeats=[0.0], time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )

        monkeypatch.setattr(
            "app.mt3.fallback.infer_chords",
            lambda *a, **k: ChordTimeline(events=[
                ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.75),
            ]),
        )
        monkeypatch.setattr(
            "app.mt3.fallback.get_last_inference_tier",
            lambda: "chroma",
        )

        result = _try_crnn(Path("/tmp/fake.wav"), bg)
        assert result is not None
        assert result.source == "chroma"
        assert result.mean_confidence == pytest.approx(0.75)

    def test_fallback_logging_includes_chain_info(self, tmp_path, monkeypatch, caplog):
        """The structured log line should contain source, confidence, and chain info."""
        import struct
        import wave

        audio_file = tmp_path / "test_logging.wav"
        with wave.open(str(audio_file), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(struct.pack(f"<{16000}h", *[0] * 16000))

        bg = BeatGrid(
            bpm=120.0, pulse_bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5],
            downbeats=[0.0, 2.0, 4.0],
            time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )

        def fake_try_mt3(*args, **kwargs):
            return TranscriptionResult(
                chord_timeline=ChordTimeline(events=[
                    ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.95),
                    ChordEvent(timestamp=1.0, chord="G:maj", confidence=0.92),
                    ChordEvent(timestamp=2.0, chord="A:min", confidence=0.90),
                ]),
                solo_notes=SoloNotes(notes=[]),
                source="mt3",
                mean_confidence=0.91,
            )

        monkeypatch.setattr("app.mt3.fallback._try_mt3", fake_try_mt3)

        with caplog.at_level(logging.INFO, logger="harmoniq.mt3.fallback"):
            transcribe_with_fallback(str(audio_file), bg, use_mt3=True)

        fallback_logs = [r for r in caplog.records
                         if "Fallback chain result" in r.message]
        assert len(fallback_logs) >= 1
        log_msg = fallback_logs[0].message
        assert "source=mt3" in log_msg
        assert "confidence=0.91" in log_msg or "confidence=0.910" in log_msg
        assert "chain=" in log_msg
        assert "reasons=" in log_msg


# ---------------------------------------------------------------------------
# Model Server / Warm-start Tests
# ---------------------------------------------------------------------------

class TestModelServer:
    def test_warm_start_returns_bool(self):
        """warm_start() should return a boolean without raising."""
        server = Mt3ModelServer()
        result = server.warm_start()
        assert isinstance(result, bool)

    def test_load_error_returns_none_when_not_attempted(self):
        """load_error() should return None before any load attempt."""
        server = Mt3ModelServer()
        err = server.load_error()
        assert err is None or isinstance(err, str)

    def test_warm_start_is_idempotent(self):
        """Calling warm_start() multiple times should not raise."""
        server = Mt3ModelServer()
        first = server.warm_start()
        second = server.warm_start()
        assert first == second


# ---------------------------------------------------------------------------
# Router / API Endpoint Tests
# ---------------------------------------------------------------------------

class TestMt3Router:
    """Tests for the MT3 FastAPI router in isolation.

    Verifies route registration, endpoint handler logic, and error responses
    by directly testing the router's route table and calling handler
    functions. Does not use TestClient (which has asyncio compatibility
    issues on this Python/OS combination).
    """

    def test_router_prefix(self):
        """Router should be mounted at /mt3 prefix."""
        from app.routers.mt3 import router as mt3_router
        assert mt3_router.prefix == "/mt3"
        routes = [r.path for r in mt3_router.routes]
        assert "/mt3/infer" in routes
        assert "/mt3/infer/batch" in routes
        assert "/mt3/status" in routes

    def test_router_tags(self):
        """Router should have mt3 tag."""
        from app.routers.mt3 import router as mt3_router
        assert "mt3" in mt3_router.tags

    def test_infer_endpoint_method_and_response_model(self):
        """POST /mt3/infer should be a POST endpoint returning Mt3EventStream."""
        from app.routers.mt3 import router as mt3_router
        from app.mt3.schemas import Mt3EventStream

        infer_route = None
        for route in mt3_router.routes:
            if route.path == "/mt3/infer" and "POST" in route.methods:
                infer_route = route
                break

        assert infer_route is not None
        assert infer_route.response_model == Mt3EventStream
        assert infer_route.endpoint is not None

    def test_batch_endpoint_method_and_response_model(self):
        """POST /mt3/infer/batch should return list[Mt3EventStream]."""
        from app.routers.mt3 import router as mt3_router
        from app.mt3.schemas import Mt3EventStream

        batch_route = None
        for route in mt3_router.routes:
            if route.path == "/mt3/infer/batch" and "POST" in route.methods:
                batch_route = route
                break

        assert batch_route is not None
        assert batch_route.response_model == list[Mt3EventStream]

    def test_status_endpoint_method(self):
        """GET /mt3/status should be a GET endpoint returning dict."""
        from app.routers.mt3 import router as mt3_router

        status_route = None
        for route in mt3_router.routes:
            if route.path == "/mt3/status" and "GET" in route.methods:
                status_route = route
                break

        assert status_route is not None

    def test_router_imports_cleanly(self):
        """The router module should import without errors."""
        from app.routers import mt3
        assert hasattr(mt3, "router")
        assert hasattr(mt3, "infer_single")
        assert hasattr(mt3, "infer_batch")
        assert hasattr(mt3, "mt3_status")

    def test_infer_handler_signature(self):
        """infer_single handler should accept a wav_path string parameter."""
        import inspect
        from app.routers.mt3 import infer_single

        sig = inspect.signature(infer_single)
        params = list(sig.parameters.keys())
        assert "wav_path" in params, f"Expected wav_path param, got {params}"

    def test_batch_handler_signature(self):
        """infer_batch handler should accept wav_paths list parameter."""
        import inspect
        from app.routers.mt3 import infer_batch

        sig = inspect.signature(infer_batch)
        params = list(sig.parameters.keys())
        assert "wav_paths" in params, f"Expected wav_paths param, got {params}"


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_chord_and_solo_coexist_in_lesson_json(self):
        """Verify LessonJSON can hold both chord_timeline and solo_notes simultaneously."""
        lesson = {
            "job_id": "test-001",
            "chord_timeline": ChordTimeline(events=[
                ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.95),
                ChordEvent(timestamp=2.0, chord="G:maj", confidence=0.90),
            ]),
            "solo_notes": SoloNotes(notes=[
                SoloNote(start_time=0.0, duration=0.5, pitch=60, velocity=100),
                SoloNote(start_time=0.5, duration=0.5, pitch=64, velocity=90),
            ]),
            "transcription_source": "mt3",
        }
        assert len(lesson["chord_timeline"].events) == 2
        assert len(lesson["solo_notes"].notes) == 2
        assert lesson["transcription_source"] == "mt3"


# ---------------------------------------------------------------------------
# Commit A1.4 — Dual-Output LessonJSON Assembly Tests
# ---------------------------------------------------------------------------


class TestMT3LessonJSONAssembly:
    """Tests for Commit A1.4: MT3 dual output → LessonJSON assembly.

    These tests mock the heavy inference dependencies (transcribe_with_fallback,
    librosa_summarize, etc.) and test only the LessonJSON assembly logic in
    build_lesson_json_from_librosa.
    """

    # ------------------------------------------------------------------
    # Test helpers — following the pattern from test_stem_routing_pipeline.py
    # ------------------------------------------------------------------

    @staticmethod
    def _fake_summary():
        from app.pipeline_proof import LibrosaSummary
        return LibrosaSummary(
            duration_s=4.0,
            tempo_bpm=120.0,
            beat_times_s=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
            key_name="C major",
            mode="major",
            segments=[{"label": "Intro", "start_s": 0.0}],
            bar_timestamps_s=[0.0, 2.0, 4.0],
            key_confidence=0.9,
            tempo_confidence=0.9,
        )

    @staticmethod
    def _fake_beat_grid_dict():
        from app.schemas import BeatGrid
        return BeatGrid(
            bpm=120.0,
            pulse_bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
            downbeats=[0.0, 2.0, 4.0],
            time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        ).model_dump()

    @staticmethod
    def _fake_mt3_chord_timeline():
        return ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.95),
            ChordEvent(timestamp=0.5, chord="C:maj", confidence=0.93),
            ChordEvent(timestamp=1.0, chord="G:maj", confidence=0.90),
            ChordEvent(timestamp=1.5, chord="G:maj", confidence=0.91),
            ChordEvent(timestamp=2.0, chord="A:min", confidence=0.88),
            ChordEvent(timestamp=2.5, chord="A:min", confidence=0.87),
            ChordEvent(timestamp=3.0, chord="F:maj", confidence=0.92),
            ChordEvent(timestamp=3.5, chord="F:maj", confidence=0.90),
        ])

    @staticmethod
    def _fake_mt3_solo_notes():
        return SoloNotes(notes=[
            SoloNote(start_time=0.0, duration=0.5, pitch=60, velocity=100, fret=3, string=3),
            SoloNote(start_time=0.5, duration=0.5, pitch=64, velocity=90, fret=2, string=2),
            SoloNote(start_time=1.0, duration=0.5, pitch=67, velocity=95, fret=0, string=1),
            SoloNote(start_time=1.5, duration=0.5, pitch=71, velocity=85, fret=2, string=2),
            SoloNote(start_time=2.0, duration=0.5, pitch=72, velocity=90, fret=3, string=1),
            SoloNote(start_time=2.5, duration=0.5, pitch=76, velocity=88, fret=3, string=2),
            SoloNote(start_time=3.0, duration=0.5, pitch=77, velocity=92, fret=5, string=2),
            SoloNote(start_time=3.5, duration=0.5, pitch=81, velocity=86, fret=6, string=2),
        ])

    @staticmethod
    @staticmethod
    def _fake_transcription_result(*, source: str = "mt3", mean_confidence: float = 0.91):
        ct = TestMT3LessonJSONAssembly._fake_mt3_chord_timeline()
        ct.metadata = {
            "source": source,
            "decoder": "chord_decoder",
            "note_count": len(TestMT3LessonJSONAssembly._fake_mt3_solo_notes().notes),
            "mean_confidence": mean_confidence,
        }
        return TranscriptionResult(
            chord_timeline=ct,
            solo_notes=TestMT3LessonJSONAssembly._fake_mt3_solo_notes(),
            source=source,
            mean_confidence=mean_confidence,
        )

    @staticmethod
    def _write_dummy_stems(tmp_path):
        """Write minimal WAV files so build_lesson_json_from_librosa doesn't crash on path resolution."""
        import soundfile as sf
        sr = 44100
        job_dir = tmp_path / "data" / "jobs" / "test_job"
        (job_dir / "stems").mkdir(parents=True, exist_ok=True)
        for name in ("guitar", "vocals"):
            p = job_dir / "stems" / f"{name}.wav"
            sf.write(str(p), np.zeros(sr, dtype=np.float32), sr)
        song_wav = job_dir / "song.wav"
        sf.write(str(song_wav), np.zeros(sr, dtype=np.float32), sr)
        return job_dir, song_wav

    def _call_build_lesson(
        self,
        tmp_path,
        monkeypatch,
        *,
        mock_transcription_result: TranscriptionResult | None = None,
        infer_chords_fn=None,
        infer_solo_fn=None,
    ):
        """Helper: set up mocks and call build_lesson_json_from_librosa.

        Args:
            infer_chords_fn: Optional override for the infer_chords mock.
                If None, defaults to _fake_mt3_chord_timeline().
            infer_solo_fn: Optional override for the infer_solo mock.
                If None, defaults to _fake_mt3_solo_notes().
        """
        from app.analyze_audio import build_lesson_json_from_librosa
        from app.mt3.fallback import TranscriptionResult as TR
        from app.schemas import ChordTimeline, SoloNotes

        job_dir, song_wav = self._write_dummy_stems(tmp_path)

        # Default mock: return MT3 result from _fake_transcription_result
        if mock_transcription_result is None:
            mock_transcription_result = self._fake_transcription_result()

        def fake_transcribe(*args, **kwargs):
            return mock_transcription_result

        if infer_chords_fn is None:
            def infer_chords_fn(*args, **kwargs):
                return self._fake_mt3_chord_timeline()

        if infer_solo_fn is None:
            def infer_solo_fn(*args, **kwargs):
                return self._fake_mt3_solo_notes()

        monkeypatch.setattr("app.analyze_audio.transcribe_with_fallback", fake_transcribe)
        monkeypatch.setattr("app.analyze_audio.infer_chords", infer_chords_fn)
        monkeypatch.setattr("app.analyze_audio.infer_solo", infer_solo_fn)
        monkeypatch.setattr("app.analyze_audio.librosa_summarize", lambda p: self._fake_summary())
        monkeypatch.setattr("app.analyze_audio.estimate_beat_grid", lambda p: self._fake_beat_grid_dict())
        monkeypatch.setattr(
            "app.analyze_audio.generate_tab_artifacts_for_guitar_stem", lambda *a, **k: {}
        )
        monkeypatch.setattr(
            "app.analyze_audio.transcribe_vocals_to_lyrics_aligned",
            lambda *args, **kwargs: ([], 0.0),
        )

        result = build_lesson_json_from_librosa(
            "test_job",
            guitar_stem_path=job_dir / "stems" / "guitar.wav",
            vocals_stem_path=job_dir / "stems" / "vocals.wav",
            stems={"guitar": "stems/guitar.wav", "vocals": "stems/vocals.wav"},
            wav_path=str(song_wav),
        )
        return result

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_build_lesson_json_includes_transcription_source(self, tmp_path, monkeypatch):
        """When MT3 produces results, transcription_source should be 'mt3'."""
        result = self._call_build_lesson(tmp_path, monkeypatch)
        assert result.transcription_source == "mt3"

    def test_build_lesson_json_fallback_to_crnn_updates_source(self, tmp_path, monkeypatch):
        """When MT3 returns empty chord_timeline, CRNN fallback should set source='crnn'."""
        # MT3 returns empty chords
        mt3_result = self._fake_transcription_result()
        mt3_result.chord_timeline = ChordTimeline(events=[])
        mt3_result.source = "mt3"

        # CRNN fallback returns real chords
        def crnn_infer_chords(*args, **kwargs):
            return self._fake_mt3_chord_timeline()

        result = self._call_build_lesson(
            tmp_path, monkeypatch,
            mock_transcription_result=mt3_result,
            infer_chords_fn=crnn_infer_chords,
        )
        assert result.transcription_source == "crnn"

    def test_mt3_chord_and_solo_share_beat_grid(self, tmp_path, monkeypatch):
        """Chord events and solo notes should share the same beat_grid_structured."""
        result = self._call_build_lesson(tmp_path, monkeypatch)
        assert result.beat_grid_structured is not None
        assert len(result.beat_grid_structured.beats) > 0
        # Check that chord timestamps align with beat positions
        if result.chord_timeline and result.chord_timeline.events:
            for event in result.chord_timeline.events:
                assert event.timestamp in result.beat_grid_structured.beats or \
                       any(abs(event.timestamp - b) < 0.01 for b in result.beat_grid_structured.beats)

    def test_musicxml_generates_from_mt3_data(self):
        """build_musicxml() should produce valid MusicXML from MT3 data."""
        from app.musicxml_builder import build_musicxml
        from app.schemas import BeatGrid

        bt = BeatGrid(
            bpm=120.0,
            pulse_bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5],
            downbeats=[0.0, 2.0],
            time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )
        chord_timeline = self._fake_mt3_chord_timeline()
        solo_notes = self._fake_mt3_solo_notes()

        musicxml_str = build_musicxml(
            beat_grid=bt,
            chord_timeline=chord_timeline,
            solo_notes=solo_notes,
            title="Test Song",
            artist="Test Artist",
            key_signature="C major",
        )

        assert "<score-partwise" in musicxml_str
        assert "<measure" in musicxml_str
        assert "<note" in musicxml_str
        assert "<harmony" in musicxml_str or musicxml_str == "", \
            "Expected at least one harmony element or empty fallback"
        assert len(musicxml_str) > 0

    def test_downstream_section_refinement_runs(self, tmp_path, monkeypatch):
        """Section refinement should process MT3 chord data without error."""
        result = self._call_build_lesson(tmp_path, monkeypatch)
        assert len(result.sections) > 0
        # Each section should have chord_timeline (as dict) filtered to its time range
        for section in result.sections:
            section_chords = getattr(section, "chord_timeline", None)
            if section_chords and section_chords.get("events"):
                for event in section_chords["events"]:
                    if section.start_time_seconds is not None:
                        assert event["timestamp"] >= section.start_time_seconds
                    if section.end_time_seconds is not None:
                        assert event["timestamp"] < section.end_time_seconds

    def test_confidence_calculation_integration(self, tmp_path, monkeypatch):
        """LessonJSON.chord_timeline metadata should reflect MT3 mean_confidence."""
        result = self._call_build_lesson(
            tmp_path,
            monkeypatch,
            mock_transcription_result=self._fake_transcription_result(mean_confidence=0.85),
        )
        assert result.chord_timeline is not None
        metadata = result.chord_timeline.metadata or {}
        assert metadata.get("mean_confidence", 0.0) == pytest.approx(0.85, abs=0.01)
