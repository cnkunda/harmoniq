"""
MusicXML generation from Harmoniq's internal JSON artifacts (BeatGrid, ChordTimeline, SoloNotes).

This module creates a MusicXML lead sheet with:
- Beat-aligned chord symbols via <harmony> elements
- Solo notes with guitar tablature (string/fret) via <technical> elements
"""

from __future__ import annotations

import math
import re
from fractions import Fraction
from typing import TYPE_CHECKING

# Lazy load music21 for performance if not always used.
# If music21 is not installed, this will raise an ImportError at runtime.
if TYPE_CHECKING:
    import music21

from app.schemas import BeatGrid, ChordTimeline, SoloNotes, TimeSignature, ChordEvent, SoloNote
from app.guitar_position import midi_to_guitar_position

# Constants for MusicXML generation
DEFAULT_DIVISIONS = 480  # Standard for many MusicXML applications (e.g., MuseScore, Finale)

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
        # music21 expects "C major", "A minor" etc.
        # We need to parse this string into music21.key.Key
        try:
            m21_key = m21.key.Key(key_signature)
        except Exception:
            print(f"WARNING: Could not parse key signature '{key_signature}'. Defaulting to C major.")
            m21_key = m21.key.Key('C', 'major')
    else:
        # TODO: Infer key from chord timeline or add as input
        m21_key = m21.key.Key('C', 'major') 

    m21_clef = m21.clef.TrebleClef()

                # NOTE: beat_grid.tick_value is currently not used for duration calculations.
                # Durations are derived directly from SoloNote.duration and BeatGrid.bpm.
                # If tick_value is intended to constrain or quantize MusicXML durations,
                # additional logic would be needed here.

    # Calculate quarter length in seconds for duration conversions
    # beat_grid.bpm gives us beats per minute, assuming quarter notes are beats.
    # If beat_grid.tick_value changes this, we need to adjust.
    # For now, assume BPM refers to quarter notes.
    quarter_note_duration_s = 60.0 / beat_grid.bpm

    # Group beats into measures based on downbeats and time signature
    # downbeats are the start times of each measure
    measure_start_times = beat_grid.downbeats
    if not measure_start_times:
        # IMPROVED: Generate a uniform measure grid if no downbeats are provided.
        # This is a more robust fallback than just two points.
        measure_duration_s = quarter_note_duration_s * time_sig.numerator
        total_duration_s = max(
            (solo_notes.notes[-1].start_time + solo_notes.notes[-1].duration if solo_notes.notes else 0.0),
            (chord_timeline.events[-1].timestamp + quarter_note_duration_s if chord_timeline.events else 0.0),
            measure_duration_s # Ensure at least one measure
        )
        measure_start_times = [0.0]
        current_measure_start = 0.0
        while current_measure_start < total_duration_s:
            current_measure_start += measure_duration_s
            measure_start_times.append(current_measure_start)
        
        # Remove the last measure start if it's too far beyond total_duration_s
        if len(measure_start_times) > 1 and measure_start_times[-1] > total_duration_s + measure_duration_s:
            measure_start_times.pop()
        
        # Ensure at least one measure is always created
        if len(measure_start_times) == 1:
             measure_start_times.append(measure_start_times[0] + measure_duration_s)


    # Keep track of notes that are tied across measures
    tied_notes_queue = []

    # Iterate through each measure
    for i in range(len(measure_start_times) - 1):
        measure_start_s = measure_start_times[i]
        measure_end_s = measure_start_times[i+1]

        m21_measure = m21.stream.Measure()
        m21_measure.number = i + 1

        if i == 0:
            m21_measure.append(m21_clef)
            m21_measure.append(m21_time_signature)
            m21_measure.append(m21_key)
            m21_measure.append(m21.tempo.MetronomeMark(number=beat_grid.bpm))

        current_measure_position_s = measure_start_s # Absolute time in seconds
        current_cumulative_ql = Fraction(0, 1)
        next_tied_notes_queue = []

        # Add notes that were tied from the previous measure
        for tied_note_info in tied_notes_queue:
            # tied_note_info is (original_note_obj, remaining_duration_s_from_original_note)
            original_note_obj, remaining_duration_s = tied_note_info

            duration_in_this_measure_s = min(remaining_duration_s, measure_end_s - measure_start_s)
            
            target_cumulative_ql = Fraction(round(duration_in_this_measure_s / quarter_note_duration_s * 8), 8)
            note_duration_ql = target_cumulative_ql - current_cumulative_ql

            if note_duration_ql > 0:
                m21_note_segment = m21.note.Note(original_note_obj.pitch)
                m21_note_segment.volume.velocity = original_note_obj.velocity
                m21_note_segment.duration = m21.duration.Duration(note_duration_ql)
                
                # Tie logic
                if remaining_duration_s > duration_in_this_measure_s:
                    # If note continues to next measure, mark as tied continue
                    m21_note_segment.tie = m21.tie.Tie('continue')
                    next_tied_notes_queue.append((original_note_obj, remaining_duration_s - duration_in_this_measure_s))
                else:
                    # If this is the last segment, mark as tied stop
                    m21_note_segment.tie = m21.tie.Tie('stop')
                
                m21_measure.append(m21_note_segment)

            current_cumulative_ql = target_cumulative_ql
            current_measure_position_s = measure_start_s + duration_in_this_measure_s

        tied_notes_queue = next_tied_notes_queue

        # Process solo notes for this measure
        # We need to consider notes that start in this measure AND notes that might have started
        # before but extend into this measure (these should have been handled by tied_notes_queue)
        # So, we only look for notes that *start* within this measure.
        notes_starting_in_this_measure = [
            n for n in solo_notes.notes
            if n.start_time >= measure_start_s and n.start_time < measure_end_s
        ]
        notes_starting_in_this_measure.sort(key=lambda n: n.start_time)

        for note in notes_starting_in_this_measure:
            # Add rests for gaps before the note
            if note.start_time > current_measure_position_s:
                target_cumulative_ql = Fraction(round((note.start_time - measure_start_s) / quarter_note_duration_s * 8), 8)
                rest_duration_ql = target_cumulative_ql - current_cumulative_ql
                if rest_duration_ql > 0:
                    m21_rest = m21.note.Rest(rest_duration_ql)
                    m21_measure.append(m21_rest)
                current_cumulative_ql = target_cumulative_ql
            
            # Determine the actual duration of this note segment within the current measure
            # A note can either end within this measure, or extend into the next
            duration_in_this_measure_s = min(note.duration, measure_end_s - note.start_time)

            target_cumulative_ql = Fraction(round((note.start_time + duration_in_this_measure_s - measure_start_s) / quarter_note_duration_s * 8), 8)
            note_duration_ql = target_cumulative_ql - current_cumulative_ql

            if note_duration_ql > 0:
                m21_note_segment = m21.note.Note(note.pitch)
                m21_note_segment.volume.velocity = note.velocity
                m21_note_segment.duration = m21.duration.Duration(note_duration_ql)

                if note.duration > duration_in_this_measure_s:
                    # This note extends into the next measure, so tie it
                    m21_note_segment.tie = m21.tie.Tie('start')
                    # Add to queue for next measure processing
                    tied_notes_queue.append((note, note.duration - duration_in_this_measure_s))
                
                m21_measure.append(m21_note_segment)

            current_measure_position_s = note.start_time + duration_in_this_measure_s
            current_cumulative_ql = target_cumulative_ql
        
        # Add a final rest if the measure is not filled
        measure_total_ql = Fraction(round((measure_end_s - measure_start_s) / quarter_note_duration_s * 8), 8)
        if current_cumulative_ql < measure_total_ql:
            final_rest_duration_ql = measure_total_ql - current_cumulative_ql
            if final_rest_duration_ql > 0:
                m21_final_rest = m21.note.Rest(final_rest_duration_ql)
                m21_measure.append(m21_final_rest)


        # Add chords to the measure (as text expressions for now, or proper harmony objects)
        # Filter chord events that fall within this measure's time
        chords_in_measure = [
            c for c in chord_timeline.events
            if c.timestamp >= measure_start_s and c.timestamp < measure_end_s
        ]
        chords_in_measure.sort(key=lambda c: c.timestamp)

        for chord_event in chords_in_measure:
            if chord_event.chord == "N":
                # "No Chord" is represented by a no-op or specific text expression
                # For now, we'll just skip it for harmony
                continue

            # Create a Music21 ChordSymbol object
            try:
                m21_chord_symbol = m21.harmony.ChordSymbol(chord_event.chord)
            except Exception:
                # Fallback for unparseable chord symbols
                print(f"WARNING: Could not parse chord symbol '{chord_event.chord}'. Adding as text expression.")
                m21_chord_symbol = m21.expressions.TextExpression(chord_event.chord)

            # Calculate offset from the start of the measure in quarter lengths
            offset_s = chord_event.timestamp - measure_start_s
            offset_ql = offset_s / quarter_note_duration_s
            
            m21_measure.insert(offset_ql, m21_chord_symbol)


        part.append(m21_measure)

    # 4. Convert the score to MusicXML string
    # Using 'midi' variant for better compatibility, as 'score-partwise' is default for music21
    # and alphaTab expects partwise.
    musicxml_output = m21.musicxml.m21ToXml.GeneralObjectExporter().parse(score).decode('utf-8')

    # 5. Add technical elements (string/fret) for guitar tablature
    musicxml_output = _add_technical_elements(musicxml_output, solo_notes)

    return musicxml_output


