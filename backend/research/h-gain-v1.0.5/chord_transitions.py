"""Transition probability matrix for chord progression Viterbi decoding (Commit 99).

Builds a 277x277 transition matrix from music-theory rules, caches it to disk,
and provides key-constrained cost injection for diatonic preference.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from app.chord_inference import CHORD_VOCAB, _ROOTS, _CHORD_QUALITIES

logger = logging.getLogger("harmoniq.inference.transitions")

_NUM_CLASSES = len(CHORD_VOCAB)  # 277
_CACHE_DIR = Path(__file__).parent.parent / "data"
_CACHE_FILE = _CACHE_DIR / "transition_matrix.npy"

# Module-level singleton, populated on first load
_TRANSITION_MATRIX: np.ndarray | None = None
_CHORD_TO_IDX: dict[str, int] = {chord: i for i, chord in enumerate(CHORD_VOCAB)}

# ---------------------------------------------------------------------------
# Music-theory weights
# ---------------------------------------------------------------------------

# Root interval weights (semitone distance → prior weight)
_ROOT_INTERVAL_WEIGHTS = {
    0: 1.8,   # unison / sustain
    1: 0.3,   # minor 2nd (chromatic)
    2: 1.5,   # major 2nd (stepwise)
    3: 1.2,   # minor 3rd (mediant)
    4: 1.2,   # major 3rd (mediant)
    5: 2.0,   # perfect 4th (strong harmonic)
    6: 0.3,   # tritone (dissonant)
    7: 2.0,   # perfect 5th (strong harmonic)
    8: 1.2,   # minor 6th
    9: 1.5,   # major 6th / minor 7th inverted
    10: 1.2,  # minor 7th
    11: 0.3,  # major 7th (chromatic)
}

# Dominant chord qualities (tend to resolve)
_DOMINANT_QUALITIES = {"7", "7#9", "7b9", "7#5", "7b5", "alt7", "7sus4"}

# Diatonic degree patterns for major and minor keys
# Each entry: (degree_offset, quality) where degree_offset is semitones from key root
_MAJOR_DIATONIC = [
    (0, "maj"),   # I
    (2, "min"),   # ii
    (4, "min"),   # iii
    (5, "maj"),   # IV
    (7, "maj"),   # V
    (7, "7"),     # V7
    (9, "min"),   # vi
    (11, "dim"),  # vii°
]

_MINOR_DIATONIC = [
    (0, "min"),   # i
    (2, "dim"),   # ii°
    (3, "maj"),   # III
    (5, "min"),   # iv
    (7, "min"),   # v
    (7, "7"),     # v7
    (8, "maj"),   # VI
    (10, "maj"),  # VII
]


def _parse_chord(chord: str) -> tuple[int, str]:
    """Parse 'C:maj' → (root_idx=0, quality='maj'). 'N' → (-1, 'N')."""
    if chord == "N":
        return -1, "N"
    root_str, qual = chord.split(":")
    return _ROOTS.index(root_str), qual


def _root_distance(i: int, j: int) -> int:
    """Circular semitone distance from chord i to chord j."""
    root_i, _ = _parse_chord(CHORD_VOCAB[i])
    root_j, _ = _parse_chord(CHORD_VOCAB[j])
    if root_i < 0 or root_j < 0:
        return 0
    return (root_j - root_i) % 12


def _quality_weight(qual_i: str, qual_j: str) -> float:
    """Quality compatibility weight."""
    if qual_i == "N" or qual_j == "N":
        return 1.0

    # Same quality persistence
    if qual_i == qual_j:
        return 1.5

    # Dominant → tonic resolution
    if qual_i in _DOMINANT_QUALITIES and qual_j in ("maj", "min"):
        return 2.0

    # ii → V progression support
    if qual_i in ("min", "min7", "min9") and qual_i != qual_j and qual_j in _DOMINANT_QUALITIES:
        return 1.5

    # V → I support (dominant to major/minor)
    if qual_i in _DOMINANT_QUALITIES and qual_j in ("maj", "min", "maj7", "min7"):
        return 1.8

    # Diminished resolution (dim/dim7 → chord a semitone above root)
    if qual_i in ("dim", "dim7"):
        return 1.3

    # Augmented tends to resolve up by semitone
    if qual_i == "aug":
        return 1.2

    return 1.0


def _no_chord_weight(i: int, j: int) -> float:
    """Special handling for N (no-chord) transitions.

    Design: N→N should be comparable to chord→chord persistence (~1.4),
    and N→chord should be slightly lower but still reachable. If N→N is
    too high relative to other transitions, Viterbi treats N as an
    absorbing state and the N ratio *increases* after decoding.
    """
    _, qi = _parse_chord(CHORD_VOCAB[i])
    _, qj = _parse_chord(CHORD_VOCAB[j])

    if qi == "N" and qj == "N":
        return 1.5  # similar to chord→chord persistence, not absorbing
    if qi == "N" and qj != "N":
        return 0.8  # entering from silence — reachable
    if qi != "N" and qj == "N":
        return 0.1  # dropping to silence (rare mid-song)
    return 1.0


def build_transition_matrix(source: str = "synthetic") -> np.ndarray:
    """Build a 277x277 row-stochastic transition probability matrix.

    Args:
        source: "synthetic" (music-theory rules) or "real" (dataset-based).
            "real" is a stub until Commit 101 dataset integration.

    Returns:
        np.ndarray of shape [277, 277], row-normalized.
    """
    if source == "real":
        logger.warning(
            "Real dataset transition matrix not yet available (Commit 101). "
            "Falling back to synthetic matrix."
        )

    n = _NUM_CLASSES
    scores = np.zeros((n, n), dtype=np.float64)

    for i in range(n):
        _, qi = _parse_chord(CHORD_VOCAB[i])
        for j in range(n):
            _, qj = _parse_chord(CHORD_VOCAB[j])

            nc_weight = _no_chord_weight(i, j)
            if nc_weight != 1.0:
                scores[i, j] = nc_weight
                continue

            rd = _root_distance(i, j)
            root_w = _ROOT_INTERVAL_WEIGHTS[rd]
            qual_w = _quality_weight(qi, qj)
            scores[i, j] = root_w * qual_w

    # Row-normalize to probabilities
    row_sums = scores.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums == 0, 1.0, row_sums)
    matrix = scores / row_sums

    logger.info(
        "Built synthetic transition matrix %dx%d (source=%s)", n, n, source
    )
    return matrix.astype(np.float32)


def _ensure_cache_dir() -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


def save_transition_matrix(matrix: np.ndarray, path: Path | None = None) -> Path:
    """Save transition matrix to .npy cache file."""
    target = path or _CACHE_FILE
    _ensure_cache_dir()
    np.save(str(target), matrix)
    logger.info("Saved transition matrix to %s", target)
    return target


def load_transition_matrix(path: Path | None = None) -> np.ndarray:
    """Load transition matrix from cache, building and caching if missing."""
    global _TRANSITION_MATRIX

    target = path or _CACHE_FILE
    if target.exists():
        matrix = np.load(str(target), mmap_mode="r")
        logger.info("Loaded cached transition matrix from %s", target)
        _TRANSITION_MATRIX = matrix
        return matrix

    logger.info("Cache miss — building transition matrix")
    matrix = build_transition_matrix()
    save_transition_matrix(matrix, target)
    _TRANSITION_MATRIX = matrix
    return matrix


def get_transition_matrix() -> np.ndarray:
    """Return the cached transition matrix (loads if needed)."""
    global _TRANSITION_MATRIX
    if _TRANSITION_MATRIX is None:
        return load_transition_matrix()
    return _TRANSITION_MATRIX


def get_chord_to_idx() -> dict[str, int]:
    """Return chord-label → index mapping."""
    return _CHORD_TO_IDX


def get_diatonic_indices(key_root: int, key_mode: str) -> set[int]:
    """Return set of vocab indices that are diatonic in the given key.

    Args:
        key_root: 0-11 (C=0, C#=1, ..., B=11)
        key_mode: "major" or "minor"

    Returns:
        Set of chord vocab indices.
    """
    degrees = _MAJOR_DIATONIC if key_mode == "major" else _MINOR_DIATONIC
    indices: set[int] = set()

    for offset, quality in degrees:
        root_idx = (key_root + offset) % 12
        chord_label = f"{_ROOTS[root_idx]}:{quality}"
        if chord_label in _CHORD_TO_IDX:
            indices.add(_CHORD_TO_IDX[chord_label])

    return indices


def apply_key_constraint(
    matrix: np.ndarray, key_root: int, key_mode: str
) -> np.ndarray:
    """Apply diatonic penalty to a copy of the transition matrix.

    Penalties:
      - Both diatonic:        ×1.0 (no change)
      - One diatonic:         ×0.4
      - Neither diatonic:     ×0.15
      - Tritone + non-diatonic: ×0.05

    Args:
        matrix: Base transition matrix [277, 277]
        key_root: 0-11
        key_mode: "major" or "minor"

    Returns:
        New row-normalized matrix with key constraints applied.
    """
    diatonic = get_diatonic_indices(key_root, key_mode)
    n = matrix.shape[0]

    # Build penalty matrix
    is_diatonic = np.zeros(n, dtype=bool)
    for idx in diatonic:
        is_diatonic[idx] = True

    # Broadcasting: diatonic[i] × diatonic[j] → penalty[i,j]
    d_row = is_diatonic[:, None]  # [n, 1]
    d_col = is_diatonic[None, :]  # [1, n]

    both = d_row & d_col       # both diatonic
    one = d_row ^ d_col        # exactly one diatonic
    neither = ~d_row & ~d_col  # neither diatonic

    penalty = np.ones((n, n), dtype=np.float32)
    penalty[one] = 0.4
    penalty[neither] = 0.15

    # Extra tritone penalty for non-diatonic pairs
    for i in range(n):
        if not is_diatonic[i]:
            root_i, _ = _parse_chord(CHORD_VOCAB[i])
            if root_i < 0:
                continue
            for j in range(n):
                if not is_diatonic[j]:
                    root_j, _ = _parse_chord(CHORD_VOCAB[j])
                    if root_j < 0:
                        continue
                    dist = (root_j - root_i) % 12
                    if dist == 6:  # tritone
                        penalty[i, j] = 0.05

    constrained = matrix * penalty

    # Re-row-normalize
    row_sums = constrained.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums == 0, 1.0, row_sums)
    constrained = constrained / row_sums

    logger.info(
        "Applied key constraint: root=%s, mode=%s, %d diatonic chords",
        _ROOTS[key_root], key_mode, len(diatonic),
    )
    return constrained.astype(np.float32)
