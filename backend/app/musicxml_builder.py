"""
MusicXML generation from Harmoniq's internal JSON artifacts (BeatGrid, ChordTimeline, SoloNotes).

This module creates a MusicXML lead sheet (Commit 107 "MusicXML as Primary Render
Format") with:

- Beat-aligned chord symbols via <harmony> elements, each with an inline
  <frame> fretboard diagram
- Solo notes with guitar tablature (string/fret) via <technical> elements
- Dynamics (<direction>/<dynamics>) mapped from note velocity
- Articulations (staccato / accent / tenuto)
- Slurs (<slur>) over legato passages
- Beams (<beam>) grouped by beat and tuplet structure
- A parallel tablature staff (part P2) below the standard notation staff (P1)
- <defaults> with <scaling> 7mm/40 tenths plus <page-layout>/<system-layout>/
  <staff-layout> so AlphaTab honors the score designer's layout
- MusicXML 3.1 Partwise doctype; harmony <offset> values are explicit,
  divisions-based positions (music21's cursor-relative offsets go negative
  and corrupt AlphaTab's harmony placement)
"""

from __future__ import annotations

import copy
import math
import re
import xml.etree.ElementTree as ET
from fractions import Fraction
from typing import TYPE_CHECKING, Any

# Lazy load music21 for performance if not always used.
# If music21 is not installed, this will raise an ImportError at runtime.
if TYPE_CHECKING:
    import music21

import logging
from app.guitar_position import OPEN_STRING_MIDI, midi_to_guitar_position
from app.rhythm_quantization import (
    decompose_rest_durations,
    quantize_seconds_to_ql,
    quantize_to_note_type,
    tick_to_quarter_fraction,
)
from app.schemas import BeatGrid, ChordTimeline, SoloNotes, TimeSignature, ChordEvent, SoloNote

logger = logging.getLogger("harmoniq.musicxml_builder")

# Constants for MusicXML generation
DEFAULT_DIVISIONS = 480  # Standard for many MusicXML applications (e.g., MuseScore, Finale)

# Commit 107: expressive-notation thresholds ----------------------------------
# Velocity → <dynamics> mark (music21's volumeScalar convention: 30..110 maps
# pp..ff).  Marks re-assert at the first attack of every measure.
DYNAMIC_MARK_AT_VELOCITY = ((110, "ff"), (90, "f"), (70, "mf"), (50, "mp"), (30, "p"))
# Articulations are exclusive: accent on loud attacks, staccato on short notes,
# tenuto on sustained emphatic notes.
ACCENT_VELOCITY = 110
TENUTO_MIN_VELOCITY = 100
TENUTO_MIN_DURATION_QL = Fraction(1, 2)
STACCATO_MAX_DURATION_QL = Fraction(1, 4)
# Notes are part of the same legato phrase when the gap to the previous note
# is at most this many quarter lengths; long phrases are capped at this many
# notes so a single slur never sprawls across the whole page.
SLUR_MAX_GAP_QL = Fraction(1, 2)
SLUR_MAX_NOTES = 10
# Note types of this quarter length or shorter join beam groups.
BEAMABLE_MAX_DURATION_QL = Fraction(1, 2)

# Standard guitar tuning (string 1 = high E) for the tablature staff.
TAB_TUNING = ((1, "E", 4), (2, "B", 3), (3, "G", 3), (4, "D", 3), (5, "A", 2), (6, "E", 2))


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


def _apply_rhythm(
    m21,
    m21_client: Any,
    duration_ql: Fraction,
    tolerance_ql: Fraction,
) -> Fraction | None:
    """Assign the nearest valid rhythm (type, dots, tuplet) to a note/rest.

    Without this, music21 infers types from the quarter length alone and can
    mislabel tuplets (e.g. a triplet eighth as "eighth with half length").
    The quantized rhythm is applied explicitly so ``<type>``, ``<dot>`` and
    ``<time-modification>`` render correctly.

    Returns the exact quarter length of the rhythm actually applied (which
    can differ from ``duration_ql`` by up to the tolerance), or None when no
    rhythm is matched.  The caller uses this to track the measure's *actual*
    content end: tolerance rounding (0.3 → 1/3) otherwise accumulates drift
    and the final rest over-fills the measure (Commit 107 regression that
    crashed the exporter with a 1/60 "2048th" tuple rest).
    """
    quantized = quantize_to_note_type(duration_ql, tolerance_ql=tolerance_ql)
    if quantized is None:
        # Fallback: nearest expressible regardless of tolerance — prevents
        # inexpressible durations (e.g. 0.137) from reaching music21 which
        # would raise MusicXMLExportException at measure 10.
        # Use a large tolerance to pick the closest valid type.
        quantized = quantize_to_note_type(duration_ql, tolerance_ql=Fraction(1, 1))
        if quantized is None:
            # Ultimate fallback: brute-force nearest candidate
            from app.rhythm_quantization import _CANDIDATES

            quantized = min(_CANDIDATES, key=lambda c: abs(c.quarter_length - duration_ql))
    dur = m21.duration.Duration(quantized.quarter_length)
    dur.type = quantized.type
    dur.dots = quantized.dots
    if quantized.tuplet is not None:
        actual, normal = quantized.tuplet
        base = m21.duration.Duration(type=quantized.base_type)
        tuplet = m21.duration.Tuplet(actual, normal)
        tuplet.durationActual = m21.duration.Duration(base.quarterLength)
        tuplet.durationNormal = m21.duration.Duration(base.quarterLength)
        dur.tuplets = (tuplet,)
    m21_client.duration = dur
    return quantized.quarter_length


