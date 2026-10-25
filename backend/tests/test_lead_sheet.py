"""Commit 177: MIDI + lyrics -> lead-sheet MusicXML."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from app.lead_sheet import (
    LeadSheetInputError,
    build_lead_sheet_from_midi,
    tokenize_lyrics,
)
from app.schemas import ChordEvent, ChordTimeline

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "lead-sheet"
DTD_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "musicxml-dtd"
    / "musicxml31-partwise-combined.dtd"
)


def _fixture(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


def _lyrics() -> str:
    return (FIXTURE_DIR / "lyrics.txt").read_text(encoding="utf-8")


def _chords() -> ChordTimeline:
    return ChordTimeline(
        events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=1.0),
            ChordEvent(timestamp=2.0, chord="G:maj", confidence=1.0),
        ]
    )


def _parse_valid(xml: str) -> etree._Element:
    root = etree.fromstring(xml.encode("utf-8"))
    dtd = etree.DTD(str(DTD_FIXTURE))
    assert dtd.validate(root), dtd.error_log
    return root


class TestTokenizeLyrics:
    def test_splits_whitespace_and_hyphens(self):
        assert tokenize_lyrics("Hel-lo world") == ["Hel-", "-lo", "world"]

    def test_three_syllable_word_uses_middle_hyphens(self):
        assert tokenize_lyrics("hap-py-ness") == ["hap-", "-py-", "-ness"]

    def test_preserves_space_separated_syllable_markers(self):
        assert tokenize_lyrics("Hel- -lo world") == ["Hel-", "-lo", "world"]

    def test_empty_lyrics(self):
        assert tokenize_lyrics("   \n") == []


class TestLeadSheet:
    def test_fixture_produces_dtd_valid_musicxml_with_underlay(self):
        xml = build_lead_sheet_from_midi(
            _fixture("melody.mid"),
            _lyrics(),
            chord_timeline=_chords(),
            title="Fixture Lead Sheet",
            key_signature="C major",
        )
        root = _parse_valid(xml)

        texts = [el.text for el in root.findall(".//lyric/text")]
        assert texts == ["Hel", "lo", "world", "sing", "with", "me", "to", "day"]

        syllabics = [el.text for el in root.findall(".//lyric/syllabic")]
        assert syllabics[0] == "begin"
        assert syllabics[1] == "end"
        assert syllabics[2] == "single"
        assert syllabics[-2] == "begin"
        assert syllabics[-1] == "end"

        harmonies = root.findall(".//harmony")
        assert len(harmonies) == 2

        # Lead-sheet mode must not emit the full-score-only annotations.
        assert root.findall(".//frame") == []
        assert root.findall(".//dynamics") == []

        pitches = [
            (p.findtext("step"), p.findtext("octave"))
            for p in root.findall(".//note/pitch")
        ]
        assert pitches[0] == ("C", "4")
        assert pitches[-1] == ("C", "5")

    def test_default_track_selection_prefers_top_line(self):
        xml = build_lead_sheet_from_midi(
            _fixture("bass_and_melody.mid"),
            "one two three four five six seven eight",
        )
        root = _parse_valid(xml)
        first_pitch = root.find(".//note/pitch")
        assert first_pitch is not None
        assert first_pitch.findtext("step") == "C"
        assert first_pitch.findtext("octave") == "5"

    def test_explicit_track_index_selects_bass(self):
        xml = build_lead_sheet_from_midi(
            _fixture("bass_and_melody.mid"),
            "",
            melody_track_index=0,
        )
        root = _parse_valid(xml)
        first_pitch = root.find(".//note/pitch")
        assert first_pitch is not None
        assert first_pitch.findtext("octave") == "2"

    def test_empty_lyrics_still_produces_melody(self):
        xml = build_lead_sheet_from_midi(_fixture("melody.mid"), "")
        root = _parse_valid(xml)
        assert root.findall(".//lyric") == []
        assert len(root.findall(".//note/pitch")) >= 8

    def test_too_many_syllables_fails_loudly(self):
        with pytest.raises(LeadSheetInputError, match="syllables"):
            build_lead_sheet_from_midi(
                _fixture("melody.mid"),
                "one two three four five six seven eight nine",
            )

    def test_invalid_midi_fails_loudly(self):
        with pytest.raises(LeadSheetInputError, match="Could not parse MIDI"):
            build_lead_sheet_from_midi(b"not a midi file", "hello")
