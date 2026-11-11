"""W5: calibrated MT3 fallback gate + rollback behavior."""

from __future__ import annotations

import pytest

from app.mt3 import fallback
from app.mt3.schemas import Mt3Event, Mt3EventStream
from app.schemas import BeatGrid, ChordEvent, ChordTimeline, SoloNotes, TimeSignature


def _beat_grid() -> BeatGrid:
    return BeatGrid(
        bpm=120.0,
        time_signature=TimeSignature(numerator=4, denominator=4),
        tick_value=0.25,
        beats=[0.0, 0.5, 1.0],
        downbeats=[0.0],
    )


class _FakeServer:
    def is_available(self) -> bool:
        return True


def _stream(mean_confidence: float = 0.9) -> Mt3EventStream:
    return Mt3EventStream(
        events=[
            Mt3Event(time=0.0, pitch=60, confidence=mean_confidence),
            Mt3Event(time=1.0, pitch=64, confidence=mean_confidence),
        ],
        audio_duration_s=3.0,
        mean_confidence=mean_confidence,
    )


def _timeline(confidence: float) -> ChordTimeline:
    return ChordTimeline(
        events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=confidence),
            ChordEvent(timestamp=1.0, chord="G:maj", confidence=confidence),
            ChordEvent(timestamp=2.0, chord="A:min", confidence=confidence),
        ]
    )


def _patch_mt3(monkeypatch, *, mean_confidence: float, chord_confidence: float):
    monkeypatch.setattr(fallback, "Mt3ModelServer", _FakeServer)
    monkeypatch.setattr(
        fallback, "mt3_infer", lambda _path: _stream(mean_confidence)
    )
    monkeypatch.setattr(
        fallback,
        "decode_events_to_chord_timeline",
        lambda _stream, _grid, **_kwargs: _timeline(chord_confidence),
    )
    monkeypatch.setattr(
        fallback,
        "decode_events_to_solo_notes",
        lambda _stream, _grid, **_kwargs: SoloNotes(notes=[]),
    )


def test_gate_off_preserves_legacy_event_confidence_behavior(monkeypatch):
    monkeypatch.delenv("HARMONIQ_CONFIDENCE_GATE", raising=False)
    _patch_mt3(monkeypatch, mean_confidence=0.5, chord_confidence=0.9)

    result = fallback._try_mt3("/tmp/x.wav", _beat_grid(), 0.7)

    assert result is not None
    assert result.chord_timeline.events == []
    assert result.fallback_reason == "mt3_low_confidence:0.50"


def test_gate_on_uses_chord_template_confidence(monkeypatch):
    monkeypatch.setenv("HARMONIQ_CONFIDENCE_GATE", "1")
    _patch_mt3(monkeypatch, mean_confidence=0.5, chord_confidence=0.9)

    result = fallback._try_mt3("/tmp/x.wav", _beat_grid(), 0.7)

    assert result is not None
    assert len(result.chord_timeline.events) == 3
    assert result.chord_mean_confidence == 0.9


def test_gate_on_falls_through_for_low_chord_confidence(monkeypatch):
    monkeypatch.setenv("HARMONIQ_CONFIDENCE_GATE", "1")
    _patch_mt3(monkeypatch, mean_confidence=0.9, chord_confidence=0.4)

    result = fallback._try_mt3("/tmp/x.wav", _beat_grid(), 0.7)

    assert result is not None
    assert result.chord_timeline.events == []
    assert result.fallback_reason == "mt3_gate_low_chord_confidence:0.40"
    assert result.chord_mean_confidence == pytest.approx(0.4)


def test_gate_on_rejects_all_no_chord_timeline(monkeypatch):
    monkeypatch.setenv("HARMONIQ_CONFIDENCE_GATE", "1")
    _patch_mt3(monkeypatch, mean_confidence=0.9, chord_confidence=0.4)
    monkeypatch.setattr(
        fallback,
        "decode_events_to_chord_timeline",
        lambda _stream, _grid, **_kwargs: ChordTimeline(
            events=[ChordEvent(timestamp=0.0, chord="N", confidence=1.0)]
        ),
    )

    result = fallback._try_mt3("/tmp/x.wav", _beat_grid(), 0.7)

    # One event is below the minimum chord-event count, so the existing
    # insufficient-chords path wins before the confidence gate.
    assert result is not None
    assert result.fallback_reason == "mt3_insufficient_chords:1"
