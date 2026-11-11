"""Stage a self-contained W2 teacher-comparison bundle for a cloud GPU.

Copies the fixed 50-track sample audio + ground truth, the committed sample
manifest, the existing teacher-output caches (MT3 baseline included, so the
cloud box does not need JAX/T5X), and the backend code needed to run the
harness. The bundle mirrors the repo layout so ``w2_teacher_sample.json``
resolves without editing.

Usage (from ``backend/``)::

    python scripts/stage_w2_cloud_bundle.py --out /tmp/w2_bundle
    # optional: ship the PyTorch checkpoints too (~700 MB)
    python scripts/stage_w2_cloud_bundle.py --out /tmp/w2_bundle --include-checkpoints
    tar -C /tmp/w2_bundle -czf w2_bundle.tgz .

On the cloud box::

    cd w2_bundle/backend
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements-w2-cloud.txt
    export HARMONIQ_MT3_INFER_PATH=$(python -c 'import mt3_infer,os;print(os.path.dirname(os.path.dirname(mt3_infer.__file__)))')
    export HARMONIQ_MT3_CHECKPOINT_DIR=$PWD/data/models/mt3infer
    python scripts/compare_teachers.py --teachers mt3,mr_mt3,yourmt3,musicfm --device cuda
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

_DEFAULT_SAMPLE = _REPO_ROOT / "docs" / "eval" / "w2_teacher_sample.json"
_CODE_DIRS = ("app", "scripts", "tests")
_CACHE_TEACHERS = ("mt3", "mr_mt3", "yourmt3")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sample", type=Path, default=_DEFAULT_SAMPLE)
    parser.add_argument(
        "--include-checkpoints",
        action="store_true",
        help="Copy data/models/mt3infer (MR-MT3 + YourMT3 weights, ~700 MB)",
    )
    parser.add_argument(
        "--no-code",
        action="store_true",
        help="Skip copying backend code (data + caches only)",
    )
    return parser.parse_args(argv)


def _copy_file(src: Path, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return src.stat().st_size


def _copy_tree(src: Path, dest: Path, *, ignore_cache: bool = True) -> int:
    total = 0
    if not src.exists():
        return total
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        if ignore_cache and "__pycache__" in path.parts:
            continue
        if path.suffix in (".pyc", ".pyo"):
            continue
        rel = path.relative_to(src)
        total += _copy_file(path, dest / rel)
    return total


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    try:
        manifest = load_manifest(args.sample)
    except (ManifestError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    data_bytes = 0
    files = 0
    for track in manifest.tracks:
        try:
            audio, gt_path, chord_gt_path = resolve_track_paths(
                manifest, track, manifest_path=args.sample
            )
        except ManifestError as exc:
            print(f"[FAIL] {track.id}: {exc}", file=sys.stderr)
            return 2
        for path in (audio, gt_path, chord_gt_path):
            if path is None or not Path(path).is_file():
                continue
            rel = Path(path).resolve().relative_to(_BACKEND_DIR)
            data_bytes += _copy_file(Path(path), out / "backend" / rel)
            files += 1

    sample_dest = out / "docs" / "eval" / args.sample.name
    sample_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.sample, sample_dest)

    cache_bytes = 0
    for teacher in _CACHE_TEACHERS:
        cache_bytes += _copy_tree(
            _BACKEND_DIR / "data" / "evaluation" / "teacher_outputs" / teacher,
            out / "backend" / "data" / "evaluation" / "teacher_outputs" / teacher,
        )

    checkpoint_bytes = 0
    if args.include_checkpoints:
        checkpoint_bytes = _copy_tree(
            _BACKEND_DIR / "data" / "models" / "mt3infer",
            out / "backend" / "data" / "models" / "mt3infer",
        )

    code_bytes = 0
    if not args.no_code:
        for name in _CODE_DIRS:
            code_bytes += _copy_tree(
                _BACKEND_DIR / name, out / "backend" / name
            )
        for name in ("pyproject.toml", "requirements-w2-cloud.txt"):
            src = _BACKEND_DIR / name
            if src.is_file():
                code_bytes += _copy_file(src, out / "backend" / name)

    def mb(value: int) -> str:
        return f"{value / 1e6:.1f} MB"

    print(f"[OK] bundle staged at {out}")
    print(f"     sample data: {files} file(s), {mb(data_bytes)}")
    print(f"     teacher caches: {mb(cache_bytes)}")
    print(f"     checkpoints: {mb(checkpoint_bytes)}")
    print(f"     code: {mb(code_bytes)}")
    print("     tar -C {} -czf w2_bundle.tgz .".format(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