def _append_rests(m21, measure: Any, rest_duration_ql: Fraction) -> None:
    """Append one or more rests whose durations sum exactly to ``rest_duration_ql``.

    Rest durations are decomposed into exact plain/dotted/tuplet pieces (see
    ``decompose_rest_durations``) instead of being tolerance-quantized like
    notes: a gap rest must land exactly on the next attack and the
    measure-final rest must fill the measure exactly, or every subsequent
    element offset (harmony/dynamics) drifts (Commit 107).
    """
    for piece in decompose_rest_durations(rest_duration_ql):
        rest = m21.note.Rest()
        if piece.type:
            _apply_rhythm(m21, rest, piece.quarter_length, Fraction(0))
        else:
            rest.duration = m21.duration.Duration(piece.quarter_length)
        measure.append(rest)


def _velocity_dynamic(velocity: float | int) -> str:
    """Map a note velocity (0-127) to a <dynamics> mark (pp..ff)."""
    for threshold, mark in DYNAMIC_MARK_AT_VELOCITY:
        if velocity >= threshold:
            return mark
    return "pp"


def _insert_dynamics(m21, measure: Any, attacks: list[tuple[Fraction, Any]]) -> None:
    """Place a <direction>/<dynamics> mark at the first attack of each mark change.

    Every measure starts with the mark re-asserted at its first attack (music21
    never writes an <offset> for directions sitting at a note's own offset, so
    the marks land on the beat grid without cursor-relative drift).
    """
    current_mark: str | None = None
    for offset_ql, note in attacks:
        mark = _velocity_dynamic(note.volume.velocity)
        if mark != current_mark:
            measure.insert(offset_ql, m21.dynamics.Dynamic(mark))
            current_mark = mark


def _apply_articulations(m21, note: Any, duration_ql: Fraction) -> None:
    """Attach staccato / accent / tenuto to an attack note (exclusive rules)."""
    velocity = note.volume.velocity or 0
    if velocity >= ACCENT_VELOCITY:
        note.articulations.append(m21.articulations.Accent())
    elif duration_ql <= STACCATO_MAX_DURATION_QL:
        note.articulations.append(m21.articulations.Staccato())
    elif velocity >= TENUTO_MIN_VELOCITY and duration_ql >= TENUTO_MIN_DURATION_QL:
        note.articulations.append(m21.articulations.Tenuto())


def _assign_beams(m21, attacks: list[tuple[Fraction, Any]]) -> None:
    """Beam consecutive sub-beat notes within the same beat (Commit 107).

    Attack notes of duration ≤ eighth that form a contiguous run inside one
    beat are grouped into a single beam (start/continue/stop).  Rests and
    quarter+ notes break the run, and tuplet members beam together within
    their beat, matching the Commit 106 rhythm structure.
    """
    i = 0
    count = len(attacks)
    while i < count:
        offset_ql, note = attacks[i]
        if note.duration.quarterLength > BEAMABLE_MAX_DURATION_QL:
            i += 1
            continue
        beat = offset_ql.numerator // offset_ql.denominator
        run: list[Any] = []
        j = i
        while j < count:
            o2, n2 = attacks[j]
            if n2.duration.quarterLength > BEAMABLE_MAX_DURATION_QL:
                break
            if o2.numerator // o2.denominator != beat:
                break
            run.append(n2)
            j += 1
        if len(run) >= 2:
            for k, nk in enumerate(run):
                beam_type = "start" if k == 0 else ("stop" if k == len(run) - 1 else "continue")
                nk.beams.append(m21.beam.Beam(beam_type, number=1))
        i = j


def _legato_phrase_groups(
    attacks: list[tuple[Fraction, Any]],
    threshold_ql: Fraction = SLUR_MAX_GAP_QL,
    max_notes: int = SLUR_MAX_NOTES,
) -> list[list[Any]]:
    """Group attack notes into legato phrases (slur candidates).

    Notes belong to the same phrase when the gap to the previous attack is at
    most ``threshold_ql`` (rests create larger gaps and break the phrase).
    """
    groups: list[list[Any]] = []
    current: list[Any] = []
    prev_end: Fraction | None = None
    for offset_ql, note in attacks:
        offset = Fraction(offset_ql)
        if prev_end is not None and offset - prev_end > threshold_ql:
            groups.append(current)
            current = []
        current.append(note)
        prev_end = offset + Fraction(note.duration.quarterLength)
        if len(current) >= max_notes:
            groups.append(current)
            current = []
            prev_end = None
    if current:
        groups.append(current)
    return groups