def _add_technical_elements(musicxml: str, solo_notes: SoloNotes) -> str:
    """
    Add <technical> elements with string/fret to notes in the MusicXML.
    
    Uses regex to find all <note>...</note> elements (including those with attributes
    like <note dynamics="88.89">), check if they contain a <pitch>, and inject
    a <technical> element with the guitar string/fret position.
    """
    if not solo_notes.notes:
        return musicxml
    
    # Build a mapping from (step, alter, octave) to string/fret
    pitch_to_position = {}
    for note in solo_notes.notes:
        try:
            pos = midi_to_guitar_position(note.pitch)
            step, alter, octave = _midi_to_step_alter_octave(note.pitch)
            pitch_key = (step, alter, octave)
            if pitch_key not in pitch_to_position:
                pitch_to_position[pitch_key] = (pos.string, pos.fret)
        except ValueError:
            pass
    
    if not pitch_to_position:
        return musicxml
    
    # Match <note> elements including those with attributes
    # Pattern: <note...>...</note> (non-greedy)
    note_pattern = re.compile(r'(<note(?:\s[^>]*)?>)(.*?)(</note>)', re.DOTALL)
    
    def replace_note(match: re.Match) -> str:
        opening_tag = match.group(1)
        note_content = match.group(2)
        closing_tag = match.group(3)
        
        # Check if this note has a pitch (not a rest)
        if '<rest' in note_content:
            return match.group(0)
        
        step_match = re.search(r'<step>([A-G])</step>', note_content)
        octave_match = re.search(r'<octave>(\d+)</octave>', note_content)
        alter_match = re.search(r'<alter>(-?\d+)</alter>', note_content)
        
        if not step_match or not octave_match:
            return match.group(0)
        
        step = step_match.group(1)
        octave = int(octave_match.group(1))
        alter = int(alter_match.group(1)) if alter_match else 0
        pitch_key = (step, alter, octave)
        
        if pitch_key not in pitch_to_position:
            return match.group(0)
        
        string_num, fret_num = pitch_to_position[pitch_key]
        technical = f"<notations><technical><string>{string_num}</string><fret>{fret_num}</fret></technical></notations>"
        # Insert technical before closing </note>
        return opening_tag + note_content + technical + closing_tag
    
    return note_pattern.sub(replace_note, musicxml)


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



