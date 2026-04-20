"""GP5 → Standard MIDI File (SMF type 1) via pyguitarpro + mido."""

from __future__ import annotations

import io

import guitarpro as gp
from mido import Message, MetaMessage, MidiFile, MidiTrack

MidiTicks = int

GP_TICKS_PER_QUARTER = gp.Duration.quarterTime


def _gp_ticks_to_midi(gp_ticks: int, ticks_per_quarter: int = 480) -> int:
    """Map Guitar Pro duration units (see `Duration.time`) to MIDI ticks."""
    if gp_ticks <= 0:
        return max(1, ticks_per_quarter // 16)
    return max(1, round(gp_ticks * ticks_per_quarter / GP_TICKS_PER_QUARTER))


def song_to_midi_bytes(song: gp.Song, *, ticks_per_quarter: int = 480) -> bytes:
    """Flatten non-percussion guitar/bass tracks into MIDI type 1."""
    mid = MidiFile(type=1, ticks_per_beat=ticks_per_quarter)

    tempo_track = MidiTrack()
    tempo = song.tempo if isinstance(song.tempo, int) and song.tempo > 0 else 120
    tempo_microseconds = max(1, round(60000000 / tempo))
    tempo_track.append(MetaMessage("set_tempo", tempo=tempo_microseconds, time=0))
    tempo_track.append(MetaMessage("track_name", name=song.title[:128] if song.title else "Harmoniq export", time=0))
    tempo_track.append(MetaMessage("time_signature", numerator=4, denominator=2, clocks_per_click=24, notated_32nd_notes_per_beat=8, time=0))
    tempo_track.append(MetaMessage("end_of_track", time=0))
    mid.tracks.append(tempo_track)

    for ti, track in enumerate(song.tracks):
        if getattr(track, "isPercussionTrack", False):
            continue

        channel = getattr(track.channel, "channel", ti)
        channel = max(0, min(15, int(channel))) & 15
        if channel == 9:
            channel = ti % 9

        program = max(0, min(127, int(getattr(track.channel, "instrument", 24))))
        name = (track.name or f"Track {ti + 1}")[:128]

        rows: list[tuple[MidiTicks, int, Message]] = []

        rows.append((0, 10, Message("program_change", channel=channel, program=program % 128)))

        abs_tick = 0
        for measure in track.measures:
            primary = measure.voices[0] if measure.voices else None
            if primary is None:
                continue
            for beat in primary.beats:
                dur_gp = beat.duration.time
                dur_midi = _gp_ticks_to_midi(dur_gp, ticks_per_quarter)

                if beat.status in (gp.BeatStatus.empty, gp.BeatStatus.rest):
                    abs_tick += dur_midi
                    continue

                notes_now: list[tuple[int, int]] = []
                for note in beat.notes:
                    if note.type == gp.NoteType.tie:
                        continue
                    if note.type != gp.NoteType.normal:
                        continue
                    pitch = int(note.realValue)
                    if pitch < 0 or pitch > 127:
                        continue
                    vel_raw = getattr(note, "velocity", gp.Velocities.default)
                    vel = vel_raw if isinstance(vel_raw, int) else gp.Velocities.default
                    vel = max(1, min(127, vel))
                    notes_now.append((pitch, vel))

                if not notes_now:
                    abs_tick += dur_midi
                    continue

                onset = abs_tick
                release = onset + dur_midi
                for pi, (pitch, vel) in enumerate(notes_now):
                    prio = 20 + pi * 4
                    rows.append((onset, prio, Message("note_on", channel=channel, note=pitch, velocity=vel, time=0)))
                    rows.append((release, prio + 1, Message("note_off", channel=channel, note=pitch, velocity=0, time=0)))

                abs_tick += dur_midi

        rows.sort(key=lambda r: (r[0], r[1]))

        mtr = MidiTrack()
        mtr.append(MetaMessage("track_name", name=name, time=0))
        last = 0
        for tick, _, msg in rows:
            dt = tick - last
            last = tick
            m = msg.copy(time=max(0, dt))
            mtr.append(m)

        mtr.append(MetaMessage("end_of_track", time=0))

        mid.tracks.append(mtr)

    buf = io.BytesIO()
    mid.save(file=buf)
    return buf.getvalue()


def gp5_bytes_to_midi(gp5_bytes: bytes) -> bytes:
    bio = io.BytesIO(gp5_bytes)
    song = gp.parse(bio)
    return song_to_midi_bytes(song)
