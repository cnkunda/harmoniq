"""Rhythm-chart generation for section tabs (F3).

Builds a strum-based rhythm track from the chord timeline and can merge it into
the lead tab as a second Guitar Pro track, giving a genuine lead + rhythm score.
"""
from __future__ import annotations

import base64
import io
import tempfile
from collections.abc import Sequence
from pathlib import Path

from app.chord_vocab import CHORD_INTERVALS, ROOT_NOTES
from app.fretting import Position, candidates_for_pitch, standard
from app.pipeline_proof import beat_slot_index_for_time

_RHYTHM_MAX_FRET = 12
_RHYTHM_MAX_NOTES = 4


def _parse_chord(chord: str) -> tuple[int, list[int]] | None:
    """Return ``(root_pc, intervals)`` for ``C:maj``-style ids."""
    if not chord or chord == "N" or ":" not in chord:
        return None
    root, quality = chord.split(":", 1)
    if root not in ROOT_NOTES:
        return None
    intervals = CHORD_INTERVALS.get(quality)
    if not intervals:
        return None
    return ROOT_NOTES.index(root), intervals


def chord_positions(chord: str) -> list[Position]:
    """Pick a compact playable voicing (distinct strings, low frets)."""
    parsed = _parse_chord(chord)
    if parsed is None:
        return []
    root_pc, intervals = parsed
    tuning = standard()
    used_strings: set[int] = set()
    positions: list[Position] = []
    for interval in intervals[:_RHYTHM_MAX_NOTES]:
        pitch_class = (root_pc + interval) % 12
        best: tuple[tuple[int, int], Position] | None = None
        for octave in range(3):  # C3..B4
            midi = 48 + pitch_class + octave * 12
            for candidate in candidates_for_pitch(midi, tuning, max_fret=_RHYTHM_MAX_FRET):
                if candidate.string in used_strings:
                    continue
                score = (candidate.fret, candidate.string)
                if best is None or score < best[0]:
                    best = (score, candidate)
        if best is not None:
            positions.append(best[1])
            used_strings.add(best[1].string)
    return sorted(positions, key=lambda p: p.string)


def _chord_by_slot(
    chord_events: Sequence[tuple[float, str]],
    *,
    bpm: float,
    beat_times_s: Sequence[float] | None,
) -> dict[int, str]:
    by_slot: dict[int, str] = {}
    for timestamp, chord in chord_events:
        if not chord or chord == "N":
            continue
        slot = beat_slot_index_for_time(float(timestamp), beat_times_s, bpm=bpm)
        by_slot[slot] = chord
    return by_slot


def build_rhythm_song(
    chord_events: Sequence[tuple[float, str]],
    *,
    bpm: float,
    beat_times_s: Sequence[float] | None = None,
    title: str = "Harmoniq rhythm",
):
    """Create a single-track Guitar Pro song with one strum per chord change."""
    import guitarpro as gp

    by_slot = _chord_by_slot(chord_events, bpm=bpm, beat_times_s=beat_times_s)
    max_slot = max(by_slot, default=-1)
    n_measures = max_slot // 4 + 1 if max_slot >= 0 else 1

    song = gp.Song(title=title, artist="", tempo=int(round(bpm)), tempoName="Moderate")
    track = song.tracks[0]
    track.name = "Rhythm"
    track.channel.instrument = 27  # GM Electric Guitar (clean)

    song.measureHeaders.clear()
    track.measures.clear()
    for _ in range(n_measures):
        header = gp.MeasureHeader()
        song.measureHeaders.append(header)
        track.measures.append(gp.Measure(track, header))

    for mi, measure in enumerate(track.measures):
        voice = measure.voices[0]
        for slot_in_bar in range(4):
            slot = mi * 4 + slot_in_bar
            chord = by_slot.get(slot)
            if chord:
                positions = chord_positions(chord)
                beat = gp.Beat(
                    voice=voice,
                    duration=gp.Duration(gp.Duration.quarter),
                    status=gp.BeatStatus.normal,
                )
                for position in positions:
                    beat.notes.append(
                        gp.Note(
                            beat=beat,
                            string=position.string,
                            value=position.fret,
                            type=gp.NoteType.normal,
                        )
                    )
                voice.beats.append(beat if beat.notes else gp.Beat(
                    voice=voice,
                    duration=gp.Duration(gp.Duration.quarter),
                    status=gp.BeatStatus.rest,
                ))
            else:
                voice.beats.append(
                    gp.Beat(
                        voice=voice,
                        duration=gp.Duration(gp.Duration.quarter),
                        status=gp.BeatStatus.rest,
                    )
                )
    return song


def build_rhythm_gp5_base64(
    chord_events: Sequence[tuple[float, str]],
    *,
    bpm: float,
    beat_times_s: Sequence[float] | None = None,
    title: str = "Harmoniq rhythm",
) -> str:
    import guitarpro as gp

    song = build_rhythm_song(chord_events, bpm=bpm, beat_times_s=beat_times_s, title=title)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "rhythm.gp5"
        gp.write(song, str(path))
        return base64.b64encode(path.read_bytes()).decode("ascii")


def merge_rhythm_into_gp5(
    lead_gp5_bytes: bytes,
    chord_events: Sequence[tuple[float, str]],
    *,
    bpm: float,
    beat_times_s: Sequence[float] | None = None,
) -> bytes:
    """Add a rhythm track to an existing lead tab and return the new GP5 bytes."""
    import guitarpro as gp

    with tempfile.TemporaryDirectory() as td:
        in_path = Path(td) / "lead.gp5"
        out_path = Path(td) / "lead_rhythm.gp5"
        in_path.write_bytes(lead_gp5_bytes)
        song = gp.parse(str(in_path))
        title = song.title or "Harmoniq"

        rhythm = build_rhythm_song(
            chord_events,
            bpm=bpm,
            beat_times_s=beat_times_s,
            title=title,
        )
        rhythm_track = rhythm.tracks[0]
        rhythm_track.song = song
        rhythm_track.number = len(song.tracks) + 1
        # Keep the standalone measures before re-parenting the track to the lead
        # song's headers so both tracks share bar boundaries.
        source_measures = list(rhythm_track.measures)
        rhythm_track.measures = [gp.Measure(rhythm_track, header) for header in song.measureHeaders]
        for mi, target_measure in enumerate(rhythm_track.measures):
            target_voice = target_measure.voices[0]
            if mi < len(source_measures):
                source_voice = source_measures[mi].voices[0]
                for beat in source_voice.beats:
                    new_beat = gp.Beat(
                        voice=target_voice,
                        duration=beat.duration,
                        status=beat.status,
                    )
                    for note in beat.notes:
                        new_beat.notes.append(
                            gp.Note(
                                beat=new_beat,
                                string=note.string,
                                value=note.value,
                                type=note.type,
                            )
                        )
                    target_voice.beats.append(new_beat)
            if not target_voice.beats:
                for _ in range(4):
                    target_voice.beats.append(
                        gp.Beat(
                            voice=target_voice,
                            duration=gp.Duration(gp.Duration.quarter),
                            status=gp.BeatStatus.rest,
                        )
                    )
        song.tracks.append(rhythm_track)
        gp.write(song, str(out_path))
        return out_path.read_bytes()
