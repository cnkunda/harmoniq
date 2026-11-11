"""Stage a self-contained W3 student-training bundle for a cloud GPU.

The bundle mirrors the repo layout so the committed manifests resolve
without editing::

    cd backend
    python scripts/stage_w3_cloud_bundle.py --out /tmp/w3_bundle
    python scripts/stage_w3_cloud_bundle.py --out /tmp/w3_bundle --include-audio
    tar -C /tmp/w3_bundle -czf w3_bundle.tgz .
    modal volume create harmoniq-w3
    modal volume put harmoniq-w3 /tmp/w3_bundle /w3

``--include-audio`` copies the raw audio used by the W0/W1 manifests. This
is the large step (several GB); omit it on a box that already has data.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent

_CODE_DIRS = ("app", "scripts", "tests")
_MANIFEST_FILES = (
    "docs/eval/w1_dataset_manifest.json",
    "docs/eval/amt_manifest.json",
    "docs/eval/w2_teacher_sample.json",
    "docs/eval/dataset_card.md",
    "docs/eval/licences.md",
)
_DATA_DIRS = (
    "data/pseudo_label/w1/labels",
    "data/pseudo_label/w1/processed/cqt",
)
_AUDIO_DIRS = (
    "data/guitarset/raw/audio_mono-mix",
    "data/guitarset/processed/timelines",
    "data/guitarset/raw/annotation",
    "data/egset12/raw",
    "data/egset12/processed/timelines",
    "data/idmt_smt_guitar/raw/audio",
    "data/idmt_smt_guitar/processed/timelines",
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--include-audio", action="store_true")
    parser.add_argument("--no-code", action="store_true")
    return parser.parse_args(argv)


def _copy_tree(src: Path, dest: Path) -> int:
    total = 0
    if not src.exists():
        print(f"[skip] missing {src}")
        return total
    for path in src.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        target = dest / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        total += path.stat().st_size
    return total


def _copy_file(src: Path, dest: Path) -> int:
    if not src.is_file():
        print(f"[skip] missing {src}")
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return src.stat().st_size


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
        total += _copy_file(
            _BACKEND_DIR / "requirements-w2-cloud.txt",
            backend_out / "requirements-w2-cloud.txt",
        )

    for rel in _MANIFEST_FILES:
        total += _copy_file(_REPO_ROOT / rel, out / rel)

    for rel in _DATA_DIRS:
        total += _copy_tree(_BACKEND_DIR / rel, backend_out / rel)

    if args.include_audio:
        for rel in _AUDIO_DIRS:
            total += _copy_tree(_BACKEND_DIR / rel, backend_out / rel)

    print(
        f"[done] bundle at {out} ({total / 1e6:.1f} MB). "
        f"Audio included: {args.include_audio}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
