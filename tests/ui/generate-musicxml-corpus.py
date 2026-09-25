#!/usr/bin/env python3
"""Generate edge-case MusicXML corpus for AlphaTab rendering tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.schemas import (
    BeatGrid,
    ChordEvent,
    ChordTimeline,
    SoloNote,
    SoloNotes,
    TimeSignature,
)
from app.musicxml_builder import build_musicxml

CORPUS_DIR = Path(__file__).resolve().parent / "musicxml-corpus"


def make_beat_grid(
    bpm: float,
    num_beats: int,
    num_divisions: int = 4,
    numerator: int = 4,
    denominator: int = 4,
) -> BeatGrid:
    beat_duration = 60.0 / bpm
    tick = beat_duration / num_divisions
    beats = [round(i * tick, 6) for i in range(num_beats * num_divisions)]
    downbeats = [beats[i] for i in range(0, len(beats), num_divisions)]
    return BeatGrid(
        bpm=bpm,
        beats=beats,
        downbeats=downbeats,
        time_signature=TimeSignature(numerator=numerator, denominator=denominator),
        tick_value=tick,
    )


def write_musicxml(name: str, musicxml: str) -> None:
    path = CORPUS_DIR / f"{name}.musicxml"
    path.write_text(musicxml, encoding="utf-8")
    print(f"  {name}.musicxml")


def gen_basic_c_major() -> str:
    bg = make_beat_grid(120, 2)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)])
    sn = SoloNotes(notes=[SoloNote(start_time=0.0, duration=0.5, pitch=60, velocity=100)])
    return build_musicxml(bg, ct, sn, title="Basic C Major", key_signature="C major")


def gen_a_minor_key() -> str:
    bg = make_beat_grid(100, 2)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="A:min", confidence=0.85)])
    sn = SoloNotes(notes=[SoloNote(start_time=0.0, duration=0.5, pitch=57, velocity=90)])
    return build_musicxml(bg, ct, sn, title="A Minor Key", key_signature="A minor")


def gen_5_4_time() -> str:
    bg = make_beat_grid(120, 5, numerator=5, denominator=4)
    ct = ChordTimeline(events=[
        ChordEvent(timestamp=0.0, chord="D:min", confidence=0.8),
        ChordEvent(timestamp=2.5, chord="G:maj", confidence=0.75),
    ])
    sn = SoloNotes(notes=[
        SoloNote(start_time=0.0, duration=0.5, pitch=62, velocity=90),
        SoloNote(start_time=2.5, duration=0.5, pitch=67, velocity=85),
    ])
    return build_musicxml(bg, ct, sn, title="5/4 Time Signature", key_signature="D minor")


def gen_7_8_time() -> str:
    bg = make_beat_grid(80, 7, numerator=7, denominator=8)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="E:min", confidence=0.7)])
    sn = SoloNotes(notes=[
        SoloNote(start_time=0.0, duration=0.375, pitch=64, velocity=80),
        SoloNote(start_time=0.75, duration=0.375, pitch=67, velocity=85),
        SoloNote(start_time=1.5, duration=0.375, pitch=71, velocity=90),
    ])
    return build_musicxml(bg, ct, sn, title="7/8 Time Signature", key_signature="E minor")


def gen_6_8_time() -> str:
    bg = make_beat_grid(80, 6, numerator=6, denominator=8)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="F:maj", confidence=0.85)])
    sn = SoloNotes(notes=[
        SoloNote(start_time=0.0, duration=0.5, pitch=65, velocity=80),
        SoloNote(start_time=1.5, duration=0.5, pitch=69, velocity=85),
    ])
    return build_musicxml(bg, ct, sn, title="6/8 Time Signature", key_signature="F major")


def gen_3_4_time() -> str:
    bg = make_beat_grid(100, 3, numerator=3, denominator=4)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="Bb:maj", confidence=0.8)])
    sn = SoloNotes(notes=[
        SoloNote(start_time=0.0, duration=0.6, pitch=58, velocity=90),
        SoloNote(start_time=0.6, duration=0.6, pitch=62, velocity=85),
        SoloNote(start_time=1.2, duration=0.6, pitch=65, velocity=80),
    ])
    return build_musicxml(bg, ct, sn, title="3/4 Waltz Time", key_signature="Bb major")


def gen_sixteenth_notes() -> str:
    bg = make_beat_grid(100, 4, num_divisions=4)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)])
    notes = []
    for i in range(16):
        t = i * (60.0 / 100 / 4)
        notes.append(SoloNote(start_time=round(t, 4), duration=0.075, pitch=60 + (i % 12), velocity=80 + (i % 20)))
    sn = SoloNotes(notes=notes)
    return build_musicxml(bg, ct, sn, title="16th Note Run", key_signature="C major")


def gen_dotted_rhythms() -> str:
    bg = make_beat_grid(120, 4)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="G:maj", confidence=0.85)])
    sn = SoloNotes(notes=[
        SoloNote(start_time=0.0, duration=0.75, pitch=67, velocity=100),  # dotted quarter
        SoloNote(start_time=0.75, duration=0.25, pitch=69, velocity=80),   # eighth
        SoloNote(start_time=1.0, duration=0.75, pitch=71, velocity=90),    # dotted quarter
        SoloNote(start_time=1.75, duration=0.25, pitch=72, velocity=75),   # eighth
    ])
    return build_musicxml(bg, ct, sn, title="Dotted Rhythms", key_signature="G major")


def gen_chord_progression() -> str:
    bg = make_beat_grid(90, 8)
    ct = ChordTimeline(events=[
        ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ChordEvent(timestamp=2.0, chord="A:min", confidence=0.85),
        ChordEvent(timestamp=4.0, chord="F:maj", confidence=0.88),
        ChordEvent(timestamp=6.0, chord="G:maj", confidence=0.82),
    ])
    sn = SoloNotes(notes=[])
    return build_musicxml(bg, ct, sn, title="I-vi-IV-V Progression", key_signature="C major")


def gen_jazz_extensions() -> str:
    bg = make_beat_grid(80, 8)
    ct = ChordTimeline(events=[
        ChordEvent(timestamp=0.0, chord="C:maj7", confidence=0.8),
        ChordEvent(timestamp=2.0, chord="D:min7", confidence=0.75),
        ChordEvent(timestamp=4.0, chord="E:min7", confidence=0.7),
        ChordEvent(timestamp=6.0, chord="A7", confidence=0.72),
    ])
    sn = SoloNotes(notes=[
        SoloNote(start_time=0.0, duration=0.75, pitch=64, velocity=80),
        SoloNote(start_time=2.0, duration=0.75, pitch=65, velocity=85),
        SoloNote(start_time=4.0, duration=0.75, pitch=67, velocity=90),
        SoloNote(start_time=6.0, duration=0.75, pitch=69, velocity=80),
    ])
    return build_musicxml(bg, ct, sn, title="Jazz 7th Chords", key_signature="C major")


def gen_blues_12bar() -> str:
    bg = make_beat_grid(120, 16)
    ct = ChordTimeline(events=[
        ChordEvent(timestamp=0.0, chord="E:min7", confidence=0.85),
        ChordEvent(timestamp=2.0, chord="E:min7", confidence=0.85),
        ChordEvent(timestamp=4.0, chord="E:min7", confidence=0.85),
        ChordEvent(timestamp=6.0, chord="E:min7", confidence=0.85),
        ChordEvent(timestamp=8.0, chord="A:min7", confidence=0.80),
        ChordEvent(timestamp=10.0, chord="A:min7", confidence=0.80),
        ChordEvent(timestamp=12.0, chord="E:min7", confidence=0.85),
        ChordEvent(timestamp=14.0, chord="E:min7", confidence=0.85),
    ])
    sn = SoloNotes(notes=[
        SoloNote(start_time=0.0, duration=0.25, pitch=64, velocity=90),
        SoloNote(start_time=0.25, duration=0.25, pitch=67, velocity=85),
        SoloNote(start_time=0.5, duration=0.5, pitch=71, velocity=95),
    ])
    return build_musicxml(bg, ct, sn, title="12-Bar Blues", key_signature="E minor")


def gen_fast_tempo() -> str:
    bg = make_beat_grid(200, 4)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="D:maj", confidence=0.9)])
    sn = SoloNotes(notes=[
        SoloNote(start_time=0.0, duration=0.15, pitch=74, velocity=100),
        SoloNote(start_time=0.15, duration=0.15, pitch=76, velocity=95),
        SoloNote(start_time=0.3, duration=0.15, pitch=78, velocity=90),
        SoloNote(start_time=0.45, duration=0.15, pitch=80, velocity=85),
    ])
    return build_musicxml(bg, ct, sn, title="Fast Tempo 200 BPM", key_signature="D major")


def gen_slow_tempo() -> str:
    bg = make_beat_grid(40, 4)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="Eb:maj", confidence=0.88)])
    sn = SoloNotes(notes=[
        SoloNote(start_time=0.0, duration=3.0, pitch=63, velocity=60),
        SoloNote(start_time=3.0, duration=1.5, pitch=67, velocity=70),
    ])
    return build_musicxml(bg, ct, sn, title="Slow Tempo 40 BPM", key_signature="Eb major")


def gen_many_chords() -> str:
    bg = make_beat_grid(120, 16)
    chords = ["C:maj", "D:min", "E:min", "F:maj", "G:maj", "A:min", "B:dim"]
    ct = ChordTimeline(events=[
        ChordEvent(timestamp=i * 2.0, chord=chords[i % len(chords)], confidence=0.7 + (i % 3) * 0.1)
        for i in range(8)
    ])
    sn = SoloNotes(notes=[])
    return build_musicxml(bg, ct, sn, title="7 Chord Types", key_signature="C major")


def gen_sharps_key() -> str:
    bg = make_beat_grid(110, 4)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="F#:min", confidence=0.75)])
    sn = SoloNotes(notes=[SoloNote(start_time=0.0, duration=0.5, pitch=66, velocity=85)])
    return build_musicxml(bg, ct, sn, title="F# Minor (3 sharps)", key_signature="F# minor")


def gen_flats_key() -> str:
    bg = make_beat_grid(105, 4)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="Ab:maj", confidence=0.8)])
    sn = SoloNotes(notes=[SoloNote(start_time=0.0, duration=0.5, pitch=56, velocity=80)])
    return build_musicxml(bg, ct, sn, title="Ab Major (4 flats)", key_signature="Ab major")


def gen_empty_solo() -> str:
    bg = make_beat_grid(120, 4)
    ct = ChordTimeline(events=[
        ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ChordEvent(timestamp=2.0, chord="G:maj", confidence=0.85),
    ])
    sn = SoloNotes(notes=[])
    return build_musicxml(bg, ct, sn, title="Chords Only (No Solo)", key_signature="C major")


def gen_many_rests() -> str:
    bg = make_beat_grid(120, 4)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)])
    sn = SoloNotes(notes=[
        SoloNote(start_time=0.0, duration=0.25, pitch=60, velocity=100),
        # 3.75 beats of rest
    ])
    return build_musicxml(bg, ct, sn, title="Mostly Rests", key_signature="C major")


def gen_high_notes() -> str:
    bg = make_beat_grid(120, 2)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)])
    sn = SoloNotes(notes=[
        SoloNote(start_time=0.0, duration=0.5, pitch=96, velocity=100),  # C7
        SoloNote(start_time=0.5, duration=0.5, pitch=100, velocity=95),  # E7
    ])
    return build_musicxml(bg, ct, sn, title="High Register Notes", key_signature="C major")


def gen_low_notes() -> str:
    bg = make_beat_grid(120, 2)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)])
    sn = SoloNotes(notes=[
        SoloNote(start_time=0.0, duration=0.5, pitch=36, velocity=100),  # C2
        SoloNote(start_time=0.5, duration=0.5, pitch=40, velocity=95),  # E2
    ])
    return build_musicxml(bg, ct, sn, title="Low Register Notes", key_signature="C major")


def gen_wide_dynamic_range() -> str:
    bg = make_beat_grid(120, 4)
    ct = ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)])
    sn = SoloNotes(notes=[
        SoloNote(start_time=0.0, duration=0.5, pitch=60, velocity=10),   # pp
        SoloNote(start_time=0.5, duration=0.5, pitch=62, velocity=40),   # p
        SoloNote(start_time=1.0, duration=0.5, pitch=64, velocity=70),   # mf
        SoloNote(start_time=1.5, duration=0.5, pitch=65, velocity=100),  # f
        SoloNote(start_time=2.0, duration=0.5, pitch=67, velocity=120),  # ff
    ])
    return build_musicxml(bg, ct, sn, title="Wide Dynamic Range", key_signature="C major")


def gen_sequential_chords_fast() -> str:
    bg = make_beat_grid(120, 8)
    ct = ChordTimeline(events=[
        ChordEvent(timestamp=i * 1.0, chord=["C:maj", "D:min", "E:min", "F:maj"][i % 4], confidence=0.8)
        for i in range(8)
    ])
    sn = SoloNotes(notes=[])
    return build_musicxml(bg, ct, sn, title="Fast Chord Changes", key_signature="C major")


def gen_minimal() -> str:
    bg = make_beat_grid(120, 1)
    ct = ChordTimeline(events=[])
    sn = SoloNotes(notes=[])
    return build_musicxml(bg, ct, sn, title="Minimal (Empty)", key_signature="C major")


GENERATORS = [
    ("01-basic-c-major", gen_basic_c_major),
    ("02-a-minor-key", gen_a_minor_key),
    ("03-5-4-time", gen_5_4_time),
    ("04-7-8-time", gen_7_8_time),
    ("05-6-8-time", gen_6_8_time),
    ("06-3-4-waltz", gen_3_4_time),
    ("07-sixteenth-notes", gen_sixteenth_notes),
    ("08-dotted-rhythms", gen_dotted_rhythms),
    ("09-chord-progression", gen_chord_progression),
    ("10-jazz-extensions", gen_jazz_extensions),
    ("11-blues-12bar", gen_blues_12bar),
    ("12-fast-tempo-200", gen_fast_tempo),
    ("13-slow-tempo-40", gen_slow_tempo),
    ("14-many-chords", gen_many_chords),
    ("15-sharps-key", gen_sharps_key),
    ("16-flats-key", gen_flats_key),
    ("17-empty-solo", gen_empty_solo),
    ("18-many-rests", gen_many_rests),
    ("19-high-notes", gen_high_notes),
    ("20-low-notes", gen_low_notes),
    ("21-dynamic-range", gen_wide_dynamic_range),
    ("22-fast-chord-changes", gen_sequential_chords_fast),
    ("23-minimal", gen_minimal),
]


def main() -> None:
    print("Generating MusicXML edge-case corpus...")
    for name, gen_fn in GENERATORS:
        try:
            xml = gen_fn()
            write_musicxml(name, xml)
        except Exception as e:
            print(f"  FAILED {name}: {e}")
    print(f"Done. {len(GENERATORS)} files generated.")


if __name__ == "__main__":
    main()
