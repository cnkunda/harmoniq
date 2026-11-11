"""Assign persisted string/fret positions to transcribed solo notes (F1).

Uses the W4 playability-aware assignment (``app.fretting``) so the LessonJSON,
MusicXML, and practice fretboard all share one authoritative position instead of
each inferring a cell from pitch.
"""
from __future__ import annotations

import logging
import os

from app.fretting import TabNote, assign_tab, get_tuning, standard
from app.schemas import SoloNotes

logger = logging.getLogger("harmoniq.tab_assignment")

_MAX_FRET = 24


def assign_solo_note_positions(solo_notes: SoloNotes) -> int:
    """Fill ``string``/``fret`` on every assignable note; returns the count.

    Honors:
    - ``HARMONIQ_SKIP_TAB_ASSIGNMENT=1`` — leave positions untouched.
    - ``HARMONIQ_TAB_ASSIGNMENT_MODE`` — ``dp`` (default) or ``baseline``.
    - ``HARMONIQ_TAB_TUNING`` — tuning name (default standard).
    """
    if os.getenv("HARMONIQ_SKIP_TAB_ASSIGNMENT", "").strip() == "1":
        return 0
    if not solo_notes.notes:
        return 0

    mode = os.getenv("HARMONIQ_TAB_ASSIGNMENT_MODE", "dp").strip().lower() or "dp"
    if mode not in {"dp", "baseline"}:
        logger.warning("Unknown HARMONIQ_TAB_ASSIGNMENT_MODE=%r; using 'dp'", mode)
        mode = "dp"
    tuning_name = os.getenv("HARMONIQ_TAB_TUNING", "standard").strip() or "standard"
    try:
        tuning = get_tuning(tuning_name)
    except ValueError:
        logger.warning("Unknown HARMONIQ_TAB_TUNING=%r; using standard", tuning_name)
        tuning = standard()

    tab_notes = [
        TabNote(
            pitch=int(note.pitch),
            onset=float(note.start_time),
            offset=float(note.start_time + note.duration),
            velocity=int(note.velocity),
        )
        for note in solo_notes.notes
    ]
    assignment = assign_tab(tab_notes, tuning=tuning, mode=mode, max_fret=_MAX_FRET)

    assigned = 0
    for solo_note, tab_note in zip(solo_notes.notes, assignment.notes):
        if tab_note.string is not None and tab_note.fret is not None:
            solo_note.string = int(tab_note.string)
            solo_note.fret = int(tab_note.fret)
            assigned += 1
    unassignable = len(assignment.unassignable)
    if unassignable:
        logger.warning(
            "tab assignment left %d/%d notes without a position (mode=%s, tuning=%s)",
            unassignable,
            len(solo_notes.notes),
            mode,
            tuning_name,
        )
    return assigned
