"""Playability cost from the Fretting-Transformer.

Implements the difficulty metric from Hamberger et al., "Fretting-Transformer:
Encoder-Decoder Model for MIDI to Tablature Transcription" (arXiv:2506.14223,
ICMC 2025), Section 3.6::

    difficulty(p, q) = fret_stretch(p, q) + locality(p, q)
                       + vertical_stretch(p, q)

    fret_stretch = 0.50 * |Δfret| when moving up,
                   0.75 * |Δfret| otherwise
    locality     = alpha * (p.fret + q.fret), alpha = 0.25
    vertical_stretch = 0.00 when Δstring = 0,
                       0.25 when |Δstring| = 1, else 0.50

The score is 0 for repeated notes on one open string and 18.5 for the
worst open-low-E → 24th-fret-high-E jump on a 24-fret guitar.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.fretting.positions import Position

DEFAULT_ALPHA = 0.25


def fret_stretch(p: Position, q: Position) -> float:
    """Horizontal movement cost between two positions."""
    delta = q.fret - p.fret
    return 0.5 * abs(delta) if delta > 0 else 0.75 * abs(delta)


def locality(
    p: Position,
    q: Position,
    *,
    alpha: float = DEFAULT_ALPHA,
) -> float:
    """Higher-fret positions are harder to press and stop cleanly."""
    if alpha < 0:
        raise ValueError(f"alpha must be >= 0, got {alpha}")
    return alpha * (p.fret + q.fret)


def vertical_stretch(p: Position, q: Position) -> float:
    """String-crossing cost between two positions.

    The same string costs nothing, so repeated notes on one open string
    score 0 (the paper's documented minimum).
    """
    distance = abs(q.string - p.string)
    if distance == 0:
        return 0.0
    return 0.25 if distance == 1 else 0.5


def transition_difficulty(
    p: Position,
    q: Position,
    *,
    alpha: float = DEFAULT_ALPHA,
) -> float:
    """Difficulty of moving from position ``p`` to position ``q``."""
    return round(
        fret_stretch(p, q)
        + locality(p, q, alpha=alpha)
        + vertical_stretch(p, q),
        6,
    )


def sequence_difficulty(
    positions: Sequence[Position],
    *,
    alpha: float = DEFAULT_ALPHA,
) -> float:
    """Mean transition difficulty over a position sequence.

    A single position (or an empty sequence) has difficulty 0.0.
    """
    if len(positions) < 2:
        return 0.0
    total = sum(
        transition_difficulty(before, after, alpha=alpha)
        for before, after in zip(positions, positions[1:])
    )
    return round(total / (len(positions) - 1), 6)
