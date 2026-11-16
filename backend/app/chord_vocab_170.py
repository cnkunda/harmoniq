"""170-class chord vocabulary and bass/inversion labels (Chord 170 program).

Single source of truth for the v2 chord model vocabulary: 12 roots ×
14 qualities + N (no chord) + X (unknown/ambiguous) = 170 classes, plus a
separate 13-class bass head (12 pitch classes + X = unknown bass) so slash
chords can be composed without inflating the flat softmax.

Mapping from the legacy 277-class vocabulary is explicit and tested —
see ``QUALITY_MAP_277_TO_170`` and :func:`map_277_to_170`. Two of the 14
qualities (``minmaj7``, ``hdim7``) have no 277-class source: they receive
labels only from real datasets and pseudo-labels going forward. The 170
vocabulary therefore does NOT silently claim 277-class coverage of
9/11/13/alt7 — those collapse to the nearest supported quality.
"""

from __future__ import annotations

ROOTS_12: list[str] = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

QUALITIES_14: list[str] = [
    "maj", "min", "dim", "aug",
    "min6", "maj6", "min7", "minmaj7",
    "maj7", "7", "dim7", "hdim7",
    "sus2", "sus4",
]

# Interval definitions (semitones from root). Qualities that also exist in
# the 277-class vocabulary reuse app.chord_vocab.CHORD_INTERVALS definitions
# verbatim; minmaj7 and hdim7 are new.
QUALITY_INTERVALS_170: dict[str, list[int]] = {
    "maj":     [0, 4, 7],
    "min":     [0, 3, 7],
    "dim":     [0, 3, 6],
    "aug":     [0, 4, 8],
    "min6":    [0, 3, 7, 9],
    "maj6":    [0, 4, 7, 9],
    "min7":    [0, 3, 7, 10],
    "minmaj7": [0, 3, 7, 11],
    "maj7":    [0, 4, 7, 11],
    "7":       [0, 4, 7, 10],
    "dim7":    [0, 3, 6, 9],
    "hdim7":   [0, 3, 6, 10],
    "sus2":    [0, 2, 7],
    "sus4":    [0, 5, 7],
}

CHORD_VOCAB_170: list[str] = (
    [f"{root}:{qual}" for qual in QUALITIES_14 for root in ROOTS_12]
    + ["N", "X"]
)

CHORD_TO_IDX_170: dict[str, int] = {label: i for i, label in enumerate(CHORD_VOCAB_170)}

N_IDX_170: int = len(CHORD_VOCAB_170) - 2  # 168
X_IDX_170: int = len(CHORD_VOCAB_170) - 1  # 169
NUM_CLASSES_170: int = len(CHORD_VOCAB_170)  # 170

# Bass head: 12 pitch classes + X (unknown bass). "N" is deliberately not a
# bass class — no-chord frames use the unknown-bass class.
BASS_VOCAB: list[str] = ROOTS_12 + ["X"]
BASS_TO_IDX: dict[str, int] = {bass: i for i, bass in enumerate(BASS_VOCAB)}
BASS_X_IDX: int = BASS_TO_IDX["X"]  # 12
NUM_CLASSES_BASS: int = len(BASS_VOCAB)  # 13

# Explicit 277-quality → 170-quality mapping (reviewed in the program spec).
QUALITY_MAP_277_TO_170: dict[str, str] = {
    # Identity / rename
    "maj": "maj", "min": "min", "7": "7", "maj7": "maj7", "min7": "min7",
    "dim": "dim", "dim7": "dim7", "aug": "aug",
    "6": "maj6", "min6": "min6",
    # Extended → nearest supported seventh
    "9": "7", "min9": "min7", "maj9": "maj7",
    "11": "7", "13": "7",
    # Altered dominants → dominant 7th
    "7#9": "7", "7b9": "7", "7#5": "7", "7b5": "7", "alt7": "7",
    # Suspended
    "sus2": "sus2", "sus4": "sus4", "7sus4": "sus4",
}


def map_277_to_170(chord_277_idx: int) -> int:
    """Map a 277-class index to its 170-class index.

    N (index 276) maps to N (168). Chord classes map the root unchanged and
    the quality through :data:`QUALITY_MAP_277_TO_170`. The original 277
    label remains recoverable from ``app.chord_vocab.CHORD_VOCAB`` for
    reporting.
    """
    from app.chord_vocab import CHORD_VOCAB, NUM_CLASSES

    if chord_277_idx >= NUM_CLASSES - 1:
        return N_IDX_170
    label = CHORD_VOCAB[chord_277_idx]
    root, quality_277 = label.split(":", 1)
    quality_170 = QUALITY_MAP_277_TO_170[quality_277]
    return CHORD_TO_IDX_170[f"{root}:{quality_170}"]


# Precomputed mapping table for fast vectorised use in the data loader.
def _build_map_277_to_170_table() -> list[int]:
    from app.chord_vocab import NUM_CLASSES

    return [map_277_to_170(i) for i in range(NUM_CLASSES)]


