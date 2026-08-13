#!/usr/bin/env python3
"""Canonical chord vocabulary + annotation label mapping (Commit 101).

Maps free-form annotation strings from Isophonics/Billboard/JAAH ``.lab``
files and GuitarSet JAMS chord values onto the production class vocabulary
used by ``build_chord_tflite.py`` / ``chord_inference.py``:

    23 qualities x 12 roots + 1 No-Chord (277 total)

Annotation strings are far richer than the model vocabulary: interval lists
like ``(3,5,b7,b9)``, slash chords (``A/5``), ``hdim7``, ``sus4(b7)``,
section labels (``verse``, ``N``), and omission hints (``9(*3)``).  Rare
qualities with no direct match are mapped to the closest class by pitch-class
set distance (symmetric difference), tie-broken by modifier-tone containment
then frequency priority.

This module must stay importable without TensorFlow so the vocabulary tests
stay fast; the constants are asserted to match ``build_chord_tflite.py``
exactly by ``tests/test_real_label_vocab.py``.
"""

from __future__ import annotations

import re
from typing import Optional

ROOT_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

CHORD_INTERVALS = {
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

CHORD_VOCAB = [f"{root}:{quality}" for quality in CHORD_INTERVALS for root in ROOT_NOTES] + ["N"]

CHORD_CLASS_MAP = [(ROOT_NOTES.index(root), quality) for quality in CHORD_INTERVALS for root in ROOT_NOTES]
CHORD_CLASS_MAP.append((-1, "N"))

NUM_CLASSES = len(CHORD_CLASS_MAP)          # 277
NO_CHORD_IDX = NUM_CLASSES - 1              # index of "N"

# Quality groups for per-category accuracy tracking (Commit 98d / 101)
QUALITY_GROUPS = {
    "triad":           {"maj", "min"},
    "extended":        {"7", "maj7", "min7", "9", "min9", "maj9", "11", "13"},
    "altered":         {"7#9", "7b9", "7#5", "7b5", "alt7"},
    "suspended_other": {"sus2", "sus4", "7sus4", "dim", "dim7", "aug", "6", "min6"},
    "no_chord":        {"N"},
}

# Class-index membership per group (precomputed for fast masking)
QUALITY_GROUP_MASKS = {
    group: {idx for idx in range(NUM_CLASSES) if CHORD_CLASS_MAP[idx][1] in qualities}
    for group, qualities in QUALITY_GROUPS.items()
}

# Different spellings resolve to the same semitone offset from the root.
_INTERVAL_SEMITONES = {
    "1": 0, "b1": 0, "#1": 1,
    "b2": 1, "2": 2, "#2": 3,
    "b3": 3, "3": 4, "#3": 5,
    "4": 5, "#4": 6, "b5": 6,
    "5": 7, "#5": 8, "b6": 8,
    "6": 9, "bb7": 9, "#6": 10,
    "b7": 10, "7": 11, "#7": 12,
    "b9": 13, "9": 14, "#9": 15,
    "b11": 16, "11": 17, "#11": 18,
    "b13": 20, "13": 21, "#13": 22,
}

_FLAT_TO_SHARP = {"Cb": "B", "Db": "C#", "Eb": "D#", "Fb": "E", "Gb": "F#", "Ab": "G#", "Bb": "A#"}

_COMPOUND_PCS = {
    "minmaj7": {0, 3, 7, 11},
    "min7b5": {0, 3, 6, 10},
    "hdim7": {0, 3, 6, 10},
    "maj7b5": {0, 4, 6, 11},
}

_SUS_FAMILY = {"sus2", "sus4", "7sus4"}

_SECTION_LABELS = {
    "n", "nc", "n/a", "none", "silence", "intro", "verse", "versea", "verseb",
    "versec", "versed", "half_verse", "half-verse", "refrain", "refraina",
    "refrainb", "half_refrain", "half-refrain", "pre-chorus", "pre_chorus",
    "chorus", "bridge", "bridgea", "bridgeb", "half_bridge", "half-bridge",
    "break", "breaka", "breakb", "outro", "interlude", "solo", "instrumental",
    "instrumental_solo", "instrumental_so", "ad_lib", "ad-lib", "new_point",
    "section_x", "section_y", "section_z",
}

_ALIAS_QUALITY = {
    "m": "min", "minor": "min", "major": "maj", "dom": "7", "dom7": "7",
    "sus": "sus4", "7sus": "7sus4", "maj6": "6",
}

# Tie-break order: common classes win before rare ones when pitch-class
# distance, overlap, and modifier containment are all equal.
_QUALITY_PRIORITY = [
    "maj", "min", "7", "min7", "maj7", "9", "min9", "maj9", "11", "13",
    "dim", "dim7", "aug", "6", "min6", "sus4", "sus2", "7sus4",
    "7#9", "7b9", "7#5", "7b5", "alt7",
]


def _pcs(intervals: list[int]) -> set[int]:
    return {iv % 12 for iv in intervals}


def nearest_quality(pcs: set[int], added: Optional[set[int]] = None,
                    candidates: Optional[list[str]] = None) -> str:
    """Return the vocabulary quality whose pitch classes are closest.

    Score = (symmetric difference size, -modifier-tone containment,
             -overlap size, priority index).  ``added`` carries the explicit
    alteration tones from a paren modifier so chords like ``7(#5)`` prefer
    ``7#5`` over plain ``7`` on a tie.
    """
    pool = candidates if candidates is not None else list(CHORD_INTERVALS)
    added = added or set()
    best: Optional[tuple[int, int, int, int, str]] = None
    for quality in pool:
        cand = _pcs(CHORD_INTERVALS[quality])
        containment = len(cand & added)
        score = (len(pcs ^ cand), -containment, -len(pcs & cand), _QUALITY_PRIORITY.index(quality))
        if best is None or score < best[:4]:
            best = (*score, quality)
    return best[4]


def _root_index(root: str) -> int:
    root = _FLAT_TO_SHARP.get(root, root)
    if root in ROOT_NOTES:
        return ROOT_NOTES.index(root)
    return -1


def _split_root(rest: str) -> tuple[int, str]:
    """Split 'G', 'Bb', 'F#min7' into (root_idx, remainder)."""
    head = rest[:2]
    if len(head) == 2 and head[0] in "ABCDEFG" and head[1] in "#b":
        idx = _root_index(head)
        return idx, rest[2:]
    if rest and rest[0] in "ABCDEFG":
        idx = _root_index(rest[0])
        return idx, rest[1:]
    return -1, rest


def interval_tokens_to_pcs(tokens: list[str], with_root: bool = True) -> set[int]:
    """Convert interval tokens (['3','5','b7','b9']) to a pitch-class set.

    Omission tokens ('*3') are ignored here; callers handle them by removing
    the corresponding pitch class from the base set.
    """
    pcs: set[int] = {0} if with_root else set()
    for token in tokens:
        key = token.replace("*", "")
        semitone = _INTERVAL_SEMITONES.get(key)
        if semitone is not None:
            pcs.add(semitone % 12)
    return pcs


def _parse_quality_token(rest: str) -> Optional[str]:
    """Parse the quality fragment (after the root) into a vocabulary quality."""
    if not rest:
        return "maj"

    if rest in _ALIAS_QUALITY:
        return _ALIAS_QUALITY[rest]

    if rest.startswith("(") and rest.endswith(")"):
        tokens = [t for t in rest[1:-1].split(",") if t]
        if "#5" in tokens and {"#9", "b9", "b13"} & set(tokens):
            return "alt7"
        return nearest_quality(interval_tokens_to_pcs(tokens, with_root=True))

    match = re.match(r"^([A-Za-z#b0-9]*)(?:\(([^)]*)\))?$", rest)
    if not match:
        return None
    base, paren = match.group(1), match.group(2)

    if base == "":
        return None

    if base in _ALIAS_QUALITY:
        base = _ALIAS_QUALITY[base]

    paren_tokens = [t for t in paren.split(",") if t] if paren else []

    base_pcs = _base_pcs(base)

    if not base_pcs:
        if re.fullmatch(r"[0-9]+", base):
            return nearest_quality(interval_tokens_to_pcs([base], with_root=True))
        return None

    added: set[int] = set()
    for token in paren_tokens:
        if token.startswith("*"):
            semitone = _INTERVAL_SEMITONES.get(token.replace("*", ""))
            if semitone is not None:
                base_pcs.discard(semitone % 12)
        else:
            semitone = _INTERVAL_SEMITONES.get(token)
            if semitone is not None:
                added.add(semitone % 12)
    pcs = base_pcs | added

    candidates = None
    has_sus_hint = any(t in {"2", "4"} for t in paren_tokens)
    if base in _SUS_FAMILY or has_sus_hint:
        if 3 not in pcs and 4 not in pcs:
            candidates = sorted(_SUS_FAMILY, key=_QUALITY_PRIORITY.index)

    return nearest_quality(pcs, added=added, candidates=candidates)


def _base_pcs(base: str) -> set[int]:
    intervals = CHORD_INTERVALS.get(base)
    if intervals is not None:
        return _pcs(intervals)
    return _COMPOUND_PCS.get(base, set()).copy()


def parse_annotation_label(label: str) -> Optional[tuple[int, str]]:
    """Parse an annotation label into (root_idx, quality) or None for no-chord.

    Handles: plain roots ('G' -> maj), colon forms ('Bb:7', 'F#min7'),
    flats ('Ebmaj7'), interval lists ('C:(3,5,b7,b9)'), slash chords
    ('A/5' -> A maj), paren composites ('G:sus4(b7)', 'C:7(#9)'),
    omission hints ('C:9(*3)'), half-diminished ('E:hdim7'), and no-chord /
    section labels ('N', 'verse', 'silence' -> None).
    """
    cleaned = label.strip()
    if not cleaned:
        return None

    lowered = cleaned.lower().replace(" ", "_")
    if lowered in _SECTION_LABELS or lowered.startswith("section_"):
        return None

    root_idx, rest = _split_root(cleaned)
    if root_idx < 0:
        return None

    rest = rest.lstrip(":").strip()
    rest = rest.split("/")[0].strip()

    if not rest:
        return (root_idx, "maj")

    if rest.lower() in _SECTION_LABELS:
        return None

    quality = _parse_quality_token(rest)
    if quality is None:
        return None
    return (root_idx, quality)


def annotation_to_class_index(label: str) -> int:
    """Parse an annotation label into its 277-class index (N for no-chord)."""
    parsed = parse_annotation_label(label)
    if parsed is None:
        return NO_CHORD_IDX
    root_idx, quality = parsed
    for i, (ri, q) in enumerate(CHORD_CLASS_MAP):
        if ri == root_idx and q == quality:
            return i
    return NO_CHORD_IDX