"""Candidate string/fret positions for a MIDI pitch."""

from __future__ import annotations

from dataclasses import dataclass

from app.fretting.tuning import MAX_FRET, Tuning, standard


@dataclass(frozen=True, order=True)
class Position:
    """A playable string/fret cell (string 1 = high E)."""

    string: int
    fret: int


def candidates_for_pitch(
    pitch: int,
    tuning: Tuning,
    *,
    max_fret: int = MAX_FRET,
) -> list[Position]:
    """Return every valid ``(string, fret)`` for ``pitch`` under ``tuning``.

    Results follow string order (1 → 6); callers that need a cost-based
    choice should score them explicitly.
    """
    target = int(round(pitch))
    out: list[Position] = []
    for string in range(1, 7):
        fret = target - tuning.open_pitch(string)
        if 0 <= fret <= max_fret:
            out.append(Position(string=string, fret=fret))
    return out


def baseline_position(
    pitch: int,
    tuning: Tuning | None = None,
    *,
    max_fret: int = MAX_FRET,
) -> Position | None:
    """Reproduce ``allCellsForMidi``: lowest fret, then high E first.

    ``src/music/fretboardCell.ts`` sorts by ``(fret, row)`` where row 0 is
    the high E string, i.e. ``(fret, string)`` with string 1 = high E.
    """
    candidates = candidates_for_pitch(
        pitch, tuning or standard(), max_fret=max_fret
    )
    if not candidates:
        return None
    return min(candidates, key=lambda position: (position.fret, position.string))


def is_playable_pitch(
    pitch: int,
    tuning: Tuning | None = None,
    *,
    max_fret: int = MAX_FRET,
) -> bool:
    """Whether ``pitch`` has at least one valid position."""
    return bool(
        candidates_for_pitch(
            pitch, tuning or standard(), max_fret=max_fret
        )
    )
