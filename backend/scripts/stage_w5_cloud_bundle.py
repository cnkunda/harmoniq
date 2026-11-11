"""Stage a self-contained W5 calibration bundle for a cloud GPU.

Copies only the files the committed ``docs/eval/amt_manifest.json`` resolves
(audio + ground truth), the MT3 checkpoint, and the backend code the W5
harness needs. The bundle mirrors the repo layout so the manifest resolves
without editing.

Usage (from ``backend/``)::

    python scripts/stage_w5_cloud_bundle.py --out /tmp/w5_bundle
    tar -C /tmp/w5_bundle -czf w5_bundle.tgz .
    modal volume create harmoniq-w5
    modal volume put harmoniq-w5 w5_bundle.tgz /w5

RWC-P audio is CC BY-NC 4.0. Keep the Modal volume private and never commit
audio to git.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.evaluation.manifest import (  # noqa: E402
    ManifestError,
    load_manifest,
    resolve_track_paths,
)

_DEFAULT_MANIFEST = _REPO_ROOT / "docs" / "eval" / "amt_manifest.json"
_CODE_DIRS = ("app", "scripts", "tests")
_MANIFEST_FILES = (
    "docs/eval/amt_manifest.json",
    "docs/eval/README.md",
    "docs/eval/dataset_card.md",
    "docs/eval/licences.md",
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    parser.add_argument(
        "--no-code",
        action="store_true",
        help="Skip copying backend code (data + checkpoint only).",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Skip copying data/models/mt3 (the cloud box must download it).",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Only stage tracks from this manifest source (smoke runs).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only stage the first N selected tracks (smoke runs).",
    )
    return parser.parse_args(argv)


def _copy_file(src: Path, dest: Path) -> int:
    if not src.is_file():
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return src.stat().st_size


def _copy_tree(src: Path, dest: Path) -> int:
    total = 0
    if not src.exists():
        return total
    for path in src.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix in (".pyc", ".pyo"):
            continue
        total += _copy_file(path, dest / path.relative_to(src))
    return total


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    out = args.out.resolve()
    backend_out = out / "backend"
    out.mkdir(parents=True, exist_ok=True)
    backend_out.mkdir(parents=True, exist_ok=True)

    total = 0
    if not args.no_code:
        for name in _CODE_DIRS:
            total += _copy_tree(_BACKEND_DIR / name, backend_out / name)
        total += _copy_file(
            _BACKEND_DIR / "pyproject.toml", backend_out / "pyproject.toml"
        )

    try:
        manifest = load_manifest(args.manifest)
    except (ManifestError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    tracks = list(manifest.tracks)
    if args.source:
        tracks = [track for track in tracks if track.source == args.source]
    if args.limit is not None:
        if args.limit < 1:
            print("[FAIL] --limit must be at least 1", file=sys.stderr)
            return 2
        tracks = tracks[: args.limit]
    if not tracks:
        print("[FAIL] no tracks selected", file=sys.stderr)
        return 2

    files = 0
    data_bytes = 0
    for track in tracks:
        try:
            audio, gt_path, chord_gt_path = resolve_track_paths(
                manifest, track, manifest_path=args.manifest
            )
        except ManifestError as exc:
            print(f"[FAIL] {track.id}: {exc}", file=sys.stderr)
            return 2
        for path in (audio, gt_path, chord_gt_path):
            if path is None or not Path(path).is_file():
                continue
            rel = Path(path).resolve().relative_to(_BACKEND_DIR)
            data_bytes += _copy_file(Path(path), backend_out / rel)
            files += 1

    for rel in _MANIFEST_FILES:
        total += _copy_file(_REPO_ROOT / rel, out / rel)

    checkpoint_bytes = 0
    if not args.no_checkpoint:
        checkpoint_bytes = _copy_tree(
            _BACKEND_DIR / "data" / "models" / "mt3",
            backend_out / "data" / "models" / "mt3",
        )

    print(
        f"[DONE] {out}: {files} manifest files, "
        f"{data_bytes / 1e9:.2f} GB audio/GT, "
        f"checkpoint {checkpoint_bytes / 1e6:.1f} MB, "
        f"code/other {total / 1e6:.1f} MB"
    )
    print(
        "[NOTE] RWC-P audio is CC BY-NC 4.0; keep the Modal volume private "
        "and do not redistribute it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
