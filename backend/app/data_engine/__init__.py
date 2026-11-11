"""W1 data engine.

Modules:

- ``splits``      — deterministic, reproducible train/val/test assignment
- ``manifest``    — validated real-audio manifest with licence/provenance
- ``confidence``  — pseudo-label confidence filtering
- ``augmentation``— cross-stem-style audio mixing
"""

from app.data_engine.manifest import (
    W1Manifest,
    W1Track,
    load_w1_manifest,
    resolve_w1_audio,
    resolve_w1_chord_label,
    resolve_w1_note_label,
)
from app.data_engine.splits import deterministic_split

__all__ = [
    "W1Manifest",
    "W1Track",
    "load_w1_manifest",
    "resolve_w1_audio",
    "resolve_w1_chord_label",
    "resolve_w1_note_label",
    "deterministic_split",
]
