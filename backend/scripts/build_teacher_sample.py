"""Build the fixed 50-track W2 teacher-comparison sample.

Selection is deterministic and stratified by source:

    10 GuitarSet, 10 IDMT, 10 Guitar-TECHS, 5 EGSet12, 15 RWC-P

Within each source, test tracks are preferred, then validation, then train.
The sample is committed so every teacher sees exactly the same 50 tracks.

Usage (from ``backend/``)::

    python scripts/build_teacher_sample.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.evaluation.manifest import EvalManifest, TrackSpec, load_manifest  # noqa: E402

_DEFAULT_INPUT = _REPO_ROOT / "docs" / "eval" / "amt_manifest.json"
_DEFAULT_OUT = _REPO_ROOT / "docs" / "eval" / "w2_teacher_sample.json"

_SOURCE_QUOTAS = {
    "guitarset": 10,
    "idmt_smt_guitar": 10,
    "guitar_techs": 10,
    "egset12": 5,
    "rwc_p": 15,
}
_SPLIT_PRIORITY = {"test": 0, "val": 1, "train": 2}


def select_sample(
    tracks: list[TrackSpec],
    *,
    quotas: dict[str, int] | None = None,
    total: int = 50,
) -> list[TrackSpec]:
    """Select a deterministic source-stratified sample."""
    quotas = quotas or _SOURCE_QUOTAS
    selected: list[TrackSpec] = []
    selected_ids: set[str] = set()

    for source, count in quotas.items():
        candidates = [track for track in tracks if track.source == source]
        candidates.sort(
            key=lambda track: (
                _SPLIT_PRIORITY.get(track.split, 9),
                track.id,
            )
        )
        for track in candidates[:count]:
            selected.append(track)
            selected_ids.add(track.id)

    if len(selected) < total:
        remaining = [track for track in tracks if track.id not in selected_ids]
        remaining.sort(
            key=lambda track: (
                _SPLIT_PRIORITY.get(track.split, 9),
                track.source,
                track.id,
            )
        )
        selected.extend(remaining[: total - len(selected)])

    selected.sort(key=lambda track: track.id)
    return selected[:total]


def build_sample(input_path: Path, *, total: int = 50) -> EvalManifest:
    base = load_manifest(input_path)
    selected = select_sample(base.tracks, total=total)
    if len(selected) < total:
        raise SystemExit(
            f"only {len(selected)} tracks available; need {total}"
        )
    return EvalManifest(
        schema_version=1,
        manifest_id="w2-teacher-sample-v1",
        description=(
            "Fixed 50-track W2 teacher comparison sample. Test preferred over "
            "validation over train within each source. Same tracks for every "
            "teacher."
        ),
        data_root=base.data_root,
        tracks=selected,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=_DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    parser.add_argument("--total", type=int, default=50)
    args = parser.parse_args(argv)

    manifest = build_sample(args.input, total=args.total)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(manifest.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    counts = Counter(track.source for track in manifest.tracks)
    splits = Counter(track.split for track in manifest.tracks)
    print(
        f"[DONE] wrote {len(manifest.tracks)} tracks to {args.out} "
        f"(sources={dict(sorted(counts.items()))}, "
        f"splits={dict(sorted(splits.items()))})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
