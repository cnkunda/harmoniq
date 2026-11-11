"""Shared dataclasses for guitar tablature assignment.

String numbering is 1-6 with 1 = high E, matching ``app.guitar_position``,
the MusicXML technical elements, and the frontend fretboard rows.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class TabNote:
    """A note with pitch, timing, and an optional string/fret position.

    ``string``/``fret`` are ``None`` until an assignment pass fills them.
    """

    pitch: int
    onset: float
    offset: float
    velocity: int | None = None
    string: int | None = None
    fret: int | None = None

    @property
    def duration(self) -> float:
        """Note duration in seconds (never negative)."""
        return max(0.0, float(self.offset) - float(self.onset))

    def with_position(self, string: int | None, fret: int | None) -> "TabNote":
        """Return a copy carrying a string/fret position."""
        return replace(self, string=string, fret=fret)

    def with_pitch(self, pitch: int) -> "TabNote":
        """Return a copy transposed to ``pitch`` (position unchanged)."""
        return replace(self, pitch=int(pitch))
