"""
MusicXML generation from Harmoniq's internal JSON artifacts (BeatGrid, ChordTimeline, SoloNotes).

This module creates a MusicXML lead sheet with:
- Beat-aligned chord symbols via <harmony> elements
- Solo notes with guitar tablature (string/fret) via <technical> elements
- Proper duration quantization to standard note types (whole through 64th)
- Tuplet detection (triplets, quintuplets, sextuplets)
- Measure-level fill validation
- Dynamics, articulations, beams, slurs (Commit 108)
- Chord diagrams (<frame>) and tab staff (Commit 108)
- <divisions> and <defaults> layout elements (Commit 108)

Commit 107: Replaced eighth-note-only quantization with full note type support.
Commit 108: Added comprehensive MusicXML notation elements for AlphaTab rendering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

# Lazy load music21 for performance if not always used.
# If music21 is not installed, this will raise an ImportError at runtime.
if TYPE_CHECKING:
    import music21

import logging
from app.schemas import BeatGrid, ChordTimeline, SoloNotes
from app.guitar_position import midi_to_guitar_position, midi_to_all_guitar_positions

logger = logging.getLogger("harmoniq.musicxml_builder")

# Velocity thresholds for dynamics mapping
_VELOCITY_DYNAMICS: list[tuple[int, str]] = [
    (33, "pp"),
    (50, "p"),
    (65, "mp"),
    (80, "mf"),
    (95, "f"),
    (128, "ff"),
]

# Chord root to semitone offset for voicing lookup
_CHORD_ROOT_SEMITONES: dict[str, int] = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

# Chord quality to intervals (semitones from root)
_CHORD_INTERVALS: dict[str, list[int]] = {
    "": [0, 4, 7],
    "maj": [0, 4, 7],
    "min": [0, 3, 7],
    "m": [0, 3, 7],
    "dim": [0, 3, 6],
    "aug": [0, 4, 8],
    "7": [0, 4, 7, 10],
    "maj7": [0, 4, 7, 11],
    "min7": [0, 3, 7, 10],
    "m7": [0, 3, 7, 10],
    "sus4": [0, 5, 7],
    "sus2": [0, 2, 7],
    "6": [0, 4, 7, 9],
    "min6": [0, 3, 7, 9],
    "m6": [0, 3, 7, 9],
    "9": [0, 4, 7, 10, 14],
    "maj9": [0, 4, 7, 11, 14],
    "min9": [0, 3, 7, 10, 14],
    "m9": [0, 3, 7, 10, 14],
    "7sus4": [0, 5, 7, 10],
}

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
    """Convert ticks to quarter-length Fraction.

    Quantizes to nearest 64th note (15-tick boundary) to prevent music21
    creating tuplets with unsupported durationNormal types (e.g. "2048th").
    At 480 PPQ, all standard note types are multiples of 15 ticks.
    """
    # Quantize to nearest 15-tick boundary (64th note), minimum 30 ticks (64th)
    quantized = max(round(ticks / 15) * 15, 30)
    return Fraction(quantized, TICKS_PER_QUARTER)


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


# ---------------------------------------------------------------------------
# Commit 108: MusicXML Enhancement Helpers
# ---------------------------------------------------------------------------

def _velocity_to_dynamics(velocity: int) -> str:
    """Map MIDI velocity (0-127) to a dynamics marking string."""
    for threshold, label in _VELOCITY_DYNAMICS:
        if velocity < threshold:
            return label
    return "ff"


# Commit B9: CAGED shape definitions for voicing-aware chord diagrams.
_CAGED_VOICING_SHAPES: dict[str, dict] = {
    "E": {"strings": [1, 2, 3, 4, 5, 6], "pattern": [0, 0, 1, 2, 2, 0], "shiftable": True},
    "A": {"strings": [1, 2, 3, 4, 5], "pattern": [0, 2, 2, 2, 0], "shiftable": True},
    "C": {"strings": [1, 2, 3, 4, 5], "pattern": [0, 1, 0, 2, 3], "shiftable": False},
    "D": {"strings": [1, 2, 3, 4], "pattern": [2, 3, 2, 0], "shiftable": False},
    "G": {"strings": [1, 2, 3, 4, 5, 6], "pattern": [3, 3, 0, 0, 2, 3], "shiftable": False},
}


def _compute_chord_midi_pitches(chord_symbol: str, root_midi: int | None = None) -> list[int]:
    """Compute MIDI pitches for a chord symbol, preferring guitar-range voicings.

    If root_midi is not given, picks the lowest root in guitar range (E2=40 to B5=83).
    Returns sorted list of MIDI pitches.
    """
    parts = chord_symbol.split(":", 1)
    root_str = parts[0]
    quality = parts[1].strip() if len(parts) > 1 else ""

    root_sem = _CHORD_ROOT_SEMITONES.get(root_str)
    if root_sem is None:
        return []

    intervals = _CHORD_INTERVALS.get(quality, _CHORD_INTERVALS.get(""))
    if root_midi is None:
        # Find lowest root in guitar range
        for oct_offset in range(2, 6):
            candidate = oct_offset * 12 + root_sem
            if 40 <= candidate <= 83:
                root_midi = candidate
                break
    if root_midi is None:
        root_midi = 40 + root_sem

    return sorted(root_midi + iv for iv in intervals if root_midi + iv <= 88)


def _compute_chord_voicing(
    chord_symbol: str,
    voicing_shape: str | None = None,
    voicing_position: int | None = None,
) -> list[tuple[int, int]]:
    """Compute guitar voicing (string, fret) pairs for a chord diagram.

    When voicing_shape and voicing_position are provided, uses the CAGED shape
    pattern directly to compute (string, fret) pairs. Otherwise falls back to
    MIDI-pitch-to-guitar-position mapping.

    Returns list of (string, fret) for each fretted/open string in the voicing.
    Empty list if voicing cannot be determined.
    """
    if voicing_shape is not None and voicing_shape in _CAGED_VOICING_SHAPES and voicing_position is not None:
        shape_def = _CAGED_VOICING_SHAPES[voicing_shape]
        position = voicing_position
        voicing: list[tuple[int, int]] = []
        for i, s in enumerate(shape_def["strings"]):
            fret = shape_def["pattern"][i] + position
            if fret >= 0:
                voicing.append((s, fret))
        return voicing

    pitches = _compute_chord_midi_pitches(chord_symbol)
    if not pitches:
        return []

    # Fallback: for each pitch, find the best guitar position (lowest fret)
    voicing = []
    used_strings: set[int] = set()
    for pitch in pitches:
        positions = midi_to_all_guitar_positions(pitch)
        for pos in sorted(positions, key=lambda p: (p.fret, p.string)):
            if pos.string not in used_strings:
                voicing.append((pos.string, pos.fret))
                used_strings.add(pos.string)
                break

    return voicing


def _inject_defaults_block(musicxml: str) -> str:
    """Inject <defaults> layout block into MusicXML.

    If music21 already emits a <defaults> block (with <scaling>), enhance it
    by adding <page-layout>, <system-layout>, and <staff-layout> elements
    that AlphaTab uses for layout decisions.
    """
    if "<defaults>" not in musicxml:
        # No defaults at all — inject a full block before <part-list>
        defaults_xml = """  <defaults>
    <scaling>
      <millimeters>7</millimeters>
      <tenths>40</tenths>
    </scaling>
    <page-layout>
      <page-height>1100</page-height>
      <page-width>850</page-width>
      <page-margins type="both">
        <left-margin>50</left-margin>
        <right-margin>50</right-margin>
        <top-margin>50</top-margin>
        <bottom-margin>50</bottom-margin>
      </page-margins>
    </page-layout>
    <system-layout>
      <system-margins>
        <left-margin>0</left-margin>
        <right-margin>0</right-margin>
      </system-margins>
      <system-distance>120</system-distance>
      <top-system-distance>70</top-system-distance>
    </system-layout>
    <staff-layout>
      <staff-distance>65</staff-distance>
    </staff-layout>
  </defaults>