def _add_legato_slurs(m21, score: Any, attacks: list[tuple[Fraction, Any]]) -> None:
    """Add a <slur> spanner over each multi-note legato phrase."""
    for group in _legato_phrase_groups(attacks):
        if len(group) >= 2:
            score.insert(0, m21.spanner.Slur(group[0], group[-1]))


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

    # 2. Create a single Part for the lead sheet (the tablature staff is added
    #    as part P2 by the XML post-processing pass below).
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
        # Prefer music21's own parser ("A minor", "Am", "C", "F# minor"...)
        # so the mode is never collapsed to major.  Fall back to the legacy
        # whitespace split, then to C major.
        try:
            m21_key = m21.key.Key(key_signature)
        except Exception:
            try:
                parts = key_signature.split(None, 1)
                root = parts[0]
                mode = parts[1].lower() if len(parts) > 1 else 'major'
                # Normalize mode names
                if mode in ('minor', 'min', 'm'):
                    mode_flag = 'minor'
                else:
                    mode_flag = 'major'
                m21_key = m21.key.Key(root, mode_flag)
            except Exception:
                logger.warning("Could not parse key signature '%s'. Defaulting to C major.", key_signature)
                m21_key = m21.key.Key('C')
    else:
        m21_key = m21.key.Key('C')

    m21_clef = m21.clef.TrebleClef()

    # Commit 106: duration math runs on the beat tick grid instead of a
    # fixed 1/8-note grid.  tick_ql is the tick size in quarter lengths
    # (e.g. tick_value 0.25 → 1/4 = a 16th note at 120 BPM).
    tick_ql = tick_to_quarter_fraction(beat_grid.tick_value)
    tick_seconds = float(tick_ql) * (60.0 / beat_grid.bpm)

    # Calculate quarter length in seconds for duration conversions
    # beat_grid.bpm gives us beats per minute, assuming quarter notes are beats.
    # If beat_grid.tick_value changes this, we need to adjust.
    # For now, assume BPM refers to quarter notes.
    quarter_note_duration_s = 60.0 / beat_grid.bpm

    # Group beats into measures based on downbeats and time signature
    # downbeats are the start times of each measure
    measure_duration_s = quarter_note_duration_s * time_sig.numerator
    total_duration_s = max(
        (solo_notes.notes[-1].start_time + solo_notes.notes[-1].duration if solo_notes.notes else 0.0),
        (chord_timeline.events[-1].timestamp + quarter_note_duration_s if chord_timeline.events else 0.0),
        measure_duration_s  # Ensure at least one measure
    )
    measure_start_times = list(beat_grid.downbeats)
    if not measure_start_times:
        # IMPROVED: Generate a uniform measure grid if no downbeats are provided.
        # This is a more robust fallback than just two points.
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
    else:
        # Commit 107: downbeats only define measure *boundaries* — the grid must
        # be extended (on the time-signature measure duration) until it covers
        # the whole score, or trailing notes/chords/ties fall off the last
        # measure and are silently dropped from the rendered score.
        while measure_start_times[-1] < total_duration_s:
            measure_start_times.append(measure_start_times[-1] + measure_duration_s)

    # Keep track of notes that are tied across measures
    tied_notes_queue = []

    # Commit 107: per-measure attack lists (dynamics/beams/slurs), the
    # quantized chord offsets for the XML offset-rewrite pass, and the global
    # attack timeline used for legato phrase detection.
    attacks_by_measure: dict[int, list[tuple[Fraction, Any]]] = {}
    global_attacks: list[tuple[Fraction, Any]] = []
    harmony_offsets_by_measure: dict[int, list[Fraction]] = {}
    cumulative_measure_start_ql = Fraction(0)

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

        measure_total_ql = quantize_seconds_to_ql(
            measure_end_s - measure_start_s, quarter_note_duration_s, tick_ql
        )

        # Add notes that were tied from the previous measure
        for tied_note_info in tied_notes_queue:
            # tied_note_info is (original_note_obj, remaining_duration_s_from_original_note)
            original_note_obj, remaining_duration_s = tied_note_info

            duration_in_this_measure_s = min(remaining_duration_s, measure_end_s - measure_start_s)

            note_duration_ql = quantize_seconds_to_ql(
                duration_in_this_measure_s, quarter_note_duration_s, tick_ql
            )
            note_duration_ql = min(
                note_duration_ql, measure_total_ql - current_cumulative_ql
            )

            if note_duration_ql > 0:
                m21_note_segment = m21.note.Note(original_note_obj.pitch)
                m21_note_segment.volume.velocity = original_note_obj.velocity
                applied_ql = _apply_rhythm(m21, m21_note_segment, note_duration_ql, tick_ql / 2)
                if applied_ql is None:
                    continue

                # Same barline clamp as the fresh-notes path: tolerance
                # rounding must not push a tied segment past the measure.
                remaining_to_fill = measure_total_ql - current_cumulative_ql
                exceeds_barline = applied_ql > remaining_to_fill
                if exceeds_barline:
                    clamped_ql = _apply_rhythm(m21, m21_note_segment, remaining_to_fill, tick_ql / 2)
                    if clamped_ql is None or clamped_ql > remaining_to_fill:
                        clamped_ql = remaining_to_fill
                        m21_note_segment.duration = m21.duration.Duration(remaining_to_fill)
                else:
                    clamped_ql = applied_ql

                if clamped_ql > 0:
                    m21_measure.append(m21_note_segment)
                    current_cumulative_ql = min(
                        current_cumulative_ql + clamped_ql, measure_total_ql
                    )

                    # Tie logic: the still-unplaced remainder (in seconds) is
                    # whatever of the original tie did not fit this measure.
                    next_remaining_s = remaining_duration_s - (
                        float(clamped_ql) * quarter_note_duration_s
                    )
                    if next_remaining_s > 0:
                        # Note continues to next measure
                        m21_note_segment.tie = m21.tie.Tie('continue')
                        next_tied_notes_queue.append(
                            (original_note_obj, next_remaining_s)
                        )
                    else:
                        # Last segment of the tie
                        m21_note_segment.tie = m21.tie.Tie('stop')

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
                target_cumulative_ql = quantize_seconds_to_ql(
                    note.start_time - measure_start_s, quarter_note_duration_s, tick_ql
                )
                rest_duration_ql = target_cumulative_ql - current_cumulative_ql
                if rest_duration_ql > 0:
                    _append_rests(m21, m21_measure, rest_duration_ql)
                    current_cumulative_ql = target_cumulative_ql

            # Determine the actual duration of this note segment within the current measure
            # A note can either end within this measure, or extend into the next
            duration_in_this_measure_s = min(note.duration, measure_end_s - note.start_time)

            target_cumulative_ql = quantize_seconds_to_ql(
                note.start_time + duration_in_this_measure_s - measure_start_s,
                quarter_note_duration_s,
                tick_ql,
            )
            note_duration_ql = min(
                target_cumulative_ql - current_cumulative_ql,
                measure_total_ql - current_cumulative_ql,
            )

            if note_duration_ql > 0:
                m21_note_segment = m21.note.Note(note.pitch)
                m21_note_segment.volume.velocity = note.velocity
                applied_ql = _apply_rhythm(m21, m21_note_segment, note_duration_ql, tick_ql / 2)

                # Clamp to the measure: tolerance rounding (e.g. 0.3 → 1/3)
                # must not push content past the barline or the exporter
                # crashes on the 1/60 leftover tuple.  Anything clamped away
                # is tied into the next measure.
                remaining_to_fill = measure_total_ql - current_cumulative_ql
                exceeds_barline = applied_ql is not None and applied_ql > remaining_to_fill
                if exceeds_barline:
                    # Re-apply so the stored duration matches the clamped ql.
                    clamped_ql = _apply_rhythm(m21, m21_note_segment, remaining_to_fill, tick_ql / 2)
                    if clamped_ql is None or clamped_ql > remaining_to_fill:
                        # Nearest rhythm still rounds up past the barline:
                        # pin the duration to the exact remainder so the
                        # stored quarter length never exceeds the cursor.
                        clamped_ql = remaining_to_fill
                        m21_note_segment.duration = m21.duration.Duration(remaining_to_fill)
                else:
                    clamped_ql = applied_ql

                if clamped_ql is not None and clamped_ql > 0:
                    crosses_measure = note.duration > duration_in_this_measure_s or exceeds_barline
                    if crosses_measure:
                        # This note extends into the next measure, so tie it
                        m21_note_segment.tie = m21.tie.Tie('start')
                        remaining_s = (
                            float(applied_ql - clamped_ql) * quarter_note_duration_s
                            if exceeds_barline
                            else note.duration - duration_in_this_measure_s
                        )
                        if remaining_s > 0:
                            tied_notes_queue.append((note, remaining_s))

                    m21_measure.append(m21_note_segment)
                    current_cumulative_ql = min(
                        current_cumulative_ql + clamped_ql, measure_total_ql
                    )

                    # Commit 107: attacks (fresh note onsets) drive dynamics,
                    # articulations, beams, and slur phrases.
                    if m21_note_segment.tie is None or m21_note_segment.tie.type == 'start':
                        _apply_articulations(m21, m21_note_segment, clamped_ql)
                        attacks_by_measure.setdefault(m21_measure.number, []).append(
                            (current_cumulative_ql - clamped_ql, m21_note_segment)
                        )

            current_measure_position_s = note.start_time + duration_in_this_measure_s

        # Add a final rest if the measure is not filled
        if current_cumulative_ql < measure_total_ql:
            final_rest_duration_ql = measure_total_ql - current_cumulative_ql
            if final_rest_duration_ql > 0:
                _append_rests(m21, m21_measure, final_rest_duration_ql)

        # Add chords to the measure (as harmony objects)
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
            m21_chord_str = _harmoniq_chord_to_music21(chord_event.chord)
            is_harmony = True
            try:
                m21_chord_symbol = m21.harmony.ChordSymbol(m21_chord_str)
            except Exception:
                logger.warning("Could not parse chord symbol '%s' (mapped to '%s'). Adding as text expression.", chord_event.chord, m21_chord_str)
                m21_chord_symbol = m21.expressions.TextExpression(m21_chord_str)
                is_harmony = False

            # Commit 107: quantize the offset on the beat tick grid.  Float
            # division (e.g. 1.333/0.667 = 1.9995002...) used to produce
            # Fraction(3999, 2000) offsets that made music21 emit negative
            # cursor-relative <offset> elements; the quantization gives exact
            # beat-aligned Fractions.
            offset_s = chord_event.timestamp - measure_start_s
            offset_ql = quantize_seconds_to_ql(
                offset_s, quarter_note_duration_s, tick_ql
            )
            m21_measure.insert(offset_ql, m21_chord_symbol)
            # Only real <harmony> elements are paired positionally with the
            # offset list by _rewrite_harmony_offsets; a failed chord becomes
            # a TextExpression (no <harmony>), so it must not consume a slot.
            if is_harmony:
                harmony_offsets_by_measure.setdefault(m21_measure.number, []).append(offset_ql)

        # Commit 107: expressive notation passes on the finished measure.
        attacks = attacks_by_measure.get(m21_measure.number, [])
        _insert_dynamics(m21, m21_measure, attacks)
        _assign_beams(m21, attacks)

        part.append(m21_measure)
        global_attacks.extend(
            (cumulative_measure_start_ql + offset_ql, note) for offset_ql, note in attacks
        )
        cumulative_measure_start_ql += measure_total_ql

    # Commit 107: legato slurs across the whole performance.
    _add_legato_slurs(m21, score, global_attacks)

    # Commit 107: <defaults> — scaling 7mm/40 tenths plus page/system/staff
    # layout so AlphaTab does not substitute its own defaults.
    score.append(
        m21.layout.ScoreLayout(
            scalingMillimeters=7,
            scalingTenths=40,
            pageLayout=m21.layout.PageLayout(
                pageWidth=850,
                pageHeight=1100,
                leftMargin=50,
                rightMargin=50,
                topMargin=50,
                bottomMargin=50,
            ),
            systemLayout=m21.layout.SystemLayout(distance=120, topDistance=70),
            staffLayoutList=[m21.layout.StaffLayout(distance=65)],
        )
    )

    # 4. Convert the score to MusicXML string
    # Using 'midi' variant for better compatibility, as 'score-partwise' is default for music21
    # and alphaTab expects partwise.
    try:
        musicxml_output = m21.musicxml.m21ToXml.GeneralObjectExporter().parse(score).decode('utf-8')
    except Exception as exc:
        # Fallback for inexpressible durations (e.g. 1/60 2048th) — sanitize all
        # durations to the nearest expressible type and retry. Prevents the
        # whole analysis from losing its MusicXML (measure 10 regression).
        err_msg = str(exc)
        if "inexpressible" in err_msg or "MusicXMLExportException" in type(exc).__name__:
            logger.warning("MusicXML export failed (%s), sanitizing durations and retrying", err_msg[:200])
            for el in score.recurse():
                if isinstance(el, (m21.note.Note, m21.note.Rest)):
                    try:
                        # Re-quantize to nearest valid rhythm (large tolerance)
                        ql = Fraction(float(el.duration.quarterLength)).limit_denominator(96)
                        q = quantize_to_note_type(ql, tolerance_ql=Fraction(1, 1))
                        if q is not None:
                            el.duration.type = q.type
                            el.duration.dots = q.dots
                            if q.tuplet is not None:
                                actual, normal = q.tuplet
                                base = m21.duration.Duration(type=q.base_type)
                                tup = m21.duration.Tuplet(actual, normal)
                                tup.durationActual = m21.duration.Duration(base.quarterLength)
                                tup.durationNormal = m21.duration.Duration(base.quarterLength)
                                el.duration.tuplets = (tup,)
                            else:
                                el.duration.tuplets = ()
                    except Exception:
                        # Last resort: force to quarter
                        try:
                            el.duration.type = "quarter"
                            el.duration.dots = 0
                            el.duration.tuplets = ()
                        except Exception:
                            pass
            musicxml_output = m21.musicxml.m21ToXml.GeneralObjectExporter().parse(score).decode('utf-8')
        else:
            raise

    # 5. Add technical elements (string/fret) for guitar tablature
    musicxml_output = _add_technical_elements(musicxml_output, solo_notes)

    # 6. Normalize <divisions> and ensure every measure carries an explicit
    #    <attributes> block with it (Commit 106).
    musicxml_output = _normalize_divisions(musicxml_output)

    # 7. Post-process with ElementTree (Commit 107): rewrite harmony offsets in
    #    divisions (music21's cursor-relative offsets go negative mid-measure),
    #    inject <frame> fretboard diagrams into <harmony>, append the parallel
    #    tablature part P2, and pin the MusicXML 3.1 Partwise doctype.
    musicxml_output = _add_tablature_and_frames(
        musicxml_output, solo_notes, harmony_offsets_by_measure
    )

    return musicxml_output


