"""Bass derivation and annotation normalization for the 170-class model.

Pure helpers shared by the real-dataset builder and the pseudo-label
pipeline (Phase 2). No file IO here — see ``scripts/chord_data_v2.py`` for
the per-dataset readers.

Bass rules (from the program spec):
  - Real datasets with note data: bass = lowest pitch class active at the
    window centre.
  - Annotation labels that already carry a bass (Harte ``/3`` degrees or
    ``/Gb`` pitch classes): resolve that bass instead.
  - Without either: unknown bass (``BASS_X_IDX``).
"""

from __future__ import annotations

import re

import numpy as np

from app.chord_vocab_170 import (
    BASS_X_IDX,
    N_IDX_170,
    QUALITIES_14,
    QUALITY_INTERVALS_170,
    ROOTS_12,
)

# Degree number → semitones from the root (before accidentals).
_DEGREE_SEMITONES: dict[int, int] = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11, 9: 14}

# Flat/sharp spelling → pitch class index (C = 0).
_PITCH_CLASS_BY_NAME: dict[str, int] = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "Fb": 4,
    "E#": 5, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8,
    "A": 9, "A#": 10, "Bb": 10, "B": 11, "Cb": 11,
}

# Shorthand qualities used by IDMT (``D7/C``) → 170 qualities.
SHORTHAND_QUALITY_MAP: dict[str, str | None] = {
    "": "maj",
    "maj": "maj",
    "M": "maj",
    "min": "min",
    "m": "min",
    "7": "7",
    "dom7": "7",
    "maj7": "maj7",
    "M7": "maj7",
    "min7": "min7",
    "m7": "min7",
    "dim": "dim",
    "dim7": "dim7",
    "aug": "aug",
    "6": "maj6",
    "maj6": "maj6",
    "min6": "min6",
    "m6": "min6",
    "sus2": "sus2",
    "sus4": "sus4",
    "sus": "sus4",
    "hdim7": "hdim7",
    "min7b5": "hdim7",
    "min75b": "hdim7",
    "minmaj7": "minmaj7",
    "minmaj79": "minmaj7",
    # Extended/altered → nearest supported (same policy as 277→170)
    "9": "7", "maj9": "maj7", "min9": "min7",
    "11": "7", "maj11": "maj7", "min11": "min7",
    "13": "7", "maj13": "maj7", "min13": "min7",
    "7113": "7", "1113": "7", "713": "7", "7913": "7", "913": "7",
    "79": "7", "79b": "7", "713b": "7", "75b": "7", "7sus4": "sus4",
    "sus9": "sus4", "maj79": "maj7", "min79": "min7",
    # Power chords carry no third; the 277-class pipeline treated them as
    # major, so keep that convention.
    "5": "maj", "B5": "maj",
}


def pitch_to_pitch_class(pitch: float) -> int:
    """Convert a MIDI pitch (float or int) to a pitch class index (C = 0)."""
    return int(round(float(pitch))) % 12


def pitch_class_name(pitch_class: int) -> str:
    """Return the canonical name for a 0-11 pitch class."""
    return ROOTS_12[int(pitch_class) % 12]


def pitch_class_from_name(name: str) -> int | None:
    """Resolve a note name (``C``, ``Gb``, ``F#``) to a pitch class, or None."""
    return _PITCH_CLASS_BY_NAME.get(name)


def active_pitches(
    notes: list[tuple[float, float, float]],
    time_s: float,
    *,
    epsilon: float = 1e-6,
) -> list[float]:
    """Return pitches sounding at ``time_s``.

    Args:
        notes: ``(start, end, pitch)`` tuples (seconds, MIDI pitch).
        time_s: Query time in seconds.
        epsilon: Interval inclusivity tolerance.
    """
    return [
        pitch for start, end, pitch in notes
        if start - epsilon <= time_s < end + epsilon
    ]


def count_active_pitches(notes: list[tuple[float, float, float]], time_s: float) -> int:
    """Number of distinct pitch classes sounding at ``time_s``."""
    return len({pitch_to_pitch_class(p) for p in active_pitches(notes, time_s)})


def bass_pitch_class_from_notes(
    notes: list[tuple[float, float, float]],
    time_s: float,
) -> int | None:
    """Lowest active pitch class at ``time_s``, or None when silent."""
    sounding = active_pitches(notes, time_s)
    if not sounding:
        return None
    return pitch_to_pitch_class(min(sounding))


def bass_from_degree(root: str, degree: str) -> int | None:
    """Resolve a Harte bass degree (``3``, ``b7``, ``b5``) to a pitch class.

    Degrees are metric intervals with optional accidentals, independent of
    chord quality (mir_eval convention).
    """
    match = re.fullmatch(r"([b#]*)(\d+)", degree.strip())
    root_pc = _PITCH_CLASS_BY_NAME.get(root)
    if not match or root_pc is None:
        return None
    accidentals, number = match.group(1), int(match.group(2))
    if number not in _DEGREE_SEMITONES:
        return None
    semitones = _DEGREE_SEMITONES[number]
    semitones += accidentals.count("#") - accidentals.count("b")
    return (root_pc + semitones) % 12