"""
        idx = musicxml.find("<part-list>")
        if idx != -1:
            return musicxml[:idx] + defaults_xml + musicxml[idx:]
        return musicxml

    # Already has <defaults> — enhance with missing layout elements
    result = musicxml

    # Add <page-layout> if missing
    if "<page-layout>" not in result:
        page_layout = """    <page-layout>
      <page-height>1100</page-height>
      <page-width>850</page-width>
      <page-margins type="both">
        <left-margin>50</left-margin>
        <right-margin>50</right-margin>
        <top-margin>50</top-margin>
        <bottom-margin>50</bottom-margin>
      </page-margins>
    </page-layout>
"""
        # Insert after </scaling> inside <defaults>
        idx = result.find("</scaling>")
        if idx != -1:
            insert_pos = idx + len("</scaling>")
            result = result[:insert_pos] + "\n" + page_layout + result[insert_pos:]

    # Add <system-layout> if missing
    if "<system-layout>" not in result:
        system_layout = """    <system-layout>
      <system-margins>
        <left-margin>0</left-margin>
        <right-margin>0</right-margin>
      </system-margins>
      <system-distance>120</system-distance>
      <top-system-distance>70</top-system-distance>
    </system-layout>
"""
        # Insert before </defaults>
        idx = result.find("</defaults>")
        if idx != -1:
            result = result[:idx] + system_layout + result[idx:]

    # Add <staff-layout> if missing
    if "<staff-layout>" not in result:
        staff_layout = """    <staff-layout>
      <staff-distance>65</staff-distance>
    </staff-layout>
