"""MusicXML (score-partwise) from Guitar Pro song — proper note conversion."""

from __future__ import annotations

import io
import xml.sax.saxutils as xs
from typing import Any

import guitarpro as gp

GP_TICKS_PER_QUARTER = gp.Duration.quarterTime
DEFAULT_DIVISIONS = 480  # MusicXML divisions per quarter note


def _gp_ticks_to_divisions(gp_ticks: int, divisions: int = DEFAULT_DIVISIONS) -> int:
    """Map Guitar Pro duration units to MusicXML divisions."""
    if gp_ticks <= 0:
        return max(1, divisions // 16)
    return max(1, round(gp_ticks * divisions / GP_TICKS_PER_QUARTER))


def _midi_pitch_to_musicxml_step(pitch: int) -> tuple[str, int, str]:
    """Convert MIDI pitch to MusicXML pitch info (step, octave, alter)."""
    note_names = ["C", "D", "E", "F", "G", "A", "B"]
    octave = (pitch // 12) - 1
    step = note_names[pitch % 12]
    alter = 0
    return step, octave, alter


def _format_duration(divisions: int, divisions_per_quarter: int) -> tuple[int, int, int, int]:
    """Convert duration in divisions to MusicXML duration tuple (duration, dots, type, tuplet)."""
    quarter_divisions = divisions_per_quarter
    whole_divisions = quarter_divisions * 4

    type_map = [
        (whole_divisions, "whole"),
        (quarter_divisions * 3, "half"),
        (quarter_divisions * 2, "quarter"),
        (quarter_divisions, "eighth"),
        (quarter_divisions // 2, "16th"),
        (quarter_divisions // 4, "32nd"),
        (quarter_divisions // 8, "64th"),
    ]

    base_duration = 0
    note_type = "quarter"
    for divs, ntype in type_map:
        if divisions >= divs:
            base_duration = divs
            note_type = ntype
            break

    if base_duration == 0:
        base_duration = 1
        note_type = "64th"

    if divisions > base_duration:
        return divisions, 0, note_type, 1

    return base_duration, 0, note_type, 1


def song_to_musicxml_bytes(song: gp.Song) -> bytes:
    """Convert a Guitar Pro song to a MusicXML 3.1 document."""
    title = xs.escape((song.title or "").strip() or "Untitled")
    subtitle = xs.escape((song.subtitle or "").strip())
    composer = xs.escape((song.artist or "").strip())

    tempo = song.tempo if isinstance(song.tempo, int) and song.tempo > 0 else 120
    divisions = DEFAULT_DIVISIONS

    time_sig_numerator = 4
    time_sig_denominator = 4
    if song.signature and song.signature.numerator:
        time_sig_numerator = song.signature.numerator
        time_sig_denominator = song.signature.denominator or 4

    tracks = [t for t in song.tracks if not getattr(t, "isPercussionTrack", False)]
    if not tracks:
        tracks = [song.tracks[0]] if song.tracks else []

    part_id = "P1"
    part_name = "Guitar"
    if len(tracks) > 1:
        part_name = xs.escape(tracks[0].name or "Guitar")

    measures_xml = _generate_measures_xml(
        tracks[0] if tracks else None,
        tempo,
        time_sig_numerator,
        time_sig_denominator,
        divisions
    )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.1">
  <movement-title>{title}</movement-title>
  <identification>
    <encoding>
      <software>Harmoniq export</software>
    </encoding>
  </identification>
  <defaults>
    <scaling>
      <millimeters>7</millimeters>
      <tenths>40</tenths>
    </scaling>
  </defaults>
  <part-list>
    <score-part id="{part_id}">
      <part-name>{part_name}</part-name>
    </score-part>
  </part-list>
  <part id="{part_id}">
    <measure number="1">
      <attributes>
        <divisions>{divisions}</divisions>
        <time>
          <beats>{time_sig_numerator}</beats>
          <beat-type>{time_sig_denominator}</beat-type>
        </time>
        <clef>
          <sign>G</sign>
          <line>2</line>
        </clef>
      </attributes>
      <direction placement="above">
        <direction-type>
          <words font-weight="bold">{title}</words>
        </direction-type>
      </direction>
      {f'<direction placement="below"><direction-type><words>{subtitle}</words></direction-type></direction>' if subtitle else ''}
      {f'<direction placement="below"><direction-type><words>{composer}</words></direction-type></direction>' if composer else ''}
      <direction>
        <sound tempo="{60 * 1000000 / tempo}"/>
      </direction>
      {measures_xml}
    </measure>
  </part>
</score-partwise>
"""
    return xml.encode("utf-8")


def _generate_measures_xml(
    track: gp.Track | None,
    tempo: int,
    time_sig_numerator: int,
    time_sig_denominator: int,
    divisions: int
) -> str:
    """Generate MusicXML measure content from a GP track."""
    if not track:
        return "<note><rest/><duration>4</duration><type>whole</type></note>"

    measures_xml_parts = []
    current_measure_number = 1

    measure_duration_divisions = divisions * time_sig_numerator * (4 // time_sig_denominator)

    for measure in track.measures:
        measure_xml = _generate_measure_xml(
            measure,
            current_measure_number,
            measure_duration_divisions,
            divisions,
            current_measure_number == 1
        )
        measures_xml_parts.append(measure_xml)
        current_measure_number += 1

    if not measures_xml_parts:
        return "<note><rest/><duration>4</duration><type>whole</type></note>"

    return "\n      ".join(measures_xml_parts)


def _generate_measure_xml(
    measure: gp.Measure,
    measure_number: int,
    measure_duration_divisions: int,
    divisions: int,
    include_header: bool
) -> str:
    """Generate MusicXML for a single measure."""
    parts = []

    voice = measure.voices[0] if measure.voices else None
    if not voice:
        return f'<measure number="{measure_number}"><note><rest/><duration>{measure_duration_divisions}</duration><type>whole</type></note></measure>'

    current_tick = 0

    for beat in voice.beats:
        dur_gp = beat.duration.time
        dur_divisions = _gp_ticks_to_divisions(dur_gp, divisions)

        if beat.status in (gp.BeatStatus.empty, gp.BeatStatus.rest):
            current_tick += dur_divisions
            continue

        if not beat.notes:
            current_tick += dur_divisions
            continue

        for note in beat.notes:
            if note.type == gp.NoteType.tie:
                continue
            if note.type != gp.NoteType.normal:
                continue

            pitch = int(note.realValue)
            if pitch < 0 or pitch > 127:
                continue

            step, octave, alter = _midi_pitch_to_musicxml_step(pitch)

            vel_raw = getattr(note, "velocity", gp.Velocities.default)
            velocity = vel_raw if isinstance(vel_raw, int) else gp.Velocities.default
            velocity = max(1, min(127, velocity))

            dynamic = "mf"
            if velocity < 50:
                dynamic = "p"
            elif velocity < 80:
                dynamic = "mf"
            elif velocity < 100:
                dynamic = "f"
            else:
                dynamic = "ff"

            note_xml = f"""<note>
        <pitch>
          <step>{step}</step>
          <octave>{octave}</octave>
          <alter>{alter}</alter>
        </pitch>
        <duration>{dur_divisions}</duration>
        <type>{_format_duration(dur_divisions, divisions)[2]}</type>
        <velocity>{velocity * 127 // 127}</velocity>
      </note>"""
            parts.append(note_xml)

        current_tick += dur_divisions

    if not parts:
        return f'<measure number="{measure_number}"><note><rest/><duration>{measure_duration_divisions}</duration><type>whole</type></note></measure>'

    measure_content = "\n        ".join(parts)
    return f'<measure number="{measure_number}">\n        {measure_content}\n      </measure>'


def gp5_bytes_to_musicxml(gp5_bytes: bytes) -> bytes:
    """Convert GP5 bytes to MusicXML."""
    bio = io.BytesIO(gp5_bytes)
    song = gp.parse(bio)
    return song_to_musicxml_bytes(song)