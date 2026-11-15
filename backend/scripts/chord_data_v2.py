"""Chord 170 v2 data loader.

Minimal Phase 1 loader: reads the existing dataset .npz layout
(features, 277-class labels, split metadata) and emits 170-class labels
plus a parallel bass-label array. Datasets without bass information
(e.g. GuitarSet CQT extracts, which have no lowest-note metadata yet)
emit the unknown-bass class for every window until the Phase 2 pipeline
derives bass labels from note data.

Splitting is by recording/track only — windows are never split across
train/val/test (the source .npz files are per-track and carry a
player-level ``split`` key by construction).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_vocab_170 import (  # noqa: E402
    BASS_X_IDX,
    MAP_277_TO_170_TABLE,
    N_IDX_170,
    NUM_CLASSES_170,
)

_N_277_IDX = 276  # N index in the legacy 277-class vocabulary


def list_track_files(data_dir: Path, split: str | None = None) -> list[Path]:
    """Return sorted .npz files under ``<data_dir>/processed/cqt``.

    Args:
        data_dir: Dataset root (e.g. ``data/guitarset``).
        split: Optional split filter; ``None`` loads every split.
    """
    cqt_dir = Path(data_dir) / "processed" / "cqt"
    files: list[Path] = []
    for npz_path in sorted(cqt_dir.glob("*.npz")):
        if split is not None:
            try:
                track_split = str(np.load(npz_path)["split"])
            except Exception as exc:
                print(f"  [WARN] skipping {npz_path.name}: {exc}")
                continue
            if track_split != split:
                continue
        files.append(npz_path)
    return files


def load_track(npz_path: Path) -> dict | None:
    """Load one .npz window file into 170-class arrays.

    Returns None when the file is unreadable (warned, never fatal).
    """
    try:
        data = np.load(npz_path)
        labels277 = data["labels"].astype(np.int64)
        mapped = np.asarray(MAP_277_TO_170_TABLE, dtype=np.int64)
        labels170 = mapped[labels277]
        if "bass_labels" in data.files:
            bass = data["bass_labels"].astype(np.int64)
            if bass.shape != labels277.shape:
                print(f"  [WARN] {npz_path.name}: bass_labels shape mismatch — using unknown bass")
                bass = np.full(labels277.shape, BASS_X_IDX, dtype=np.int64)
        else:
            bass = np.full(labels277.shape, BASS_X_IDX, dtype=np.int64)
        return {
            "features": data["features"].astype(np.float32),
            "labels170": labels170,
            "bass_labels": bass,
            "track_id": str(data["track_id"]),
            "split": str(data["split"]),
            "loss_weight": float(data["loss_weight"]) if "loss_weight" in data.files else 1.0,
        }
    except Exception as exc:
        print(f"  [WARN] skipping {npz_path.name}: {exc}")
        return None


def load_dataset_dir_170(data_dir: Path, split: str | None = None) -> dict:
    """Load all tracks of a dataset directory as 170-class arrays.

    Args:
        data_dir: Dataset root containing ``processed/cqt/*.npz``.
        split: Optional split filter (train/val/test).

    Returns:
        Dict with concatenated features, labels170, bass_labels, track_ids,
        and per-track loss weights.
    """
    features: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    bass: list[np.ndarray] = []
    track_ids: list[str] = []
    weights: list[float] = []
    for npz_path in list_track_files(data_dir, split):
        track = load_track(npz_path)
        if track is None:
            continue
        features.append(track["features"])
        labels.append(track["labels170"])
        bass.append(track["bass_labels"])
        track_ids.extend([track["track_id"]] * track["features"].shape[0])
        weights.append(track["loss_weight"])
    if not features:
        return {
            "features": np.zeros((0, 128, 144), dtype=np.float32),
            "labels170": np.zeros((0,), dtype=np.int64),
            "bass_labels": np.zeros((0,), dtype=np.int64),
            "track_ids": [],
            "loss_weights": [],
        }
    return {
        "features": np.concatenate(features, axis=0),
        "labels170": np.concatenate(labels, axis=0),
        "bass_labels": np.concatenate(bass, axis=0),
        "track_ids": track_ids,
        "loss_weights": weights,
    }


def summarize_dataset(data_dir: Path, split: str | None = None) -> dict:
    """Dataset-card summary: window counts, N rate, unique classes.

    The Phase 2 pipeline extends this with per-source counts and the
    pseudo-label quality report (N rate must be ≤ 20% before training).
    """
    data = load_dataset_dir_170(data_dir, split)
    labels = data["labels170"]
    n = len(labels)
    summary: dict = {
        "data_dir": str(data_dir),
        "split": split,
        "n_tracks": len(set(data["track_ids"])),
        "n_windows": int(n),
    }
    if n == 0:
        summary.update({"n_rate": 0.0, "x_rate": 0.0, "unique_classes": 0})
        return summary
    summary.update({
        "n_rate": float(np.mean(labels == N_IDX_170)),
        "x_rate": float(np.mean(labels == NUM_CLASSES_170 - 1)),
        "unique_classes": int(len(np.unique(labels))),
        "bass_unknown_rate": float(np.mean(data["bass_labels"] == BASS_X_IDX)),
    })
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--split", default=None)
    args = parser.parse_args()
    import json

    print(json.dumps(summarize_dataset(args.data_dir, args.split), indent=2))