# ---------------------------------------------------------------------------
# Tablature / chord-diagram post-processing (Commit 107)
# ---------------------------------------------------------------------------

# (step, alter, octave) → (string, fret) map for every solo pitch.
def _pitch_to_position_map(solo_notes: SoloNotes) -> dict[tuple[str, int, int], tuple[int, int]]:
    if not solo_notes.notes:
        return {}
    pitch_to_position: dict[tuple[str, int, int], tuple[int, int]] = {}
    for note in solo_notes.notes:
        try:
            pos = midi_to_guitar_position(note.pitch)
        except ValueError:
            continue
        pitch_key = _midi_to_step_alter_octave(note.pitch)
        if pitch_key not in pitch_to_position:
            pitch_to_position[pitch_key] = (pos.string, pos.fret)
    return pitch_to_position


def _measure_divisions(measure: ET.Element) -> int:
    """Divisions of the first <attributes>/<divisions> in the measure."""
    divisions_el = measure.find("attributes/divisions")
    if divisions_el is not None and divisions_el.text:
        try:
            return max(1, int(divisions_el.text))
        except ValueError:
            pass
    return DEFAULT_DIVISIONS


def _rewrite_harmony_offsets(measure: ET.Element, harmony_offsets_by_measure: dict[int, list[Fraction]]) -> None:
    """Replace cursor-relative harmony <offset> values with explicit divisions.

    music21 writes <offset> = (object offset − exporter cursor), which goes
    negative for harmonies inside long rests and renders wrong in AlphaTab.
    Every harmony with a positive quantized offset gets an explicit
    <offset sound="yes">N</offset> in divisions; zero-offset harmonies get none.
    """
    try:
        number = int(measure.get("number") or 1)
    except ValueError:
        number = 1
    offsets = iter(harmony_offsets_by_measure.get(number, []))
    divisions = _measure_divisions(measure)
    for harmony in measure.findall("harmony"):
        for offset_el in harmony.findall("offset"):
            harmony.remove(offset_el)
        offset_ql = next(offsets, None)
        if offset_ql:
            offset_divisions = int(round(Fraction(offset_ql) * divisions))
            if offset_divisions > 0:
                offset_el = ET.Element("offset")
                offset_el.set("sound", "yes")
                offset_el.text = str(offset_divisions)
                harmony.append(offset_el)