MAP_277_TO_170_TABLE: list[int] = _build_map_277_to_170_table()


# ---------------------------------------------------------------------------
# Label composition / parsing (slash chords)
# ---------------------------------------------------------------------------


def compose_label(root: str, quality: str | None, bass: str | None = None) -> str:
    """Compose a 170-class label with optional bass (slash chord).

    Args:
        root: Root note (e.g. ``"C"``), or ``"N"``/``"X"`` with ``quality=None``.
        quality: One of :data:`QUALITIES_14`, or ``None`` for N/X labels.
        bass: Optional bass pitch class. Slash is appended only when the bass
            is a real pitch class and differs from the root; ``None`` or
            ``"X"`` yields a plain label.

    Returns:
        e.g. ``"C:maj"`` (root position), ``"C:maj/E"`` (first inversion),
        ``"N"``, ``"X"``.
    """
    if quality is None:
        if root not in ("N", "X"):
            raise ValueError(f"N/X labels require quality=None, got root={root!r}")
        if bass not in (None, "X"):
            raise ValueError(f"N/X labels do not carry bass, got bass={bass!r}")
        return root
    if root not in ROOTS_12:
        raise ValueError(f"unknown root: {root!r}")
    if quality not in QUALITIES_14:
        raise ValueError(f"unknown quality: {quality!r}")
    label = f"{root}:{quality}"
    if bass is not None and bass != root and bass != "X":
        if bass not in ROOTS_12:
            raise ValueError(f"unknown bass: {bass!r}")
        label += f"/{bass}"
    return label


def parse_label(label: str) -> tuple[str, str | None, str | None]:
    """Parse a composed 170-class label.

    Accepts both the internal format (``"C:maj7/B"``) and the display format
    (``"Cmaj7/B"``).

    Returns:
        (root, quality, bass) where quality/bass may be ``None``
        (plain label / no slash). N and X parse to ``(label, None, None)``.
    """
    if not label:
        raise ValueError("empty chord label")
    if label in ("N", "X"):
        return label, None, None

    body = label
    bass: str | None = None
    if "/" in label:
        body, bass = label.split("/", 1)
    if ":" in body:
        root, quality = body.split(":", 1)
    else:
        # Display format: two-char roots are the sharp roots
        if body[:2] in ("C#", "D#", "F#", "G#", "A#"):
            root, quality = body[:2], body[2:]
        else:
            root, quality = body[:1], body[1:]
    if root not in ROOTS_12:
        raise ValueError(f"unknown root in label: {label!r}")
    if quality not in QUALITIES_14:
        raise ValueError(f"unknown quality in label: {label!r}")
    if bass is not None:
        if bass not in ROOTS_12:
            raise ValueError(f"unknown bass in label: {label!r}")
        if bass == root:
            bass = None  # root-position labels never carry an equal bass
    return root, quality, bass


def render_label(label: str) -> str:
    """Render a composed label for display (``"C:maj7/B"`` → ``"Cmaj7/B"``)."""
    root, quality, bass = parse_label(label)
    if quality is None:
        return root
    text = f"{root}{quality}"
    if bass is not None:
        text += f"/{bass}"
    return text


def label_to_indices(label: str) -> tuple[int, int]:
    """Convert a composed label to (chord_idx_170, bass_idx).

    The chord head is a flat 170-class softmax: slash labels resolve to
    their root-position class (the bass head predicts the bass separately,
    and is never a hard override of the chord head). For N/X labels the
    bass index is the unknown class. For plain labels the bass index is
    the root's own pitch class (root position = bass == root).
    """
    if label in ("N", "X"):
        return (N_IDX_170 if label == "N" else X_IDX_170), BASS_X_IDX
    root, quality, bass = parse_label(label)
    chord_idx = CHORD_TO_IDX_170[compose_label(root, quality)]
    bass_idx = BASS_TO_IDX[bass if bass is not None else root]
    return chord_idx, bass_idx


# Strong-minor / strong-major quality families for the MIREX-25 ablation.
_MAJORISH_QUALITIES = {"maj", "maj6", "maj7", "7", "sus2", "sus4"}
_MINORISH_QUALITIES = {"min", "min6", "min7", "minmaj7", "dim", "dim7", "hdim7", "aug"}


def map_170_to_mirex25(chord_idx: int) -> int:
    """Map a 170-class index to the MIREX-25 index (maj/min/N).

    Follows the legacy 277→25 policy: major-ish → major, minor-ish → minor,
    N/X → N. Used only by the vocabulary-size ablation.
    """
    from app.chord_vocab import MIREX_TO_IDX, ROOT_NOTES

    if chord_idx in (N_IDX_170, X_IDX_170):
        return MIREX_TO_IDX["N"]
    quality_index, root_index = divmod(int(chord_idx), 12)
    quality = QUALITIES_14[quality_index]
    target = "maj" if quality in _MAJORISH_QUALITIES else "min"
    return MIREX_TO_IDX[f"{ROOT_NOTES[root_index]}:{target}"]
