"""Tests for heuristic section-level playing-style detection."""

from __future__ import annotations

from app.mt3.schemas import Mt3Event, Mt3EventStream
from app.playing_style_detect import build_performance_profiles
from app.schemas import ChordEvent, ChordTimeline, LessonSectionStub, SoloNote, SoloNotes


def _section(index: int, start: float, end: float, label: str = "Verse") -> LessonSectionStub:
    return LessonSectionStub(
        label=label,
        start_time_seconds=start,
        end_time_seconds=end,
    )


def _strum_events() -> Mt3EventStream:
    events: list[Mt3Event] = []
    pitches = [40, 45, 50, 55, 59, 64]
    for i in range(4):
        t = i * 1.0
        for pitch in pitches:
            events.append(
                Mt3Event(
                    time=t,
                    pitch=pitch,
                    velocity=80,
                    program=25,
                    is_onset=True,
                    confidence=0.9,
                )
            )
            events.append(
                Mt3Event(
                    time=t + 0.4,
                    pitch=pitch,
                    velocity=80,
                    program=25,
                    is_onset=False,
                    is_offset=True,
                    confidence=0.9,
                )
            )
    return Mt3EventStream(events=events, audio_duration_s=10.0, mean_confidence=0.9)


def _lead_events() -> Mt3EventStream:
    events: list[Mt3Event] = []
    pitches = [64, 67, 69, 71, 74, 76, 79, 81, 83, 84]
    for i in range(30):
        t = i / 3.0
        pitch = pitches[i % len(pitches)]
        events.append(
            Mt3Event(
                time=t,
                pitch=pitch,
                velocity=90,
                program=25,
                is_onset=True,
                confidence=0.9,
            )
        )
        events.append(
            Mt3Event(
                time=t + 0.2,
                pitch=pitch,
                velocity=90,
                program=25,
                is_onset=False,
                is_offset=True,
                confidence=0.9,
            )
        )
    return Mt3EventStream(events=events, audio_duration_s=10.0, mean_confidence=0.9)


def _chord_timeline() -> ChordTimeline:
    return ChordTimeline(
        events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=4.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=6.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=8.0, chord="C:maj", confidence=0.9),
        ]
    )


def test_strummed_section_is_rhythm() -> None:
    section = _section(0, 0.0, 10.0)
    profiles, summary = build_performance_profiles(
        [section],
        chord_timeline=_chord_timeline(),
        solo_notes=SoloNotes(notes=[]),
        mt3_events=_strum_events(),
    )

    assert profiles[0].playing_style == "strummed"
    assert profiles[0].part_role == "rhythm"
    assert "strumming" in profiles[0].technique_tags
    assert summary.playing_style == "strummed"
    assert summary.part_role == "rhythm"


def test_monophonic_lead_section_is_lead_solo() -> None:
    section = _section(0, 0.0, 10.0, label="Solo")
    profiles, _ = build_performance_profiles(
        [section],
        chord_timeline=_chord_timeline(),
        solo_notes=SoloNotes(notes=[]),
        mt3_events=_lead_events(),
    )

    assert profiles[0].playing_style == "picked"
    assert profiles[0].part_role == "lead_solo"


def test_fingerpicked_chord_tones() -> None:
    section = _section(0, 0.0, 10.0)
    notes = [
        SoloNote(start_time=i * 0.75, duration=0.5, pitch=pitch, velocity=80)
        for i, pitch in enumerate([60, 64, 67, 60, 64, 67, 60, 64, 67, 60, 64, 67])
    ]
    profiles, _ = build_performance_profiles(
        [section],
        chord_timeline=_chord_timeline(),
        solo_notes=SoloNotes(notes=notes),
        mt3_events=None,
    )

    assert profiles[0].playing_style == "fingerpicked_arpeggiated"
    assert profiles[0].part_role == "chord_melody"
    assert "fingerpicking" in profiles[0].technique_tags


def test_technique_tags_flow_to_section() -> None:
    section = _section(0, 0.0, 4.0)
    notes = [
        SoloNote(
            start_time=i * 0.5,
            duration=0.3,
            pitch=64 + (i % 3),
            velocity=90,
            technique=["bend"] if i % 2 == 0 else ["vibrato"],
        )
        for i in range(6)
    ]
    profiles, _ = build_performance_profiles(
        [section],
        chord_timeline=_chord_timeline(),
        solo_notes=SoloNotes(notes=notes),
    )

    assert "bend" in profiles[0].technique_tags
    assert "vibrato" in profiles[0].technique_tags
    assert set(section.technique_tags) == set(profiles[0].technique_tags)


def test_empty_section_is_unknown() -> None:
    section = _section(0, 0.0, 10.0)
    profiles, summary = build_performance_profiles(
        [section],
        chord_timeline=None,
        solo_notes=None,
    )

    assert profiles[0].playing_style == "unknown"
    assert profiles[0].confidence == 0.0
    assert summary.playing_style == "unknown"


def test_summary_is_duration_weighted() -> None:
    sections = [
        _section(0, 0.0, 2.0),
        _section(1, 2.0, 12.0),
    ]
    profiles, summary = build_performance_profiles(
        sections,
        chord_timeline=_chord_timeline(),
        solo_notes=SoloNotes(notes=[]),
        mt3_events=_strum_events(),
    )

    assert profiles[0].playing_style == "strummed"
    assert summary.playing_style == "strummed"
    assert 0.0 <= summary.confidence <= 1.0