def _mirror_tab_measure(measure: ET.Element, p2: ET.Element, pitch_map: dict[tuple[str, int, int], tuple[int, int]]) -> None:
    """Clone one P1 measure into the tablature part P2 (TAB clef + staff-details)."""
    m2 = ET.SubElement(p2, "measure")
    m2.set("number", measure.get("number") or "1")
    attrs = measure.find("attributes")
    if attrs is not None:
        a2 = ET.SubElement(m2, "attributes")
        for tag in ("divisions", "key", "time"):
            child = attrs.find(tag)
            if child is not None:
                a2.append(copy.deepcopy(child))
        clef = ET.SubElement(a2, "clef")
        sign = ET.SubElement(clef, "sign")
        sign.text = "TAB"
        line = ET.SubElement(clef, "line")
        line.text = "5"
        staff_details = ET.SubElement(a2, "staff-details")
        staff_lines = ET.SubElement(staff_details, "staff-lines")
        staff_lines.text = "6"
        for line_no, step, octave in TAB_TUNING:
            tuning = ET.SubElement(staff_details, "staff-tuning")
            tuning.set("line", str(line_no))
            tuning_step = ET.SubElement(tuning, "tuning-step")
            tuning_step.text = step
            tuning_octave = ET.SubElement(tuning, "tuning-octave")
            tuning_octave.text = str(octave)
    for note in measure.findall("note"):
        _mirror_tab_note(note, m2, pitch_map)


