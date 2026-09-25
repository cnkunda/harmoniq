"""Tests for Commit B8: MusicXML slash chord &lt;bass&gt; element emission.

Verifies:
- &lt;bass&gt; element present in MusicXML when bass differs from chord root
- &lt;bass&gt; absent for root-position chords
- &lt;bass-step&gt; contains correct note letter
- Backward compatibility: existing chord timeline without bass still works
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.musicxml_builder import build_musicxml
from app.schemas import (
    BeatGrid,
    ChordEvent,
    ChordTimeline,
    SoloNotes,
    SoloNote,
    TimeSignature,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_beat_grid(
    bpm: float = 120.0,
    time_sig_num: int = 4,
    time_sig_den: int = 4,
    n_measures: int = 2,
) -> BeatGrid:
    quarter_note_s = 60.0 / bpm
    measure_s = quarter_note_s * time_sig_num
    beats_per_measure = time_sig_num
    total_beats = n_measures * beats_per_measure
    beats = [i * quarter_note_s for i in range(total_beats + 1)]
    downbeats = [i * measure_s for i in range(n_measures + 1)]
    return BeatGrid(
        bpm=bpm,
        pulse_bpm=bpm,
        beats=beats,
        downbeats=downbeats,
        time_signature=TimeSignature(numerator=time_sig_num, denominator=time_sig_den),
        tick_value=1.0 / time_sig_den,
    )


def _empty_solo() -> SoloNotes:
    return SoloNotes(notes=[])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMusicXmlSlashChord:
    """Verify that <bass> element is emitted correctly for slash chords."""

    def _extract_harmony(self, musicxml: str) -> list[str]:
        """Extract <harmony>...</harmony> blocks from MusicXML."""
        return re.findall(r'<harmony>.*?</harmony>', musicxml, re.DOTALL)

    def _has_root_step(self, harmony: str, step: str) -> bool:
        """Check if a harmony block contains <root-step>step</root-step> (whitespace-tolerant)."""
        return bool(re.search(rf'<root-step>\s*{step}\s*</root-step>', harmony))

    def test_slash_chord_emits_bass_element(self):
        """C:maj with bass=E → MusicXML should contain <bass><bass-step>E</bass-step></bass>."""
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9, bass="E"),
        ])
        beat_grid = _make_beat_grid()
        musicxml = build_musicxml(beat_grid, timeline, _empty_solo())
        assert '<bass>' in musicxml, "Expected <bass> element for slash chord"
        assert '<bass-step>' in musicxml

    def test_root_position_no_bass_element(self):
        """C:maj with bass=None → MusicXML should NOT contain <bass>."""
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ])
        beat_grid = _make_beat_grid()
        musicxml = build_musicxml(beat_grid, timeline, _empty_solo())
        harmonies = self._extract_harmony(musicxml)
        for h in harmonies:
            if self._has_root_step(h, 'C'):
                assert '<bass>' not in h, f"Root-position harmony should not have <bass>: {h[:200]}"
                return
        pytest.fail("Could not find C:maj harmony in MusicXML output")

    def test_bass_equals_root_suppresses_slash(self):
        """C:maj with bass=C → should behave as root position, no <bass>."""
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9, bass="C"),
        ])
        beat_grid = _make_beat_grid()
        musicxml = build_musicxml(beat_grid, timeline, _empty_solo())
        harmonies = self._extract_harmony(musicxml)
        for h in harmonies:
            if self._has_root_step(h, 'C'):
                assert '<bass>' not in h, "Root-position chord (bass=root) should not emit <bass>"
                return

    def test_slash_bass_step_matches_note(self):
        """G:7 with bass=F → <bass-step> should be F."""
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="G:7", confidence=0.9, bass="F"),
        ])
        beat_grid = _make_beat_grid()
        musicxml = build_musicxml(beat_grid, timeline, _empty_solo())
        assert '<bass-step>' in musicxml
        assert 'F' in musicxml.split('<bass-step>')[1].split('</bass-step>')[0]

    def test_minor_slash_chord(self):
        """A:min with bass=G → <bass-step>G</bass-step>."""
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="A:min", confidence=0.9, bass="G"),
        ])
        beat_grid = _make_beat_grid()
        musicxml = build_musicxml(beat_grid, timeline, _empty_solo())
        assert '<bass-step>' in musicxml
        assert 'G' in musicxml.split('<bass-step>')[1].split('</bass-step>')[0]

    def test_n_chord_no_bass(self):
        """N (no-chord) should not emit any harmony."""
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="N", confidence=1.0),
        ])
        beat_grid = _make_beat_grid()
        musicxml = build_musicxml(beat_grid, timeline, _empty_solo())
        harmonies = self._extract_harmony(musicxml)
        # N chords are skipped in MusicXML output, so no harmony should contain N
        for h in harmonies:
            assert 'N' not in h

    def test_backward_compat_no_bass_field(self):
        """Existing ChordEvent without bass field should still produce valid MusicXML."""
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="G:7", confidence=0.85),
        ])
        beat_grid = _make_beat_grid()
        musicxml = build_musicxml(beat_grid, timeline, _empty_solo())
        assert '<root-step>C' in musicxml
        assert '<root-step>G' in musicxml
        # No <bass> should appear
        harmonies = self._extract_harmony(musicxml)
        for h in harmonies:
            assert '<bass>' not in h, "Backward-compat test should not emit <bass>"
