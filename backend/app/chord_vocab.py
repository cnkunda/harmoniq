"""Shared chord vocabulary and interval definitions.

Single source of truth for the 277-class chord vocabulary used across
training, inference, and tests. Prevents drift between the training script
and inference pipeline.

Vocabulary: 23 qualities × 12 roots + 1 No-Chord = 277 total classes.
"""

from __future__ import annotations

ROOT_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

CHORD_INTERVALS: dict[str, list[int]] = {
    # Core triads
    "maj":  [0, 4, 7],
    "min":  [0, 3, 7],
    # 7th chords
    "7":    [0, 4, 7, 10],
    "maj7": [0, 4, 7, 11],
    "min7": [0, 3, 7, 10],
    # Extended
    "9":    [0, 4, 7, 10, 14],
    "min9": [0, 3, 7, 10, 14],
    "maj9": [0, 4, 7, 11, 14],
    "11":   [0, 4, 7, 10, 14, 17],
    "13":   [0, 4, 7, 10, 14, 17, 21],
    # Altered dominants
    "7#9":  [0, 4, 7, 10, 15],
    "7b9":  [0, 4, 7, 10, 13],
    "7#5":  [0, 4, 8, 10],
    "7b5":  [0, 4, 6, 10],
    "alt7": [0, 4, 6, 8, 10, 13, 15],
    # Suspended
    "sus2":  [0, 2, 7],
    "sus4":  [0, 5, 7],
    "7sus4": [0, 5, 7, 10],
    # Other
    "dim":   [0, 3, 6],
    "dim7":  [0, 3, 6, 9],
    "aug":   [0, 4, 8],
    "6":     [0, 4, 7, 9],
    "min6":  [0, 3, 7, 9],
}

CHORD_QUALITIES = list(CHORD_INTERVALS.keys())

CHORD_VOCAB = [f"{root}:{qual}" for qual in CHORD_QUALITIES for root in ROOT_NOTES] + ["N"]

CHORD_TO_IDX = {chord: i for i, chord in enumerate(CHORD_VOCAB)}

NUM_CLASSES = len(CHORD_VOCAB)  # 277

# MIREX 25-class vocabulary: 12 major + 12 minor + N
MIREX_QUALITY_MAP: dict[str, str] = {
    "maj": "maj", "min": "min",
    "7": "maj", "maj7": "maj", "9": "maj", "maj9": "maj",
    "11": "maj", "13": "maj",
    "7#9": "maj", "7b9": "maj", "7#5": "maj", "7b5": "maj", "alt7": "maj",
    "sus2": "maj", "sus4": "maj", "7sus4": "maj",
    "aug": "maj", "6": "maj",
    "min7": "min", "min9": "min", "min6": "min",
    "dim": "min", "dim7": "min",
}

MIREX_VOCAB: list[str] = (
    [f"{root}:maj" for root in ROOT_NOTES]
    + [f"{root}:min" for root in ROOT_NOTES]
    + ["N"]
)
MIREX_TO_IDX: dict[str, int] = {chord: i for i, chord in enumerate(MIREX_VOCAB)}
NUM_CLASSES_MIREX = 25

_CHORD_CLASS_QUALITIES: list[str] = []
for _q in CHORD_QUALITIES:
    for _ in range(12):
        _CHORD_CLASS_QUALITIES.append(_q)


def mirex_label(chord_277_idx: int) -> int:
    """Map a 277-class index to the corresponding 25-class MIREX index.

    N (index 276) maps to N (index 24).
    Chord classes map through MIREX_QUALITY_MAP to the nearest major/minor.
    """
    if chord_277_idx >= NUM_CLASSES - 1:
        return NUM_CLASSES_MIREX - 1
    quality = _CHORD_CLASS_QUALITIES[chord_277_idx]
    root = chord_277_idx % 12
    target_quality = MIREX_QUALITY_MAP.get(quality, "maj")
    return MIREX_TO_IDX[f"{ROOT_NOTES[root]}:{target_quality}"]