# Notation children that do not belong on a tablature staff (replaced by
# <technical> string/fret).  Tuplet and slur markers are kept.
_TAB_STRIPPED_NOTATIONS = {"tied", "articulations", "ornaments", "technical"}


def _mirror_tab_note(src_note: ET.Element, m2: ET.Element, pitch_map: dict[tuple[str, int, int], tuple[int, int]]) -> None:
    """Mirror a P1 note into the tab staff with a <technical> string/fret."""
    n2 = ET.SubElement(m2, "note")
    kept_notations: ET.Element | None = None
    for child in src_note:
        if child.tag == "notations":
            keep = [c for c in child if c.tag not in _TAB_STRIPPED_NOTATIONS]
            if keep:
                kept_notations = ET.SubElement(n2, "notations")
                for c in keep:
                    kept_notations.append(copy.deepcopy(c))
        elif child.tag in ("beam", "stem"):
            continue
        else:
            n2.append(copy.deepcopy(child))
    pitch = src_note.find("pitch")
    if pitch is not None:
        step = pitch.findtext("step")
        octave_text = pitch.findtext("octave")
        if step and octave_text:
            alter = int(pitch.findtext("alter") or 0)
            position = pitch_map.get((step, alter, int(octave_text)))
            if position is not None:
                string, fret = position
                notations = kept_notations
                if notations is None:
                    notations = ET.SubElement(n2, "notations")
                technical = ET.SubElement(notations, "technical")
                string_el = ET.SubElement(technical, "string")
                string_el.text = str(string)
                fret_el = ET.SubElement(technical, "fret")
                fret_el.text = str(fret)


