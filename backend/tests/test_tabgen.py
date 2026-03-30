from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import pytest

from app.pipeline_proof import NoteEvent
from app.schemas import LessonSectionStub
from app.tabgen import (
    TAB_ALT_CONFIDENCE_THRESHOLD,
    apply_tab_artifacts_to_sections,
    derive_section_confidence,
    generate_tab_artifacts_from_note_events,
)

gp = pytest.importorskip("guitarpro")


def _parse_gp5_from_base64(gp5_base64: str) -> "gp.Song":
    raw = base64.b64decode(gp5_base64.encode("ascii"))
    # On Windows, `NamedTemporaryFile(delete=True)` can keep the handle locked,
    # which may break downstream readers. Write to a non-locked temp path.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "proof.gp5"
        p.write_bytes(raw)
        return gp.parse(str(p))


def _count_pitched_beats(song: "gp.Song") -> int:
    pitched = 0
    for track in song.tracks:
        for measure in track.measures:
            for voice in measure.voices:
                for beat in voice.beats:
                    if beat.status.name == "normal" and beat.notes:
                        pitched += 1
    return pitched


def test_generate_full_and_skeleton_gp5_are_parseable_and_skeleton_filters_short_notes():
    bpm = 120.0
    # Beat 0 has an ornament-like short note; Beat 1 has a longer note.
    events = [
        NoteEvent(start_s=0.0, end_s=0.02, pitch_midi=64, amplitude=1.0),
        NoteEvent(start_s=60.0 / bpm, end_s=60.0 / bpm + 0.25, pitch_midi=67, amplitude=1.0),
    ]

    artifacts = generate_tab_artifacts_from_note_events(
        events,
        bpm=bpm,
        transcription_confidence=0.1,
    )

    assert "tab_full_gp5_base64" in artifacts
    assert "tab_skeleton_gp5_base64" in artifacts
    assert "tab_alt_position_gp5_base64" not in artifacts

    full_song = _parse_gp5_from_base64(artifacts["tab_full_gp5_base64"])
    skeleton_song = _parse_gp5_from_base64(artifacts["tab_skeleton_gp5_base64"])

    assert _count_pitched_beats(full_song) >= 1
    # Ornament-like short beat should be filtered out for skeleton.
    assert _count_pitched_beats(skeleton_song) < _count_pitched_beats(full_song)


def test_confidence_gating_omits_alt_gp5_when_transcription_confidence_is_low():
    bpm = 120.0
    events = [
        NoteEvent(start_s=0.0, end_s=0.25, pitch_midi=64, amplitude=1.0),
    ]

    artifacts = generate_tab_artifacts_from_note_events(
        events,
        bpm=bpm,
        transcription_confidence=TAB_ALT_CONFIDENCE_THRESHOLD - 0.05,
    )
    assert "tab_alt_position_gp5_base64" not in artifacts


def test_confidence_gating_includes_alt_gp5_when_transcription_confidence_is_high():
    bpm = 120.0
    events = [
        NoteEvent(start_s=0.0, end_s=0.25, pitch_midi=64, amplitude=1.0),
    ]

    artifacts = generate_tab_artifacts_from_note_events(
        events,
        bpm=bpm,
        transcription_confidence=TAB_ALT_CONFIDENCE_THRESHOLD + 0.05,
    )
    assert "tab_alt_position_gp5_base64" in artifacts


def test_apply_tab_artifacts_sets_approximate_flag_via_section_confidence():
    bpm = 120.0
    events = [
        NoteEvent(start_s=0.0, end_s=0.25, pitch_midi=64, amplitude=1.0),
    ]
    transcription_confidence = 0.1

    artifacts = generate_tab_artifacts_from_note_events(
        events,
        bpm=bpm,
        transcription_confidence=transcription_confidence,
    )

    sections = [LessonSectionStub(label="Solo", confidence=0.6)]
    out_sections = apply_tab_artifacts_to_sections(
        sections,
        transcription_confidence=transcription_confidence,
        tab_artifacts=artifacts,
    )
    sec = out_sections[0]

    assert sec.confidence == pytest.approx(derive_section_confidence(transcription_confidence))
    assert sec.confidence < 0.7

    dumped = sec.model_dump()
    assert "tab_alt_position_gp5_base64" not in dumped