def normalize_quality(raw_quality: str) -> str | None:
    """Normalize an annotation quality to one of :data:`QUALITIES_14`.

    Handles RWC parenthesized alterations (``maj(*3)``, ``7(b9)``,
    ``sus4(b7)``) by reducing to the base quality, then the shorthand map.
    Returns None for unmappable qualities (callers report and drop them).
    """
    quality = raw_quality.strip()
    if quality in QUALITIES_14:
        return quality
    # Strip Harte parenthesized additions/alterations: maj(*3), 7(b9,#9)
    base = re.sub(r"\(.*\)$", "", quality).strip()
    if base != quality:
        # sus4(b7) / sus2(b7) are the seventh-suspended chords → base already
        if base in QUALITIES_14:
            return base
        return SHORTHAND_QUALITY_MAP.get(base)
    return SHORTHAND_QUALITY_MAP.get(quality)


def parse_annotation_label(
    label: str,
) -> tuple[str, str, int | None] | None:
    """Parse a Harte/shorthand annotation chord label.

    Accepts ``"C:maj"``, ``"Eb:maj/3"``, ``"D7/C"``, ``"G"``, ``"N"``.
    Returns ``(root, quality_170, bass_pc_or_None)`` or None for N/unknown.
    """
    label = label.strip()
    if not label or label in ("N", "NC", "X"):
        return None

    body, _, raw_bass = label.partition("/")
    if ":" in body:
        root, quality = body.split(":", 1)
    else:
        # Shorthand: root is 1-2 chars (letter + optional accidental)
        match = re.match(r"^([A-G][#b]?)(.*)$", body)
        if not match:
            return None
        root, quality = match.group(1), match.group(2)

    if pitch_class_from_name(root) is None:
        return None
    normalized = normalize_quality(quality)
    if normalized is None:
        return None

    bass: int | None = None
    if raw_bass:
        candidate = pitch_class_from_name(raw_bass)
        if candidate is not None:
            bass = candidate
        else:
            bass = bass_from_degree(root, raw_bass)
        if bass is None:
            return None
    return root, normalized, bass


def is_root_position(root: str, bass_pc: int | None) -> bool:
    """True when the bass is the root (or unknown)."""
    if bass_pc is None:
        return True
    return pitch_class_from_name(root) == bass_pc


def chord_tones(root: str, quality: str) -> set[int]:
    """Absolute pitch classes of a chord's interval template."""
    root_pc = ROOTS_12.index(root)
    return {(root_pc + interval) % 12 for interval in QUALITY_INTERVALS_170[quality]}


def pitch_shift_labels(
    chord: np.ndarray | list[int],
    bass: np.ndarray | list[int],
    shift: int,
    *,
    space: str = "170",
) -> tuple[np.ndarray, np.ndarray]:
    """Transpose chord and bass labels by ``shift`` semitones.

    Supports the 170 layout (quality-major), the legacy 277 layout
    (quality-major, N = 276) and the MIREX-25 layout (12 major + 12 minor +
    N). N/X labels are unchanged; unknown bass stays unknown.
    """
    chord_arr = np.asarray(chord).copy()
    bass_arr = np.asarray(bass).copy()
    shift = int(shift) % 12
    if shift == 0:
        return chord_arr, bass_arr

    if space in ("170", "277"):
        n_index = N_IDX_170 if space == "170" else 276
        chord_mask = chord_arr < n_index
        quality = chord_arr[chord_mask] // 12
        root = chord_arr[chord_mask] % 12
        chord_arr[chord_mask] = quality * 12 + ((root + shift) % 12)
    elif space == "mirex25":
        major = chord_arr < 12
        minor = (chord_arr >= 12) & (chord_arr < 24)
        chord_arr[major] = (chord_arr[major] + shift) % 12
        chord_arr[minor] = 12 + ((chord_arr[minor] - 12 + shift) % 12)
    else:
        raise ValueError(f"unknown label space: {space}")

    bass_mask = bass_arr != BASS_X_IDX
    bass_arr[bass_mask] = (bass_arr[bass_mask] + shift) % 12
    return chord_arr, bass_arr


INVERSION_LABELS: tuple[str, ...] = ("root", "first", "second", "third", "other")
NUM_INVERSION_CLASSES = len(INVERSION_LABELS)


def inversion_class(chord_idx: int, bass_idx: int) -> int:
    """Inversion class of a chord given its bass.

    0 = root position, 1/2/3 = first/second/third inversion (bass is the
    chord's 2nd/3rd/4th interval), 4 = other/unknown (including no chord or
    an unknown bass).
    """
    from app.chord_vocab_170 import BASS_X_IDX, N_IDX_170, QUALITIES_14, QUALITY_INTERVALS_170

    chord_idx = int(chord_idx)
    bass_idx = int(bass_idx)
    if chord_idx >= N_IDX_170 or bass_idx == BASS_X_IDX:
        return 4
    quality = QUALITIES_14[chord_idx // 12]
    root = chord_idx % 12
    semitone = (bass_idx - root) % 12
    intervals = [interval % 12 for interval in QUALITY_INTERVALS_170[quality]]
    if semitone not in intervals:
        return 4
    position = intervals.index(semitone)
    return position if position < 4 else 4


def compose_bass_from_inversion(chord_idx: int, inversion_idx: int) -> int:
    """Bass pitch class implied by (chord, inversion), or -1 if unknown."""
    from app.chord_vocab_170 import N_IDX_170, QUALITIES_14, QUALITY_INTERVALS_170

    chord_idx = int(chord_idx)
    inversion_idx = int(inversion_idx)
    if chord_idx >= N_IDX_170 or inversion_idx >= 4:
        return -1
    quality = QUALITIES_14[chord_idx // 12]
    root = chord_idx % 12
    intervals = [interval % 12 for interval in QUALITY_INTERVALS_170[quality]]
    if inversion_idx >= len(intervals):
        return -1
    return (root + intervals[inversion_idx]) % 12
