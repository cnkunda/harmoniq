"""String-activity targets for a future audio auxiliary head.

The W4 deliverable is the symbolic assignment itself; the audio→string
auxiliary head requires a student retrain and is deferred. This module
builds the 6-string activity matrix that such a head would predict, so the
target format is defined and tested now.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from app.fretting.tuning import NUM_STRINGS
from app.fretting.types import TabNote


def build_string_activity_targets(
    notes: Sequence[TabNote],
    *,
    duration_s: float | None = None,
    hop_s: float = 0.1,
) -> np.ndarray:
    """Build a ``(frames, 6)`` binary string-activity matrix.

    Column 0 is string 1 (high E); column 5 is string 6 (low E). A note is
    active from its onset up to (excluding) its offset. Notes without a
    string assignment are ignored.

    Args:
        notes: Notes carrying ``string`` positions.
        duration_s: Total duration. Defaults to the last note offset.
        hop_s: Frame hop in seconds.

    Raises:
        ValueError: invalid ``hop_s`` or a string outside 1-6.
    """
    if hop_s <= 0:
        raise ValueError(f"hop_s must be > 0, got {hop_s}")
    if duration_s is None:
        duration_s = max(
            (float(note.offset) for note in notes), default=0.0
        )
    frames = max(0, int(np.ceil(float(duration_s) / hop_s)))
    matrix = np.zeros((frames, NUM_STRINGS), dtype=np.float32)
    if frames == 0:
        return matrix

    for note in notes:
        if note.string is None:
            continue
        if not 1 <= note.string <= NUM_STRINGS:
            raise ValueError(
                f"note string must be 1-{NUM_STRINGS}, got {note.string}"
            )
        start = int(np.floor(float(note.onset) / hop_s))
        end = int(np.ceil(float(note.offset) / hop_s))
        start = max(0, min(frames, start))
        end = max(start + 1, min(frames, end))
        matrix[start:end, note.string - 1] = 1.0
    return matrix


def string_activity_summary(matrix: np.ndarray) -> dict[str, float]:
    """Return the active-frame fraction per string, keyed ``string_1`` …."""
    if matrix.ndim != 2 or matrix.shape[1] != NUM_STRINGS:
        raise ValueError(
            f"expected a (frames, {NUM_STRINGS}) matrix, got {matrix.shape}"
        )
    if matrix.shape[0] == 0:
        return {f"string_{index}": 0.0 for index in range(1, NUM_STRINGS + 1)}
    fractions = matrix.mean(axis=0)
    return {
        f"string_{index + 1}": round(float(fractions[index]), 6)
        for index in range(NUM_STRINGS)
    }
