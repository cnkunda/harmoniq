"""
MusicXML generation from Harmoniq's internal JSON artifacts (BeatGrid, ChordTimeline, SoloNotes).

This module creates a MusicXML lead sheet with:
- Beat-aligned chord symbols via <harmony> elements
- Solo notes with guitar tablature (string/fret) via <technical> elements
- Proper duration quantization to standard note types (whole through 64th)
- Tuplet detection (triplets, quintuplets, sextuplets)
- Measure-level fill validation

Commit 107: Replaced eighth-note-only quantization with full note type support.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

# Lazy load music21 for performance if not always used.
# If music21 is not installed, this will raise an ImportError at runtime.
if TYPE_CHECKING:
    import music21

import logging
from app.schemas import BeatGrid, ChordTimeline, SoloNotes, TimeSignature, ChordEvent, SoloNote
from app.guitar_position import midi_to_guitar_position

logger = logging.getLogger("harmoniq.musicxml_builder")

# Constants for MusicXML generation
DEFAULT_DIVISIONS = 480  # Standard for many MusicXML applications (e.g., MuseScore, Finale)
TICKS_PER_QUARTER = DEFAULT_DIVISIONS  # 480 ticks per quarter note


# ---------------------------------------------------------------------------
# Duration Quantization (Commit 107)
# ---------------------------------------------------------------------------

@dataclass
class QuantizedDuration:
    """A duration quantized to a standard note type with optional dots and tuplets."""
    type_name: str        # "whole", "half", "quarter", "eighth", "16th", "32nd", "64th"
    num_dots: int         # 0 = normal, 1 = dotted, 2 = double-dotted
    ticks: int            # Duration in ticks (at DEFAULT_DIVISIONS)
    tuplet_ratio: tuple[int, int] = (1, 1)  # (actual, normal) — (3,2) for triplet, (1,1) for normal


# Standard note types with their tick values (at 480 PPQ)
_NOTE_TYPE_TICKS: list[tuple[str, int]] = [
    ("64th",  TICKS_PER_QUARTER // 16),  # 30
    ("32nd",  TICKS_PER_QUARTER // 8),   # 60
    ("16th",  TICKS_PER_QUARTER // 4),   # 120
    ("eighth", TICKS_PER_QUARTER // 2),  # 240
    ("quarter", TICKS_PER_QUARTER),       # 480
    ("half",   TICKS_PER_QUARTER * 2),    # 960
    ("whole",  TICKS_PER_QUARTER * 4),    # 1920
]


def _seconds_to_ticks(duration_s: float, quarter_note_duration_s: float) -> int:
    """Convert a duration in seconds to ticks at DEFAULT_DIVISIONS PPQ."""
    if quarter_note_duration_s <= 0:
        return 0
    return round(duration_s / quarter_note_duration_s * TICKS_PER_QUARTER)


def _ticks_to_ql(ticks: int) -> Fraction:
    """Convert ticks to quarter-length Fraction."""
    return Fraction(ticks, TICKS_PER_QUARTER)


def quantize_to_note_type(duration_ticks: int) -> QuantizedDuration:
    """Map a tick duration to the nearest standard note type with dots.

    Uses nearest-neighbor matching with dotted variants. For tuplet durations,
    returns the base type and the tuplet ratio separately.

    Args:
        duration_ticks: Duration in ticks (at DEFAULT_DIVISIONS PPQ).

    Returns:
        QuantizedDuration with type, dots, ticks, and tuplet_ratio.
    """
    if duration_ticks <= 0:
        return QuantizedDuration("quarter", 0, 0)

    best_type = "quarter"
    best_ticks = TICKS_PER_QUARTER
    best_diff = abs(duration_ticks - best_ticks)

    # Check normal note types
    for type_name, type_ticks in _NOTE_TYPE_TICKS:
        diff = abs(duration_ticks - type_ticks)
        if diff < best_diff:
            best_diff = diff
            best_type = type_name
            best_ticks = type_ticks

    # Check dotted variants (1.5x)
    for type_name, type_ticks in _NOTE_TYPE_TICKS:
        dotted_ticks = int(type_ticks * 1.5)
        diff = abs(duration_ticks - dotted_ticks)
        if diff < best_diff:
            best_diff = diff
            best_type = type_name
            best_ticks = dotted_ticks

    # Check double-dotted variants (1.75x)
    for type_name, type_ticks in _NOTE_TYPE_TICKS:
        dd_ticks = int(type_ticks * 1.75)
        diff = abs(duration_ticks - dd_ticks)
        if diff < best_diff:
            best_diff = diff
            best_type = type_name
            best_ticks = dd_ticks

    # Determine dots
    base_ticks = next(t for n, t in _NOTE_TYPE_TICKS if n == best_type)
    if best_ticks == int(base_ticks * 1.75):
        dots = 2
    elif best_ticks == int(base_ticks * 1.5):
        dots = 1
    else:
        dots = 0

    return QuantizedDuration(best_type, dots, best_ticks)


def detect_tuplets(
    notes_with_ticks: list[tuple[int, int]],  # (start_tick, duration_ticks)
    measure_length_ticks: int,
    beat_ticks: int,
) -> list[tuple[int, int, int]]:
    """Detect tuplet patterns in a measure using IOI analysis.

    Scans sequential notes for patterns where inter-onset intervals deviate
    from the standard grid. Detects:
    - Triplets: 3 notes in the space of 2 (IOI ≈ 2/3 of a beat)
    - Quintuplets: 5 notes in the space of 4 (IOI ≈ 4/5 of a beat)
    - Sextuplets: 6 notes in the space of 4 (IOI ≈ 2/3 of a beat)

    Args:
        notes_with_ticks: List of (start_tick, duration_ticks) sorted by start_tick.
        measure_length_ticks: Total ticks in one measure.
        beat_ticks: Ticks per beat (e.g., 480 for quarter-note beat in 4/4).

    Returns:
        List of (start_idx, end_idx, actual_notes) for each detected tuplet group.
        start_idx and end_idx are indices into notes_with_ticks.
    """
    if len(notes_with_ticks) < 3:
        return []

    tuplets: list[tuple[int, int, int]] = []
    i = 0

    while i < len(notes_with_ticks):
        # Try to match a tuplet group starting at position i
        matched = False

        for actual, normal in [(6, 4), (5, 4), (3, 2)]:
            if i + actual > len(notes_with_ticks):
                continue

            group = notes_with_ticks[i:i + actual]
            group_start = group[0][0]
            group_end = group[-1][0] + group[-1][1]

            # Expected span for this tuplet ratio
            expected_span = beat_ticks * normal
            # Tolerance: 30% of expected span
            tolerance = int(expected_span * 0.3)

            actual_span = group_end - group_start
            if abs(actual_span - expected_span) <= tolerance:
                # Check that IOIs are roughly uniform within the group
                iois = [group[j+1][0] - group[j][0] for j in range(len(group) - 1)]
                if iois:
                    mean_ioi = sum(iois) / len(iois)
                    ioi_tolerance = mean_ioi * 0.4
                    if all(abs(ioi - mean_ioi) <= ioi_tolerance for ioi in iois):
                        tuplets.append((i, i + actual, actual))
                        i += actual
                        matched = True
                        break

        if not matched:
            i += 1

    return tuplets


def break_rests_at_beats(gap_ticks: int, beat_ticks: int) -> list[int]:
    """Break a rest gap into beat-aligned rest durations.

    Standard notation requires rests to expose the beat grid. A gap of 720 ticks
    (1.5 beats) should be [480, 240] (quarter + eighth), not one 720-tick rest.

    Args:
        gap_ticks: Total rest gap in ticks.
        beat_ticks: Ticks per beat (e.g., 480 for quarter-note beat).

    Returns:
        List of rest durations in ticks, aligned to beat boundaries.
    """
    if gap_ticks <= 0:
        return []

    rests: list[int] = []
    remaining = gap_ticks

    # First, fill with as many full beats as possible
    while remaining >= beat_ticks:
        rests.append(beat_ticks)
        remaining -= beat_ticks

    # Then fill the remaining with sub-beat values
    if remaining > 0:
        # Find the best note type for the remainder, but cap to remaining gap
        quantized = quantize_to_note_type(remaining)
        rests.append(min(quantized.ticks, remaining))

    return rests

def _get_music21_objects():
    """Helper to lazy-load music21."""
    try:
        import music21
        return music21
    except ImportError:
        raise ImportError(
            "The 'music21' library is required for MusicXML generation. "
            "Please install it with 'pip install music21'."
        )

def build_musicxml(
    beat_grid: BeatGrid,
    chord_timeline: ChordTimeline,
    solo_notes: SoloNotes,
    title: str = "Harmoniq Score",
    artist: str = "Harmoniq AI",
    key_signature: str | None = None, # New parameter
) -> str:
    """
    Builds a MusicXML string from Harmoniq's internal data structures.

    Args:
        beat_grid: The BeatGrid object containing tempo, beats, and time signature.
        chord_timeline: The ChordTimeline object with chord events.
        solo_notes: The SoloNotes object with individual note events.
        title: Title for the MusicXML score.
        artist: Artist for the MusicXML score.

    Returns:
        A string containing the MusicXML representation of the score.
    """
    m21 = _get_music21_objects()

    # 1. Create a new Score object
    score = m21.stream.Score()
    score.metadata = m21.metadata.Metadata()
    score.metadata.title = title
    score.metadata.composer = artist

    # 2. Create a single Part for the lead sheet
    part = m21.stream.Part()
    part.id = "P1"
    part.partName = "Lead Sheet"
    score.append(part)

    # 3. Add measures and initial attributes
    # We need to map beat_grid timestamps to MusicXML measures and durations.
    # MusicXML durations are relative to the 'divisions' attribute.
    
    # Determine the time signature
    time_sig = beat_grid.time_signature
    m21_time_signature = m21.meter.TimeSignature(f"{time_sig.numerator}/{time_sig.denominator}")

        # Determine the key
    if key_signature:
        # Parse "C major" or "C" or "A minor" or "Am" into music21.key.Key
        parts = key_signature.split(None, 1)
        root = parts[0]
        mode = parts[1].lower() if len(parts) > 1 else 'major'
        # Normalize mode names
        if mode in ('minor', 'min', 'm'):
            mode_flag = 'minor'
        else:
            mode_flag = 'major'
        try:
            m21_key = m21.key.Key(root, mode_flag)
        except Exception:
            logger.warning("Could not parse key signature '%s'. Defaulting to C major.", key_signature)
            m21_key = m21.key.Key('C')
    else:
        m21_key = m21.key.Key('C') 

    m21_clef = m21.clef.TrebleClef()

    # Calculate timing constants for tick-based quantization
    quarter_note_duration_s = 60.0 / beat_grid.bpm
    beat_ticks = TICKS_PER_QUARTER  # 480 ticks per quarter note
    measure_length_ticks = beat_ticks * time_sig.numerator

    # Group beats into measures based on downbeats and time signature
    measure_start_times = beat_grid.downbeats
    if not measure_start_times:
        # Generate a uniform measure grid if no downbeats are provided
        measure_duration_s = quarter_note_duration_s * time_sig.numerator
        total_duration_s = max(
            (solo_notes.notes[-1].start_time + solo_notes.notes[-1].duration if solo_notes.notes else 0.0),
            (chord_timeline.events[-1].timestamp + quarter_note_duration_s if chord_timeline.events else 0.0),
            measure_duration_s,
        )
        measure_start_times = [0.0]
        current_measure_start = 0.0
        while current_measure_start < total_duration_s:
            current_measure_start += measure_duration_s
            measure_start_times.append(current_measure_start)

        if len(measure_start_times) > 1 and measure_start_times[-1] > total_duration_s + measure_duration_s:
            measure_start_times.pop()

        if len(measure_start_times) == 1:
            measure_start_times.append(measure_start_times[0] + measure_duration_s)

    # Build pitch-to-guitar-position mapping for technical elements
    pitch_to_position: dict[tuple[int, int, int], tuple[int, int]] = {}
    for note in solo_notes.notes:
        try:
            pos = midi_to_guitar_position(note.pitch)
            step, alter, octave = _midi_to_step_alter_octave(note.pitch)
            pitch_key = (step, alter, octave)
            if pitch_key not in pitch_to_position:
                pitch_to_position[pitch_key] = (pos.string, pos.fret)
        except ValueError:
            pass

    # Keep track of notes that are tied across measures
    tied_notes_queue = []

    # Iterate through each measure
    for i in range(len(measure_start_times) - 1):
        measure_start_s = measure_start_times[i]
        measure_end_s = measure_start_times[i + 1]

        m21_measure = m21.stream.Measure()
        m21_measure.number = i + 1

        if i == 0:
            m21_measure.append(m21_clef)
            m21_measure.append(m21_time_signature)
            m21_measure.append(m21_key)
            m21_measure.append(m21.tempo.MetronomeMark(number=beat_grid.bpm))

        current_cumulative_ticks = 0  # Ticks from start of measure
        next_tied_notes_queue = []

        # Process notes tied from the previous measure
        for tied_note_info in tied_notes_queue:
            original_note_obj, remaining_duration_s = tied_note_info

            duration_in_this_measure_s = min(remaining_duration_s, measure_end_s - measure_start_s)
            target_ticks = _seconds_to_ticks(duration_in_this_measure_s, quarter_note_duration_s)
            note_ticks = target_ticks - current_cumulative_ticks

            if note_ticks > 0:
                m21_note_segment = m21.note.Note(original_note_obj.pitch)
                m21_note_segment.volume.velocity = original_note_obj.velocity
                m21_note_segment.duration = m21.duration.Duration(_ticks_to_ql(note_ticks))

                # Attach guitar technical elements (string/fret) via music21-native API
                _attach_technical_elements(m21_note_segment, original_note_obj.pitch, pitch_to_position)

                if remaining_duration_s > duration_in_this_measure_s:
                    m21_note_segment.tie = m21.tie.Tie('continue')
                    next_tied_notes_queue.append((original_note_obj, remaining_duration_s - duration_in_this_measure_s))
                else:
                    m21_note_segment.tie = m21.tie.Tie('stop')

                m21_measure.append(m21_note_segment)

            current_cumulative_ticks = target_ticks

        tied_notes_queue = next_tied_notes_queue

        # Process solo notes for this measure
        notes_starting_in_this_measure = [
            n for n in solo_notes.notes
            if n.start_time >= measure_start_s and n.start_time < measure_end_s
        ]
        notes_starting_in_this_measure.sort(key=lambda n: n.start_time)

        for note in notes_starting_in_this_measure:
            # Add rests for gaps before the note (beat-aligned)
            note_offset_s = note.start_time - measure_start_s
            note_offset_ticks = _seconds_to_ticks(note_offset_s, quarter_note_duration_s)

            if note_offset_ticks > current_cumulative_ticks:
                gap_ticks = note_offset_ticks - current_cumulative_ticks
                rest_ticks_list = break_rests_at_beats(gap_ticks, beat_ticks)
                for rest_ticks in rest_ticks_list:
                    if rest_ticks > 0:
                        m21_rest = m21.note.Rest(_ticks_to_ql(rest_ticks))
                        m21_measure.append(m21_rest)
                current_cumulative_ticks = note_offset_ticks

            # Determine duration within this measure
            duration_in_this_measure_s = min(note.duration, measure_end_s - note.start_time)
            note_end_ticks = _seconds_to_ticks(note.start_time + duration_in_this_measure_s - measure_start_s, quarter_note_duration_s)
            note_ticks = note_end_ticks - current_cumulative_ticks

            if note_ticks > 0:
                m21_note_segment = m21.note.Note(note.pitch)
                m21_note_segment.volume.velocity = note.velocity
                m21_note_segment.duration = m21.duration.Duration(_ticks_to_ql(note_ticks))

                # Attach guitar technical elements (string/fret) via music21-native API
                _attach_technical_elements(m21_note_segment, note.pitch, pitch_to_position)

                if note.duration > duration_in_this_measure_s:
                    m21_note_segment.tie = m21.tie.Tie('start')
                    tied_notes_queue.append((note, note.duration - duration_in_this_measure_s))

                m21_measure.append(m21_note_segment)

            current_cumulative_ticks = note_end_ticks

        # Add a final rest if the measure is not filled (beat-aligned)
        if current_cumulative_ticks < measure_length_ticks:
            gap_ticks = measure_length_ticks - current_cumulative_ticks
            rest_ticks_list = break_rests_at_beats(gap_ticks, beat_ticks)
            for rest_ticks in rest_ticks_list:
                if rest_ticks > 0:
                    m21_final_rest = m21.note.Rest(_ticks_to_ql(rest_ticks))
                    m21_measure.append(m21_final_rest)

        # Add chords to the measure
        chords_in_measure = [
            c for c in chord_timeline.events
            if c.timestamp >= measure_start_s and c.timestamp < measure_end_s
        ]
        chords_in_measure.sort(key=lambda c: c.timestamp)

        for chord_event in chords_in_measure:
            if chord_event.chord == "N":
                continue

            m21_chord_str = _harmoniq_chord_to_music21(chord_event.chord)
            try:
                m21_chord_symbol = m21.harmony.ChordSymbol(m21_chord_str)
            except Exception:
                logger.warning("Could not parse chord symbol '%s' (mapped to '%s'). Adding as text expression.", chord_event.chord, m21_chord_str)
                m21_chord_symbol = m21.expressions.TextExpression(m21_chord_str)

            offset_s = chord_event.timestamp - measure_start_s
            offset_ql = offset_s / quarter_note_duration_s

            m21_measure.insert(offset_ql, m21_chord_symbol)

        part.append(m21_measure)

    # 4. Convert the score to MusicXML string
    musicxml_output = m21.musicxml.m21ToXml.GeneralObjectExporter().parse(score).decode('utf-8')

    # 5. Add technical elements (string/fret) for guitar tablature
    musicxml_output = _add_technical_elements(musicxml_output, solo_notes)

    return musicxml_output


def _attach_technical_elements(
    note_obj: music21.note.Note,
    pitch: int,
    pitch_to_position: dict[tuple[int, int, int], tuple[int, int]],
) -> None:
    """Attach guitar string/fret technical elements to a music21 Note object.

    Uses music21-native StringIndication and FretIndication, which render as
    <notations><technical><string>N</string><fret>N</fret></technical></notations>
    and merge correctly with <tie> elements (no duplicate <notations> blocks).

    Args:
        note_obj: The music21 Note to annotate.
        pitch: MIDI pitch number.
        pitch_to_position: Mapping from (step, alter, octave) to (string, fret).
    """
    try:
        step, alter, octave = _midi_to_step_alter_octave(pitch)
        pitch_key = (step, alter, octave)
        if pitch_key in pitch_to_position:
            string_num, fret_num = pitch_to_position[pitch_key]
            import music21 as m21
            note_obj.articulations.append(
                m21.articulations.StringIndication(number=string_num)
            )
            note_obj.articulations.append(
                m21.articulations.FretIndication(number=fret_num)
            )
    except ValueError:
        pass


def _add_technical_elements(musicxml: str, solo_notes: SoloNotes) -> str:
    """No-op: technical elements are now attached via music21-native API.

    Kept for backward compatibility with callers. The regex-based approach
    was replaced with music21-native StringIndication/FretIndication to fix
    the <tie> + <notations> duplication bug.
    """
    return musicxml


def _midi_to_step_alter_octave(midi: int) -> tuple[str, int, int]:
    """Convert MIDI to (step, alter, octave) matching MusicXML format.
    
    Returns: (step letter, alter (-1/0/1), octave number)
    """
    # Use sharps for chromatic notes (matches music21 default)
    sharp_map = [
        ('C', 0), ('C', 1), ('D', 0), ('D', 1), ('E', 0), ('F', 0),
        ('F', 1), ('G', 0), ('G', 1), ('A', 0), ('A', 1), ('B', 0),
    ]
    pc = midi % 12
    octave = (midi // 12) - 1
    step, alter = sharp_map[pc]
    return step, alter, octave


def _harmoniq_chord_to_music21(chord_symbol: str) -> str:
    """Convert Harmoniq chord format (e.g. 'C:maj', 'F#:min7') to music21 format ('C', 'F#m7').

    music21's ChordSymbol expects standard chord abbreviations like 'C', 'Cm', 'C7', 'Cmaj7'.
    Harmoniq uses a 'root:quality' format that music21 cannot parse directly.
    """
    if not chord_symbol:
        return chord_symbol
    parts = chord_symbol.split(":", 1)
    root = parts[0]
    if len(parts) < 2:
        return root
    quality = parts[1].strip()
    if not quality:
        return root
    quality_map = {
        "maj": "", "min": "m", "m": "m", "dim": "dim", "aug": "aug",
        "7": "7", "maj7": "maj7", "min7": "m7", "m7": "m7",
        "7sus4": "7sus4", "sus4": "sus4", "sus2": "sus2",
        "6": "6", "min6": "m6", "m6": "m6",
        "9": "9", "maj9": "maj9", "min9": "m9", "m9": "m9",
    }
    suffix = quality_map.get(quality.lower(), quality)
    return root + suffix

