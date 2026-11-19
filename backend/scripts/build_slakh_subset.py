"""Build a quality-balanced Slakh fine subset from the existing cache.

The full Slakh fine cache is dominated by common maj/min windows and full-mix
timbres. This script selects a smaller, deterministic subset that maximises
coverage of the 170 chord classes and inversion classes, while keeping the
original track-level train/val/test split. It only hardlinks/copies existing
npz files; no audio or CQT is recomputed.

Usage (from backend/)::

    python scripts/build_slakh_subset.py --limit 400 --force
    python scripts/build_slakh_subset.py --limit 400 --report ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_labels import inversion_class  # noqa: E402
from app.chord_vocab_170 import BASS_X_IDX, N_IDX_170  # noqa: E402
from scripts.chord_data_v2 import DATA_ROOT  # noqa: E402

SOURCE_DIR = DATA_ROOT / "chord170" / "slakh_fine" / "processed" / "cqt"
OUT_DIR = DATA_ROOT / "chord170" / "slakh_balanced" / "processed" / "cqt"


def _decode(value) -> str:
    if isinstance(value, np.ndarray):
        value = value.item() if value.shape == () else value.flat[0]
    if isinstance(value, (bytes, np.bytes_)):
        return bytes(value).decode("utf-8", "replace")
    return str(value)


def track_profile(labels: np.ndarray, bass: np.ndarray) -> dict:
    """Coverage profile for one track."""
    labels = np.asarray(labels, dtype=np.int64)
    bass = np.asarray(bass, dtype=np.int64)
    chord_mask = labels < N_IDX_170
    classes = {int(c) for c in np.unique(labels[chord_mask])}
    roots = np.where(chord_mask, labels % 12, -1)
    known = chord_mask & (bass != BASS_X_IDX)
    inversions = {
        inversion_class(int(chord), int(bb))
        for chord, bb in zip(labels[known], bass[known])
    }
    return {
        "classes": classes,
        "inversions": inversions,
        "n_rate": float(np.mean(labels == N_IDX_170)),
        "windows": int(len(labels)),
    }


def _hash_key(track_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{track_id}".encode()).hexdigest()


def greedy_cover(profiles: dict[str, dict], count: int, seed: int) -> list[str]:
    """Greedy set cover over chord classes, tie-broken by deterministic hash."""
    selected: list[str] = []
    covered: set[int] = set()
    remaining = sorted(profiles, key=lambda t: _hash_key(t, seed))
    for _ in range(min(count, len(remaining))):
        best = None
        best_score = -1.0
        for track_id in remaining:
            profile = profiles[track_id]
            new_classes = len(profile["classes"] - covered)
            new_inversions = len(profile["inversions"] - {0, 1})
            score = new_classes + 0.25 * new_inversions
            if score > best_score:
                best_score = score
                best = track_id
        if best is None:
            break
        selected.append(best)
        covered |= profiles[best]["classes"]
        remaining.remove(best)
    return selected


def _hash_sample(track_ids: list[str], count: int, seed: int) -> list[str]:
    return sorted(track_ids, key=lambda t: _hash_key(t, seed))[:count]


def select_subset(source_dir: Path, limit: int, seed: int = 0) -> dict:
    paths = sorted(source_dir.glob("*.npz"))
    if not paths:
        raise SystemExit(f"no npz files under {source_dir}")

    profiles: dict[str, dict] = {}
    splits: dict[str, str] = {}
    by_split: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    for path in paths:
        with np.load(path) as data:
            labels = data["labels170"].astype(np.int64)
            bass = (data["bass_labels"].astype(np.int64)
                    if "bass_labels" in data.files
                    else np.full(labels.shape, BASS_X_IDX, dtype=np.int64))
            split = _decode(data["split"]) if "split" in data.files else "train"
            track_id = _decode(data["track_id"]) if "track_id" in data.files else path.stem
        if split not in by_split:
            split = "train"
        profiles[track_id] = track_profile(labels, bass)
        splits[track_id] = split
        by_split[split].append(track_id)

    n_train = max(1, int(round(limit * 0.8)))
    n_val = max(1, int(round(limit * 0.1)))
    n_test = max(0, limit - n_train - n_val)
    train_ids = greedy_cover(
        {t: profiles[t] for t in by_split["train"]}, n_train, seed)
    val_ids = _hash_sample(by_split["val"], n_val, seed)
    test_ids = _hash_sample(by_split["test"], n_test, seed + 1)
    selected = train_ids + val_ids + test_ids
    covered = set().union(*(profiles[t]["classes"] for t in selected))
    inversions = set().union(*(profiles[t]["inversions"] for t in selected))
    return {
        "selected": selected,
        "train": train_ids,
        "val": val_ids,
        "test": test_ids,
        "profiles": profiles,
        "splits": splits,
        "covered_classes": len(covered),
        "covered_inversions": len(inversions),
    }


def materialise(selection: dict, source_dir: Path, out_dir: Path,
                force: bool = False) -> None:
    if out_dir.exists() and not force:
        existing = len(list(out_dir.glob("*.npz")))
        if existing:
            raise SystemExit(
                f"{out_dir} already has {existing} files; pass --force to rebuild")
    out_dir.mkdir(parents=True, exist_ok=True)
    for track_id in selection["selected"]:
        src = source_dir / f"{track_id}.npz"
        dst = out_dir / f"{track_id}.npz"
        if dst.exists():
            dst.unlink()
        try:
            os.link(src, dst)
        except OSError:
            try:
                os.symlink(src.resolve(), dst)
            except OSError:
                shutil.copyfile(src, dst)


def build_subset(source_dir: Path = SOURCE_DIR, out_dir: Path = OUT_DIR,
                 limit: int = 400, seed: int = 0, force: bool = False,
                 report_path: Path | None = None) -> dict:
    selection = select_subset(source_dir, limit, seed)
    materialise(selection, source_dir, out_dir, force=force)
    profiles = selection["profiles"]
    report = {
        "source_dir": str(source_dir),
        "out_dir": str(out_dir),
        "limit": int(limit),
        "seed": int(seed),
        "tracks": len(selection["selected"]),
        "splits": {name: len(selection[name]) for name in ("train", "val", "test")},
        "windows": int(sum(profiles[t]["windows"] for t in selection["selected"])),
        "covered_classes": int(selection["covered_classes"]),
        "covered_inversions": int(selection["covered_inversions"]),
        "n_rate": float(np.mean([profiles[t]["n_rate"] for t in selection["selected"]])),
        "track_ids": selection["selected"],
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)
    report = build_subset(args.source_dir, args.out_dir, limit=args.limit,
                          seed=args.seed, force=args.force,
                          report_path=args.report)
    print(json.dumps({k: v for k, v in report.items() if k != "track_ids"},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
