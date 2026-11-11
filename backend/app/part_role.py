"""Per-note lead/rhythm classification for transcribed solo notes (T3).

The section-level ``performance_profile.part_role`` is a coarse summary. This
module tags each note so the UI can reason about mixed sections and exports can
separate voices.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.schemas import SoloNote, SoloNotes

_SIMULTANEOUS_TOLERANCE_S = 0.05
_CHORD_CHANGE_TOLERANCE_S = 0.12
_RHYTHM_MAX_DURATION_S = 0.18


@dataclass
class PartRoleStats:
    lead: int = 0
    rhythm: int = 0

    @property
    def total(self) -> int:
        return self.lead + self.rhythm


def assign_solo_note_part_roles(
    solo_notes: SoloNotes,
    *,
    chord_timestamps: list[float] | None = None,
) -> PartRoleStats:
    """Tag every note as ``lead`` or ``rhythm`` and return the counts.

    Heuristics (deterministic and explainable):
    - notes attacked nearly together (≤50 ms) are a strum/rhythm group;
    - short notes (≤180 ms) landing on a chord change are rhythmic comping;
    - everything else is lead melody.
    """
    notes = list(solo_notes.notes)
    if not notes:
        return PartRoleStats()

    ordered = sorted(notes, key=lambda note: (float(note.start_time), float(note.pitch)))
    rhythms: set[int] = set()

    # 1. Simultaneous attack groups -> rhythm.
    group_start = 0
    for index in range(1, len(ordered) + 1):
        if index == len(ordered) or (
            float(ordered[index].start_time) - float(ordered[group_start].start_time)
            > _SIMULTANEOUS_TOLERANCE_S
        ):
            if index - group_start >= 2:
                for grouped in range(group_start, index):
                    rhythms.add(id(ordered[grouped]))
            group_start = index

    # 2. Short notes on chord changes -> rhythm comping.
    changes = sorted(float(ts) for ts in (chord_timestamps or []))
    if changes:
        change_index = 0
        for note in ordered:
            duration = float(note.duration)
            if duration > _RHYTHM_MAX_DURATION_S:
                continue
            start = float(note.start_time)
            while change_index < len(changes) - 1 and changes[change_index + 1] <= start:
                change_index += 1
            if abs(changes[change_index] - start) <= _CHORD_CHANGE_TOLERANCE_S:
                rhythms.add(id(note))

    stats = PartRoleStats()
    for note in notes:
        role: str = "rhythm" if id(note) in rhythms else "lead"
        note.part_role = role  # type: ignore[assignment]
        if role == "rhythm":
            stats.rhythm += 1
        else:
            stats.lead += 1
    return stats


def dominant_part_role(stats: PartRoleStats) -> str | None:
    """Return ``lead``/``rhythm``/``mixed`` (None when empty)."""
    if stats.total == 0:
        return None
    if stats.rhythm == 0:
        return "lead"
    if stats.lead == 0:
        return "rhythm"
    return "mixed"