# Chord-diagram <frame> voicings ---------------------------------------------
# E-shape (root on string 6) and A-shape (root on string 5) movable forms per
# quality.  Each entry is (string, interval-above-root in semitones); open
# strings are interval 0, and the octave placement is resolved per string.
_E_SHAPES = {
    "major": ((6, 0), (5, 7), (4, 12), (3, 4), (2, 7), (1, 0)),
    "minor": ((6, 0), (5, 7), (4, 12), (3, 3), (2, 7), (1, 0)),
    "dominant": ((6, 0), (5, 7), (4, 10), (3, 4), (2, 7), (1, 0)),
    "major-seventh": ((6, 0), (5, 7), (4, 11), (3, 4), (2, 7), (1, 0)),
    "minor-seventh": ((6, 0), (5, 7), (4, 10), (3, 3), (2, 7), (1, 0)),
    "diminished": ((6, 0), (5, 7), (4, 12), (3, 3), (2, 6), (1, 0)),
    "diminished-seventh": ((6, 0), (5, 7), (4, 9), (3, 3), (2, 6), (1, 0)),
    "augmented": ((6, 0), (5, 8), (4, 12), (3, 4), (2, 8), (1, 0)),
    "suspended-fourth": ((6, 0), (5, 7), (4, 12), (3, 5), (2, 7), (1, 0)),
    "suspended-second": ((6, 0), (5, 7), (4, 12), (3, 2), (2, 7), (1, 0)),
    "major-sixth": ((6, 0), (5, 7), (4, 9), (3, 4), (2, 7), (1, 0)),
    "minor-sixth": ((6, 0), (5, 7), (4, 9), (3, 3), (2, 7), (1, 0)),
    "ninth": ((6, 0), (5, 7), (4, 10), (3, 4), (2, 7), (1, 14)),
    "major-ninth": ((6, 0), (5, 7), (4, 11), (3, 4), (2, 7), (1, 14)),
    "minor-ninth": ((6, 0), (5, 7), (4, 10), (3, 3), (2, 7), (1, 14)),
    "power": ((6, 0), (5, 7), (4, 12)),
}
_A_SHAPES = {
    "major": ((5, 0), (4, 7), (3, 12), (2, 4), (1, 7)),
    "minor": ((5, 0), (4, 7), (3, 12), (2, 3), (1, 7)),
    "dominant": ((5, 0), (4, 7), (3, 10), (2, 4), (1, 7)),
    "major-seventh": ((5, 0), (4, 7), (3, 11), (2, 4), (1, 7)),
    "minor-seventh": ((5, 0), (4, 7), (3, 10), (2, 3), (1, 7)),
    "diminished": ((5, 0), (4, 7), (3, 12), (2, 3), (1, 6)),
    "diminished-seventh": ((5, 0), (4, 7), (3, 9), (2, 3), (1, 6)),
    "augmented": ((5, 0), (4, 8), (3, 12), (2, 4), (1, 8)),
    "suspended-fourth": ((5, 0), (4, 7), (3, 12), (2, 5), (1, 7)),
    "suspended-second": ((5, 0), (4, 7), (3, 12), (2, 2), (1, 7)),
    "major-sixth": ((5, 0), (4, 7), (3, 9), (2, 4), (1, 7)),
    "minor-sixth": ((5, 0), (4, 7), (3, 9), (2, 3), (1, 7)),
    "ninth": ((5, 0), (4, 7), (3, 10), (2, 4), (1, 14)),
    "major-ninth": ((5, 0), (4, 7), (3, 11), (2, 4), (1, 14)),
    "minor-ninth": ((5, 0), (4, 7), (3, 10), (2, 3), (1, 14)),
    "power": ((5, 0), (4, 7)),
}

_PC_OF_STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _fret_for_interval(root_pc: int, string: int, interval: int) -> int | None:
    """Fret (0-12) on ``string`` that plays ``interval`` above the root pc."""
    open_midi = OPEN_STRING_MIDI[string]
    root_midi = open_midi + ((root_pc - open_midi) % 12)
    for octave_shift in range(-2, 3):
        midi = root_midi + interval + 12 * octave_shift
        fret = midi - open_midi
        if 0 <= fret <= 12:
            return fret
    return None


def _frame_for_harmony(harmony: ET.Element) -> ET.Element | None:
    """Build a <frame> fretboard diagram for a <harmony> element.

    The voicing is the tightest (smallest fret span) movable E/A shape for the
    chord's root and quality; the fret board is placed at the lowest fretted
    note.  Returns None for chords without a recognizable root/quality.
    """
    root_step = harmony.findtext("root/root-step")
    kind = harmony.findtext("kind")
    if not root_step or not kind:
        return None
    root_pc = _PC_OF_STEP.get(root_step)
    if root_pc is None:
        return None
    alter = harmony.findtext("root/root-alter")
    if alter:
        try:
            root_pc = (root_pc + int(float(alter))) % 12
        except (TypeError, ValueError):
            pass

    e_shape = _E_SHAPES.get(kind)
    a_shape = _A_SHAPES.get(kind)
    if e_shape is None and a_shape is None:
        e_shape, a_shape = _E_SHAPES["major"], _A_SHAPES["major"]

    best: tuple[int, int, list[tuple[int, int]]] | None = None
    for shape in (e_shape, a_shape):
        if shape is None:
            continue
        notes: list[tuple[int, int]] = []
        for string, interval in shape:
            fret = _fret_for_interval(root_pc, string, interval)
            if fret is None:
                notes = []
                break
            notes.append((string, fret))
        if len(notes) < 3:
            continue
        frets = [fret for _, fret in notes]
        span = max(frets) - min(frets)
        if best is None or span < best[0]:
            best = (span, len(notes), notes)

    if best is None:
        return None
    _, _, notes = best

    frets = [fret for _, fret in notes]
    min_fret = min(frets)
    span = max(frets) - min_fret

    frame = ET.Element("frame")
    strings = ET.SubElement(frame, "frame-strings")
    strings.text = "6"
    frame_frets = ET.SubElement(frame, "frame-frets")
    frame_frets.text = str(max(5, span + 1))
    first_fret = ET.SubElement(frame, "first-fret")
    first_fret.text = str(max(1, min_fret))
    for string, fret in sorted(notes, key=lambda t: t[0]):
        frame_note = ET.SubElement(frame, "frame-note")
        string_el = ET.SubElement(frame_note, "string")
        string_el.text = str(string)
        fret_el = ET.SubElement(frame_note, "fret")
        fret_el.text = str(fret)
    return frame


