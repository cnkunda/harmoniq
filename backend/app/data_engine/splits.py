"""W1 data-engine helpers: deterministic splits and provenance.

The split is a pure function of the track id and a fixed salt, so the same
manifest is produced on a laptop, in CI, and on a GPU host. Datasets with a
human-authored policy (GuitarSet) keep using ``split_policy.json``.
"""

from __future__ import annotations

import hashlib
from typing import Literal

SplitName = Literal["train", "val", "test"]

DEFAULT_SPLIT_SALT = "harmoniq-w1-v1"
DEFAULT_TRAIN_RATIO = 0.80
DEFAULT_VAL_RATIO = 0.10


def deterministic_split(
    track_id: str,
    *,
    salt: str = DEFAULT_SPLIT_SALT,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    val_ratio: float = DEFAULT_VAL_RATIO,
) -> SplitName:
    """Assign a reproducible 80/10/10 split from a stable hash.

    Args:
        track_id: Stable, source-qualified id (e.g. ``"idmt:dataset1/..."``).
        salt: Fixed salt; bump it only when intentionally re-splitting.
        train_ratio: Fraction assigned to ``train``.
        val_ratio: Fraction assigned to ``val``.

    Returns:
        ``"train"``, ``"val"``, or ``"test"``.
    """
    if not 0.0 <= train_ratio <= 1.0:
        raise ValueError("train_ratio must be in [0, 1]")
    if not 0.0 <= val_ratio <= 1.0:
        raise ValueError("val_ratio must be in [0, 1]")
    if train_ratio + val_ratio > 1.0:
        raise ValueError("train_ratio + val_ratio must be <= 1")

    digest = hashlib.sha256(f"{salt}:{track_id}".encode("utf-8")).hexdigest()
    bucket = int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)
    if bucket < train_ratio:
        return "train"
    if bucket < train_ratio + val_ratio:
        return "val"
    return "test"
