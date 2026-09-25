"""MT3 Voicing & Position Recognizer — CAGED shape detection from event stream.

Analyzes the actual MIDI pitch distribution per chord window to determine
which CAGED shape (E/A/C/D/G) the guitarist is playing and at what fret
position. Uses MIDI pitch matching against expected voicing patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.caged_shapes import CAGED_SHAPES
from app.mt3.schemas import Mt3Event

# Confidence threshold for accepting a voicing detection
_VOICING_CONFIDENCE_THRESHOLD = 0.6

# Standard tuning open string MIDI pitches: string → MIDI
_OPEN_STRING_MIDI: dict[int, int] = {
    1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40,
}


@dataclass
class VoicingResult:
    """Result of voicing detection for a chord time window."""
    shape: str | None       # 'E', 'A', 'C', 'D', 'G' or None
    position: int | None    # 0-12 fret position
    confidence: float       # 0.0-1.0


def _midi_pitches_from_active_notes(
    active_notes: dict[int, list[Mt3Event]],
) -> set[int]:
    """Collect all unique MIDI pitches from an active_notes per-pitch-class dict."""
    pitches: set[int] = set()
    for events in active_notes.values():
        for e in events:
            pitches.add(e.pitch)
    return pitches


def _compute_expected_pitches(
    shape_name: str,
    position: int,
) -> set[int]:
    """Compute the expected MIDI pitches for a CAGED shape at a given position."""
    shape = CAGED_SHAPES[shape_name]
    pitches: set[int] = set()
    for i, string in enumerate(shape["strings"]):
        fret = shape["pattern"][i] + position
        midi = _OPEN_STRING_MIDI[string] + fret
        if 0 <= midi <= 127:
            pitches.add(midi)
    return pitches


def _compute_voicing_label(shape: str, position: int | None) -> str:
    """Build a human-readable voicing label like 'E-shape' or 'A-shape barre VII'."""
    if shape is None:
        return ""
    if position is not None and position > 0:
        roman_numerals = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
        roman = roman_numerals[position] if position < len(roman_numerals) else str(position)
        return f"{shape}-shape barre {roman}"
    return f"{shape}-shape (open)"


def recognize_voicing(
    active_notes: dict[int, list[Mt3Event]],
    chord_root: str,
    chord_quality: str,
) -> VoicingResult:
    """Recognize the CAGED voicing shape from a chord window's active notes.

    For each CAGED shape at each candidate root position, computes the
    expected set of MIDI pitches and checks what fraction of them are
    present in the active note set. This avoids per-string assignment
    ambiguity by matching directly on MIDI pitch values.

    Args:
        active_notes: Per-pitch-class active events for the chord window.
        chord_root: Root note name (e.g., 'C', 'F#').
        chord_quality: Quality string (e.g., 'maj', 'min7').

    Returns:
        VoicingResult with detected shape, position, and confidence.
    """
    if not active_notes:
        return VoicingResult(shape=None, position=None, confidence=0.0)

    active_pitches = _midi_pitches_from_active_notes(active_notes)
    if not active_pitches:
        return VoicingResult(shape=None, position=None, confidence=0.0)

    if len(active_pitches) < 3:
        return VoicingResult(shape=None, position=None, confidence=0.0)

    best_shape: str | None = None
    best_position: int | None = None
    best_score = 0.0

    for shape_name, shape_def in CAGED_SHAPES.items():
        shiftable = shape_def["shiftable"]
        max_candidate_pos = 12 if shiftable else 0

        for root_fret in range(max_candidate_pos + 1):
            expected_pitches = _compute_expected_pitches(shape_name, root_fret)

            if not expected_pitches:
                continue

            # Score = fraction of expected pitches present in active set
            match_count = sum(1 for p in expected_pitches if p in active_pitches)
            total = len(expected_pitches)
            raw_score = match_count / total if total > 0 else 0.0

            # Penalty for extra pitches not in the expected voicing
            extra_pitches = active_pitches - expected_pitches
            extra_penalty = len(extra_pitches) * 0.05

            score = max(0.0, min(1.0, raw_score - extra_penalty))

            if score > best_score:
                best_score = score
                best_shape = shape_name
                best_position = root_fret

    if best_score >= _VOICING_CONFIDENCE_THRESHOLD and best_shape is not None:
        return VoicingResult(
            shape=best_shape,
            position=best_position,
            confidence=round(best_score, 4),
        )

    return VoicingResult(shape=None, position=None, confidence=round(best_score, 4))
