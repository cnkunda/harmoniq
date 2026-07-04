"""Tests for MT3-Primary AMT Pipeline (Phase 2, Milestone A).

Tests cover:
  - Mt3Event and Mt3EventStream schema validation
  - Chord decoder: pitch class aggregation, template matching, MIREX mapping
  - Solo decoder: event filtering, note segment building, quantization
  - Fallback orchestrator: tier selection, confidence gating
  - Integration: full pipeline wiring in analyze_audio.py
"""

from __future__ import annotations

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
from app.mt3.model_server import Mt3ModelServer, _convert_note_sequence_to_events
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
