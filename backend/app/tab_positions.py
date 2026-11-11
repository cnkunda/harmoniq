"""Guitar Pro position maps for full + alternate tablature (F2).

The full tab uses the playability-aware DP assignment; the alternate tab picks a
different (mid-neck) position for the same pitches so the two charts are
genuinely different fingerings rather than the same notes with a new title.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from app.fretting import TabNote, assign_tab, candidates_for_pitch, standard
from app.pipeline_proof import NoteEvent, beat_slot_index_for_time

_MAX_FRET = 24
_ALT_FRET_MIN = 5
_ALT_FRET_MAX = 12
_ALT_TARGET_FRET = 8.0
_ALT_MAX_JUMP = 7


def chosen_beat_notes(
    events: Sequence[NoteEvent],
    *,
    bpm: float,
    beat_times_s: Sequence[float] | None = None,
) -> dict[int, NoteEvent]:
    """Mirror the GP5 writer's beat-slot selection (one strongest pitch per slot)."""
    by_slot: dict[int, list[NoteEvent]] = defaultdict(list)
    for ev in events:
        slot = beat_slot_index_for_time(float(ev.start_s), beat_times_s, bpm=bpm)
        by_slot[slot].append(ev)
    return {
        slot: max(slot_events, key=lambda e: (float(e.amplitude), int(e.pitch_midi)))
        for slot, slot_events in by_slot.items()
        if slot_events
    }


def _position_map_from_assignment(
    chosen: dict[int, NoteEvent],
    assignment_mode: str = "dp",
) -> dict[tuple[int, int], tuple[int, int]]:
    slots = sorted(chosen)
    if not slots:
        return {}
    tab_notes = [
        TabNote(pitch=int(chosen[slot].pitch_midi), onset=float(index), offset=float(index) + 0.5, velocity=100)
        for index, slot in enumerate(slots)
    ]
    assignment = assign_tab(tab_notes, mode=assignment_mode, max_fret=_MAX_FRET)
    out: dict[tuple[int, int], tuple[int, int]] = {}
    for index, tab_note in enumerate(assignment.notes):
        if tab_note.string is None or tab_note.fret is None:
            continue
        slot = slots[index]
        out[(slot, int(tab_note.pitch))] = (int(tab_note.string), int(tab_note.fret))
    return out


def primary_positions(
    chosen: dict[int, NoteEvent],
    *,
    assignment_mode: str = "dp",
) -> dict[tuple[int, int], tuple[int, int]]:
    """Playability-aware positions for the full tab."""
    return _position_map_from_assignment(chosen, assignment_mode=assignment_mode)


def alternate_positions(
    chosen: dict[int, NoteEvent],
) -> dict[tuple[int, int], tuple[int, int]] | None:
    """Mid-neck alternate fingering; ``None`` when it would match the primary map."""
    primary = primary_positions(chosen)
    if not chosen:
        return None
    tuning = standard()
    alt: dict[tuple[int, int], tuple[int, int]] = {}
    previous_fret: float | None = None
    for slot in sorted(chosen):
        pitch = int(chosen[slot].pitch_midi)
        candidates = candidates_for_pitch(pitch, tuning, max_fret=_MAX_FRET)
        if not candidates:
            continue
        mid_neck = [c for c in candidates if _ALT_FRET_MIN <= c.fret <= _ALT_FRET_MAX]
        pool = mid_neck or candidates
        if previous_fret is not None and mid_neck:
            pool = [c for c in mid_neck if abs(c.fret - previous_fret) <= _ALT_MAX_JUMP] or mid_neck or candidates
        anchor = previous_fret if previous_fret is not None else _ALT_TARGET_FRET
        choice = min(pool, key=lambda c: (abs(c.fret - anchor), -c.string))
        alt[(slot, pitch)] = (choice.string, choice.fret)
        previous_fret = float(choice.fret)
    if not alt or alt == primary:
        return None
    return alt