"""
        idx = result.find("</defaults>")
        if idx != -1:
            result = result[:idx] + staff_layout + result[idx:]

    return result


def _inject_divisions(musicxml: str) -> str:
    """Ensure <divisions> element is present in the first measure's <attributes>."""
    if "<divisions>" in musicxml:
        return musicxml
    # Insert after first <attributes> open tag
    match = re.search(r"(<attributes[^>]*>)", musicxml)
    if match:
        insert_pos = match.end()
        return musicxml[:insert_pos] + f"\n        <divisions>{DEFAULT_DIVISIONS}</divisions>" + musicxml[insert_pos:]
    return musicxml


def _inject_dynamics(musicxml: str, solo_notes: SoloNotes, beat_grid: BeatGrid) -> str:
    """Add <dynamics> elements to notes based on velocity.

    Dynamics are inserted when velocity changes significantly from the previous note.
    This avoids redundant markings on every note.
    """
    if not solo_notes.notes:
        return musicxml

    quarter_note_duration_s = 60.0 / beat_grid.bpm if beat_grid.bpm > 0 else 0.5

    # Build a map of (measure_number, offset_ql) -> dynamics string
    dynamics_map: dict[tuple[int, float], str] = {}
    prev_velocity = 64  # default mf
    prev_dynamics = "mf"

    for note in sorted(solo_notes.notes, key=lambda n: n.start_time):
        vel = note.velocity or 64
        dyn = _velocity_to_dynamics(vel)

        # Only add dynamics when there's a significant change
        if dyn != prev_dynamics:
            dynamics_map[(0, note.start_time / quarter_note_duration_s)] = dyn
            prev_dynamics = dyn
        prev_velocity = vel

    if not dynamics_map:
        return musicxml

    # Inject dynamics into <note> elements that have <pitch>
    # Find each <note> with <pitch> and match it to a dynamics entry
    lines = musicxml.split("\n")
    result_lines: list[str] = []
    note_idx = 0
    sorted_notes = sorted(solo_notes.notes, key=lambda n: n.start_time)

    for line in lines:
        result_lines.append(line)
        # When we close a <note> that has a <pitch>, check if it needs dynamics
        if line.strip() == "</note>" and note_idx < len(sorted_notes):
            note = sorted_notes[note_idx]
            vel = note.velocity or 64
            dyn = _velocity_to_dynamics(vel)
            # Check if this note needs a dynamics marking (first note or velocity changed)
            if note_idx == 0 or dyn != _velocity_to_dynamics(sorted_notes[note_idx - 1].velocity or 64):
                # Insert dynamics before </note>
                dynamics_line = f"        <dynamics><{dyn}/></dynamics>"
                # Find the last </notations> or insert before </note>
                for j in range(len(result_lines) - 1, -1, -1):
                    if "</notations>" in result_lines[j]:
                        # Insert after </notations> but inside <note>
                        result_lines.insert(j + 1, dynamics_line)
                        break
                    if "<notations" in result_lines[j]:
                        # Find closing tag
                        for k in range(j, len(result_lines)):
                            if "</notations>" in result_lines[k]:
                                result_lines.insert(k + 1, dynamics_line)
                                break
                        break
                else:
                    # No <notations> found; insert before </note>
                    result_lines.insert(len(result_lines) - 1, dynamics_line)
            note_idx += 1

    return "\n".join(result_lines)