def _add_tablature_and_frames(
    musicxml: str,
    solo_notes: SoloNotes,
    harmony_offsets_by_measure: dict[int, list[Fraction]],
) -> str:
    """ElementTree post-processing pass (Commit 107).

    - Rewrite harmony <offset> values as explicit divisions
    - Inject <frame> fretboard diagrams into <harmony>
    - Append the parallel tablature part (P2) after the lead sheet part
    - Pin the MusicXML 3.1 Partwise doctype and version
    """
    root = ET.fromstring(musicxml)
    root.set("version", "3.1")

    part_list = root.find("part-list")
    if part_list is not None:
        tab_score_part = ET.SubElement(part_list, "score-part")
        tab_score_part.set("id", "P2")
        part_name = ET.SubElement(tab_score_part, "part-name")
        part_name.text = "Tablature"

    p1 = root.find("part")
    if p1 is not None:
        p2 = ET.Element("part")
        p2.set("id", "P2")
        pitch_map = _pitch_to_position_map(solo_notes)
        for measure in p1.findall("measure"):
            _rewrite_harmony_offsets(measure, harmony_offsets_by_measure)
            for harmony in measure.findall("harmony"):
                frame = _frame_for_harmony(harmony)
                if frame is not None:
                    # DTD order: (root|function), kind, inversion?, bass?,
                    # degree*, frame?, offset?, ...
                    offset_el = harmony.find("offset")
                    if offset_el is not None:
                        harmony.insert(list(harmony).index(offset_el), frame)
                    else:
                        harmony.append(frame)
            _mirror_tab_measure(measure, p2, pitch_map)
        root.append(p2)

    body = ET.tostring(root, encoding="unicode")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" '
        '"http://www.musicxml.org/dtds/partwise.dtd">\n'
        + body
    )


def _add_technical_elements(musicxml: str, solo_notes: SoloNotes) -> str:
    """
    Add <technical> elements with string/fret to notes in the MusicXML.

    Uses regex to find all <note>...</note> elements (including those with attributes
    like <note dynamics="88.89">), check if they contain a <pitch>, and inject
    a <technical> element with the guitar string/fret position.
    """
    pitch_to_position = _pitch_to_position_map(solo_notes)
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
        technical_inner = f"<technical><string>{string_num}</string><fret>{fret_num}</fret></technical>"
        # Merge into an existing <notations> block (tied notes carry
        # <tied>...</tied> there) instead of appending a duplicate, so a
        # single <notations> holds both <tied> and <technical> — invalid
        # duplicates would confuse AlphaTab (Commit 106).
        if '<notations>' in note_content:
            idx = note_content.rfind('</notations>')
            if idx == -1:
                return match.group(0)
            merged = note_content[:idx] + technical_inner + note_content[idx:]
            return opening_tag + merged + closing_tag
        technical = f"<notations>{technical_inner}</notations>"
        # Insert technical before closing </note>
        return opening_tag + note_content + technical + closing_tag

    return note_pattern.sub(replace_note, musicxml)


def _normalize_divisions(musicxml: str) -> str:
    """Force per-measure ``<divisions>`` on an LCM-friendly tick grid.

    music21 derives ``<divisions>`` from the full LCM of every duration
    (e.g. 10080 when triplets are present), so the canonical 480 only appears
    by accident.  This rescales the document to ``lcm(480, X)`` where X is
    music21's divisions: common rhythms land on the canonical 480, while
    micro-durations (64th notes) still resolve to integer tick units.  Every
    measure without an ``<attributes>`` block receives one containing only
    the divisions, which AlphaTab consults per measure (Commit 106).
    """
    div_matches = re.findall(r"<divisions>(\d+)</divisions>", musicxml)
    if not div_matches:
        return musicxml
    current = max(int(x) for x in div_matches)
    if current <= 0:
        return musicxml
    if current % DEFAULT_DIVISIONS != 0:
        target = DEFAULT_DIVISIONS * current // math.gcd(DEFAULT_DIVISIONS, current)
    else:
        target = current
    factor = target // current

    out = re.sub(r"<divisions>\d+</divisions>", f"<divisions>{target}</divisions>", musicxml)
    out = re.sub(r"<duration>(\d+)</duration>", lambda m: f"<duration>{int(m.group(1)) * factor}</duration>", out)
    out = re.sub(r"<offset>(\d+)</offset>", lambda m: f"<offset>{int(m.group(1)) * factor}</offset>", out)

    def _inject_per_measure(m: re.Match) -> str:
        opening, body, closing = m.group(1), m.group(2), m.group(3)
        if "<attributes>" in body:
            return opening + body + closing
        attrs = f"<attributes><divisions>{target}</divisions></attributes>"
        return opening + attrs + body + closing

    return re.sub(r"(<measure\b[^>]*>)(.*?)(</measure>)", _inject_per_measure, out, flags=re.DOTALL)


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
