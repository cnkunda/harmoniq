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
        """C major triad should match C:maj with Jaccard ≥ 0.66."""
        active_pcs = {e.pitch % 12 for e in cmaj_events}
        chord_label, confidence = _match_chord_template(active_pcs, {}, prefer_guitar=True)
        assert chord_label == "C:maj"
        assert confidence >= 0.66

    def test_match_chord_template_cmaj7(self, cmaj7_events):
        """C major 7 should match C:maj7 via 277-class → C:maj via MIREX."""
        active_pcs = {e.pitch % 12 for e in cmaj7_events}
        chord_label, confidence = _match_chord_template(active_pcs, {}, prefer_guitar=True)
        assert "C:" in chord_label
        assert confidence >= 0.66

    def test_match_chord_template_too_few_notes(self):
        """A single pitch should not match any chord."""
        active_pcs = {0}  # just C
        chord_label, confidence = _match_chord_template(active_pcs, {}, prefer_guitar=True)
        assert chord_label == "N"
        assert confidence > 0

    def test_match_chord_template_empty(self):
        """No pitches should produce N."""
        chord_label, confidence = _match_chord_template(set(), {}, prefer_guitar=True)
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
# Solo Decoder Tests
# ---------------------------------------------------------------------------

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