def _inject_articulations(musicxml: str, solo_notes: SoloNotes, beat_grid: BeatGrid) -> str:
    """Add articulation elements (staccato, accent, tenuto) to notes.

    - Staccato: note duration < 50% of quantized value
    - Accent: velocity > 100
    - Tenuto: note duration > 120% of quantized value
    """
    if not solo_notes.notes:
        return musicxml

    quarter_note_duration_s = 60.0 / beat_grid.bpm if beat_grid.bpm > 0 else 0.5

    # Build map of note index -> articulations
    artic_map: dict[int, list[str]] = {}
    for i, note in enumerate(solo_notes.notes):
        note_ticks = _seconds_to_ticks(note.duration, quarter_note_duration_s)
        quantized = quantize_to_note_type(note_ticks)
        arts: list[str] = []

        if quantized.ticks > 0 and note_ticks < quantized.ticks * 0.5:
            arts.append("staccato")
        if (note.velocity or 64) > 100:
            arts.append("accent")
        if quantized.ticks > 0 and note_ticks > quantized.ticks * 1.2:
            arts.append("tenuto")

        if arts:
            artic_map[i] = arts

    if not artic_map:
        return musicxml

    # Inject articulations into note elements
    lines = musicxml.split("\n")
    result_lines: list[str] = []
    note_idx = 0
    sorted_notes = sorted(solo_notes.notes, key=lambda n: n.start_time)

    for line in lines:
        result_lines.append(line)
        if line.strip() == "</note>" and note_idx < len(sorted_notes):
            if note_idx in artic_map:
                arts = artic_map[note_idx]
                art_elements = "".join(f"<{a}/>" for a in arts)
                art_line = f"          <articulations>{art_elements}</articulations>"
                # Insert into <notations>
                for j in range(len(result_lines) - 1, -1, -1):
                    if "</notations>" in result_lines[j]:
                        result_lines.insert(j, art_line)
                        break
            note_idx += 1

    return "\n".join(result_lines)


