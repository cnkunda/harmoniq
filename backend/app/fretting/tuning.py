"""Guitar tunings and capo conditioning for tablature assignment.

The open-string tuples are indexed by string number: index 0 is string 1
(high E), index 5 is string 6 (low E). This matches the rest of the repo
(``app.guitar_position.OPEN_STRING_MIDI``), just inverted.
"""

from __future__ import annotations

from dataclasses import dataclass

NUM_STRINGS = 6
MAX_FRET = 24

#: Standard tuning, high E → low E (MIDI).
STANDARD_OPEN_MIDI: tuple[int, ...] = (64, 59, 55, 50, 45, 40)

#: Drop-D tuning: the low E string drops to D2.
DROP_D_OPEN_MIDI: tuple[int, ...] = (64, 59, 55, 50, 45, 38)


@dataclass(frozen=True)
class Tuning:
    """A guitar tuning plus a capo position.

    ``open_midi`` holds the open-string pitches *without* the capo. The
    capo raises every string by ``capo`` semitones; tablature frets stay
    relative to the capo (fret 0 = the capo'd open string).
    """

    name: str
    open_midi: tuple[int, ...]
    capo: int = 0

    def __post_init__(self) -> None:
        if len(self.open_midi) != NUM_STRINGS:
            raise ValueError(
                f"tuning {self.name!r} must define {NUM_STRINGS} strings, "
                f"got {len(self.open_midi)}"
            )
        if self.capo < 0:
            raise ValueError(f"capo must be >= 0, got {self.capo}")
        for index, pitch in enumerate(self.open_midi):
            if not 0 <= int(pitch) <= 127:
                raise ValueError(
                    f"tuning {self.name!r} string {index + 1} has invalid "
                    f"MIDI pitch {pitch}"
                )

    def open_pitch(self, string: int) -> int:
        """Return the sounding open-string pitch for ``string`` (1-6)."""
        if not 1 <= string <= NUM_STRINGS:
            raise ValueError(f"string must be 1-{NUM_STRINGS}, got {string}")
        return int(self.open_midi[string - 1]) + self.capo

    def pitch_for(self, string: int, fret: int) -> int:
        """Return the MIDI pitch for a string/fret position."""
        if fret < 0:
            raise ValueError(f"fret must be >= 0, got {fret}")
        return self.open_pitch(string) + int(fret)

    def with_capo(self, capo: int) -> "Tuning":
        """Return the same tuning at a different capo position."""
        return Tuning(name=self.name, open_midi=self.open_midi, capo=capo)


def standard(capo: int = 0) -> Tuning:
    """Standard tuning (E2 A2 D3 G3 B3 E4)."""
    return Tuning("standard", STANDARD_OPEN_MIDI, capo)


def half_step_down(capo: int = 0) -> Tuning:
    """Eb standard (all strings one semitone down)."""
    return Tuning(
        "half_step_down",
        tuple(pitch - 1 for pitch in STANDARD_OPEN_MIDI),
        capo,
    )


def full_step_down(capo: int = 0) -> Tuning:
    """D standard (all strings two semitones down)."""
    return Tuning(
        "full_step_down",
        tuple(pitch - 2 for pitch in STANDARD_OPEN_MIDI),
        capo,
    )


def drop_d(capo: int = 0) -> Tuning:
    """Drop-D (low E string down to D2)."""
    return Tuning("drop_d", DROP_D_OPEN_MIDI, capo)


TUNING_FACTORIES = {
    "standard": standard,
    "half_step_down": half_step_down,
    "full_step_down": full_step_down,
    "drop_d": drop_d,
}


def get_tuning(name: str, capo: int = 0) -> Tuning:
    """Look up a tuning by name.

    Raises:
        ValueError: ``name`` is not a known tuning.
    """
    try:
        factory = TUNING_FACTORIES[name]
    except KeyError as exc:
        known = ", ".join(sorted(TUNING_FACTORIES))
        raise ValueError(f"unknown tuning {name!r}; known: {known}") from exc
    return factory(capo)