def _inject_beams(musicxml: str, beat_grid: BeatGrid) -> str:
    """Add <beam> elements to eighth and shorter notes, grouped by beat.

    Notes within the same beat are beamed together. Beam groups are limited
    to notes within a single beat (no cross-beam beams).

    Uses string-based injection to preserve the original XML formatting.
    """
    beat_ticks = TICKS_PER_QUARTER  # 480 ticks per quarter note

    # Parse note durations from the XML by scanning for <duration> and <type> elements
    # within <note> blocks that have <pitch> (not rests)
    lines = musicxml.split("\n")
    note_stack: list[str] = []  # Tracks current note being parsed
    in_note = False
    current_offset = 0  # Ticks from start of current measure
    beat_notes: list[int] = []  # Line indices of beammable notes in current beat
    beam_type_map: dict[int, str] = {}  # line_idx -> beam type

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Track measure boundaries
        if "<measure" in stripped and "number=" in stripped:
            current_offset = 0
            if beat_notes:
                _assign_beams(beat_notes, beam_type_map)
                beat_notes = []
            continue

        # Detect note start
        if stripped == "<note>":
            in_note = True
            note_stack = []
            continue

        # Collect note contents
        if in_note:
            note_stack.append(stripped)
            # Check if this is a closing </note>
            if stripped == "</note>":
                in_note = False

                # Check if this note has <pitch> (not a rest)
                has_pitch = any("<pitch>" in s for s in note_stack)
                has_rest = any("<rest" in s for s in note_stack)

                if has_pitch and not has_rest:
                    # Find note type
                    note_type = ""
                    duration = 0
                    for s in note_stack:
                        if s.startswith("<type>") and s.endswith("</type>"):
                            note_type = s[6:-7]
                        if s.startswith("<duration>") and s.endswith("</duration>"):
                            try:
                                duration = int(s[10:-11])
                            except ValueError:
                                pass

                    # Check if beammable (eighth or shorter)
                    if note_type in ("eighth", "16th", "32nd", "64th"):
                        beat_end = ((current_offset // beat_ticks) + 1) * beat_ticks
                        note_end = current_offset + duration

                        # If note extends past beat, finalize current group first
                        if note_end > beat_end and beat_notes:
                            _assign_beams(beat_notes, beam_type_map)
                            beat_notes = []

                        beat_notes.append(i)
                        current_offset = note_end

                        # Check if we've hit a beat boundary
                        if current_offset % beat_ticks == 0 and beat_notes:
                            _assign_beams(beat_notes, beam_type_map)
                            beat_notes = []
                    else:
                        # Non-beam note: finalize any pending group
                        if beat_notes:
                            _assign_beams(beat_notes, beam_type_map)
                            beat_notes = []
                        current_offset += duration
                else:
                    # Rest: finalize pending group
                    if beat_notes:
                        _assign_beams(beat_notes, beam_type_map)
                        beat_notes = []
                    for s in note_stack:
                        if s.startswith("<duration>") and s.endswith("</duration>"):
                            try:
                                current_offset += int(s[10:-11])
                            except ValueError:
                                pass

    # Finalize any remaining notes
    if beat_notes:
        _assign_beams(beat_notes, beam_type_map)

    # Second pass: insert beam elements
    final_lines: list[str] = []
    for i, line in enumerate(lines):
        final_lines.append(line)
        if i in beam_type_map:
            # Insert beam element before </note>
            # Find the right indentation by looking at surrounding lines
            indent = "        "
            beam_line = f"{indent}<beam number=\"1\">{beam_type_map[i]}</beam>"
            # Insert before the last </note>
            for j in range(len(final_lines) - 1, -1, -1):
                if final_lines[j].strip() == "</note>":
                    final_lines.insert(j, beam_line)
                    break

    return "\n".join(final_lines)


def _assign_beams(beat_notes: list[int], beam_type_map: dict[int, str]) -> None:
    """Assign beam types to a group of note line indices."""
    if len(beat_notes) < 2:
        return
    for idx in beat_notes:
        if idx not in beam_type_map:
            pos = beat_notes.index(idx)
            if pos == 0:
                beam_type_map[idx] = "begin"
            elif pos == len(beat_notes) - 1:
                beam_type_map[idx] = "end"
            else:
                beam_type_map[idx] = "continue"


def _inject_tuplet_time_modification(musicxml: str, solo_notes: SoloNotes, beat_grid: BeatGrid) -> str:
    """Add <time-modification> to notes in detected tuplet groups.

    Uses detect_tuplets() to find tuplet patterns, then injects
    <time-modification><actual-notes>N</actual-notes><normal-notes>M</normal-notes>
    into each note in the group.
    """
    if not solo_notes.notes or len(solo_notes.notes) < 3:
        return musicxml

    quarter_note_duration_s = 60.0 / beat_grid.bpm if beat_grid.bpm > 0 else 0.5
    beat_ticks = TICKS_PER_QUARTER
    time_sig = beat_grid.time_signature
    measure_length_ticks = beat_ticks * time_sig.numerator

    # Group notes by measure
    sorted_notes = sorted(solo_notes.notes, key=lambda n: n.start_time)
    if not sorted_notes:
        return musicxml

    measure_starts = beat_grid.downbeats if beat_grid.downbeats else []
    if not measure_starts:
        # Generate uniform measure starts
        measure_dur = quarter_note_duration_s * time_sig.numerator
        total = sorted_notes[-1].start_time + sorted_notes[-1].duration + measure_dur
        measure_starts = []
        t = 0.0
        while t < total:
            measure_starts.append(t)
            t += measure_dur

    # Detect tuplets per measure
    tuplet_map: dict[int, tuple[int, int]] = {}  # note_index -> (actual, normal)
    for mi in range(len(measure_starts) - 1):
        m_start = measure_starts[mi]
        m_end = measure_starts[mi + 1]
        measure_notes = [
            (n, _seconds_to_ticks(n.start_time - m_start, quarter_note_duration_s),
             _seconds_to_ticks(n.duration, quarter_note_duration_s))
            for n in sorted_notes
            if m_start <= n.start_time < m_end
        ]
        if len(measure_notes) < 3:
            continue

        notes_with_ticks = [(st, dur) for _, st, dur in measure_notes]
        tuplets = detect_tuplets(notes_with_ticks, measure_length_ticks, beat_ticks)
        for start_idx, end_idx, actual in tuplets:
            normal = 2 if actual == 3 else 4
            for idx in range(start_idx, end_idx):
                global_idx = sorted_notes.index(measure_notes[idx][0])
                tuplet_map[global_idx] = (actual, normal)

    if not tuplet_map:
        return musicxml

    # Inject <time-modification> into identified tuplet notes
    lines = musicxml.split("\n")
    result_lines: list[str] = []
    note_idx = 0

    for line in lines:
        result_lines.append(line)
        if line.strip() == "</note>" and note_idx in tuplet_map:
            actual, normal = tuplet_map[note_idx]
            tm_line = f"        <time-modification><actual-notes>{actual}</actual-notes><normal-notes>{normal}</normal-notes></time-modification>"
            # Insert before </note>
            result_lines.insert(len(result_lines) - 1, tm_line)
        if line.strip() == "</note>" or (line.strip().startswith("<note") and "<rest>" not in line and "<pitch>" not in line):
            if "</note>" in line:
                note_idx += 1

    return "\n".join(result_lines)


def _inject_chord_diagrams(musicxml: str, chord_timeline: ChordTimeline, beat_grid: BeatGrid) -> str:
    """Add <frame> chord diagram elements after each <harmony> element.

    Uses guitar voicing data to generate fretboard diagrams that AlphaTab
    renders as inline chord charts.
    """
    if not chord_timeline.events:
        return musicxml

    # Build list of chord symbols that need diagrams
    chord_diagrams: dict[str, str] = {}  # chord_symbol -> frame XML
    for event in chord_timeline.events:
        if event.chord == "N" or event.chord in chord_diagrams:
            continue
        voicing_shape: str | None = getattr(event, 'voicing_shape', None)
        voicing_position: int | None = getattr(event, 'voicing_position', None)
        voicing = _compute_chord_voicing(
            event.chord,
            voicing_shape=voicing_shape,
            voicing_position=voicing_position,
        )
        if not voicing:
            continue

        # Build <frame> XML
        first_fret = max(1, voicing_position) if voicing_position and voicing_position > 0 else None
        if first_fret is not None:
            frame_parts = [
                f'          <frame first-fret="{first_fret}">',
                "            <frame-strings>6</frame-strings>",
                "            <frame-frets>5</frame-frets>",
            ]
        else:
            frame_parts = [
                "          <frame>",
                "            <frame-strings>6</frame-strings>",
                "            <frame-frets>5</frame-frets>",
            ]

        # Build fret array: fret number per string (6=low E, 1=high E)
        frets_by_string = {s: -1 for s in range(1, 7)}
        for string_num, fret_num in voicing:
            frets_by_string[string_num] = fret_num

        for s in range(6, 0, -1):
            fret = frets_by_string[s]
            if fret >= 0:
                frame_parts.append(f"            <frame-note><string>{s}</string><fret>{fret}</fret></frame-note>")
            else:
                frame_parts.append(f"            <frame-note><string>{s}</string><mute>muted</mute></frame-note>")

        frame_parts.append("          </frame>")
        chord_diagrams[event.chord] = "\n".join(frame_parts)

    if not chord_diagrams:
        return musicxml

    # Insert <frame> after each <harmony> element, advancing past previous insertions
    result = musicxml
    search_offset = 0
    for event in chord_timeline.events:
        if event.chord == "N" or event.chord not in chord_diagrams:
            continue
        # Find the next </harmony> after the current search offset
        match = re.search(r"</harmony>", result[search_offset:])
        if match:
            abs_pos = search_offset + match.end()
            result = result[:abs_pos] + "\n" + chord_diagrams[event.chord] + result[abs_pos:]
            search_offset = abs_pos + len(chord_diagrams[event.chord]) + 1

    return result


def _inject_slurs(musicxml: str, solo_notes: SoloNotes, beat_grid: BeatGrid) -> str:
    """Add <slur> elements for legato passages.

    Detects consecutive notes with no gap (or gap < 32nd note) and similar
    pitch direction, grouping them into slur phrases of 1-4 beats.
    """
    if not solo_notes.notes or len(solo_notes.notes) < 2:
        return musicxml

    quarter_note_duration_s = 60.0 / beat_grid.bpm if beat_grid.bpm > 0 else 0.5
    beat_ticks = TICKS_PER_QUARTER
    slur_max_gap = beat_ticks // 4  # 32nd note = max gap within a slur

    sorted_notes = sorted(solo_notes.notes, key=lambda n: n.start_time)

    # Detect slur groups
    slur_groups: list[tuple[int, int]] = []  # (start_idx, end_idx) inclusive
    group_start = 0

    for i in range(1, len(sorted_notes)):
        prev = sorted_notes[i - 1]
        curr = sorted_notes[i]

        gap_ticks = _seconds_to_ticks(curr.start_time - (prev.start_time + prev.duration), quarter_note_duration_s)
        pitch_change = abs(curr.pitch - prev.pitch)

        # Break slur if gap is too large or pitch jump is too big
        is_legato = gap_ticks <= slur_max_gap and pitch_change <= 7
        # Also break if group is longer than 4 beats
        group_duration_ticks = _seconds_to_ticks(
            sorted_notes[i].start_time + sorted_notes[i].duration - sorted_notes[group_start].start_time,
            quarter_note_duration_s,
        )
        too_long = group_duration_ticks > beat_ticks * 4

        if not is_legato or too_long:
            if i - group_start >= 2:  # Need at least 2 notes for a slur
                slur_groups.append((group_start, i - 1))
            group_start = i

    # Final group
    if len(sorted_notes) - group_start >= 2:
        slur_groups.append((group_start, len(sorted_notes) - 1))

    if not slur_groups:
        return musicxml

    # Build slur map: note_idx -> slur type
    slur_map: dict[int, str] = {}
    for start, end in slur_groups:
        slur_map[start] = "start"
        slur_map[end] = "stop"

    # Inject slurs into XML
    lines = musicxml.split("\n")
    result_lines: list[str] = []
    note_idx = 0

    for line in lines:
        result_lines.append(line)
        if line.strip() == "</note>" and note_idx in slur_map:
            slur_type = slur_map[note_idx]
            slur_line = f"        <slur type=\"{slur_type}\" number=\"1\"/>"
            # Insert into <notations>
            for j in range(len(result_lines) - 1, -1, -1):
                if "</notations>" in result_lines[j]:
                    result_lines.insert(j, slur_line)
                    break
                if "<notations" in result_lines[j]:
                    for k in range(j, len(result_lines)):
                        if "</notations>" in result_lines[k]:
                            result_lines.insert(k, slur_line)
                            break
                    break
        if line.strip() == "</note>":
            note_idx += 1

    return "\n".join(result_lines)

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

            m21_chord_str = _harmoniq_chord_to_music21(chord_event.chord, chord_event.bass)
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

    # 6. Commit 108: Inject comprehensive MusicXML notation elements
    # Order matters: divisions first, then defaults, then note-level annotations
    musicxml_output = _inject_divisions(musicxml_output)
    musicxml_output = _inject_defaults_block(musicxml_output)
    musicxml_output = _inject_tuplet_time_modification(musicxml_output, solo_notes, beat_grid)
    musicxml_output = _inject_beams(musicxml_output, beat_grid)
    musicxml_output = _inject_dynamics(musicxml_output, solo_notes, beat_grid)
    musicxml_output = _inject_articulations(musicxml_output, solo_notes, beat_grid)
    musicxml_output = _inject_slurs(musicxml_output, solo_notes, beat_grid)
    musicxml_output = _inject_chord_diagrams(musicxml_output, chord_timeline, beat_grid)

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


_HARMONIQ_TO_MUSIC21_QUALITY_MAP: dict[str, str] = {
    # Core triads
    "maj": "", "min": "m", "m": "m", "dim": "dim", "dim7": "dim7", "aug": "aug",
    # 7th chords
    "7": "7", "maj7": "maj7", "min7": "m7", "m7": "m7",
    # Suspended
    "7sus4": "7sus4", "sus4": "sus4", "sus2": "sus2",
    # 6th chords
    "6": "6", "min6": "m6", "m6": "m6",
    # Extended
    "9": "9", "maj9": "maj9", "min9": "m9", "m9": "m9",
    "11": "11", "13": "13",
    # Altered dominants
    "7#9": "7#9", "7b9": "7b9", "7#5": "7#5", "7b5": "7b5", "alt7": "7alt",
}


def _harmoniq_chord_to_music21(chord_symbol: str, bass: str | None = None) -> str:
    """Convert Harmoniq chord format (e.g. 'C:maj', 'F#:min7') to music21 format ('C', 'F#m7').

    music21's ChordSymbol expects standard chord abbreviations like 'C', 'Cm', 'C7', 'Cmaj7'.
    Harmoniq uses a 'root:quality' format that music21 cannot parse directly.

    When ``bass`` differs from the chord root, appends ``/bass`` to produce a
    slash chord (e.g., ``C:maj`` with bass ``E`` → ``C/E``). music21's
    ChordSymbol parser natively recognises the slash format and emits the
    corresponding ``<bass>`` MusicXML element.

    Qualities not in the map fall back to ``quality`` itself, which usually
    causes music21 to fail and emit a "Could not parse chord symbol"
    warning; we keep the full set in :data:`_HARMONIQ_TO_MUSIC21_QUALITY_MAP`
    so every Harmoniq quality has an explicit, music21-compatible suffix.
    """
    if not chord_symbol:
        return chord_symbol
    parts = chord_symbol.split(":", 1)
    root = parts[0]
    if len(parts) < 2:
        if bass and bass != root:
            return f"{root}/{bass}"
        return root
    quality = parts[1].strip()
    if not quality:
        if bass and bass != root:
            return f"{root}/{bass}"
        return root
    suffix = _HARMONIQ_TO_MUSIC21_QUALITY_MAP.get(quality.lower(), quality)
    result = root + suffix
    if bass and bass != root:
        result = f"{result}/{bass}"
    return result

