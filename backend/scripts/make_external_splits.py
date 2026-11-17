"""Generate quality-stratified external splits for the Chord 170 gates.

GuitarSet / Guitar-TECHS / EGSet12 keep their existing player-level splits.
IDMT-SMT-Guitar and RWC-P get track-level val/test holdouts (~10% each),
chosen so that every quality present in at least two tracks is represented
in the held-out test (and one track remains in train).

Also guards pseudo-label leakage: W1 pseudo tracks that map to a held-out
IDMT track are marked ``exclude`` so they are never trained on.

Output: ``data/chord170/splits.json``

Usage (from backend/, on a machine with the CQT caches)::

    python scripts/make_external_splits.py
    python scripts/make_external_splits.py --val-frac 0.10 --test-frac 0.10 --seed 0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_labels import parse_annotation_label  # noqa: E402
from scripts.chord_data_v2 import (  # noqa: E402
    DATA_ROOT,
    REAL_DATASETS,
    _decode,
    _w1_kept_centers,  # noqa: F401 (imported for symmetry / reuse by callers)
    idmt_chord_labels,
    rwc_chord_labels,
)

SPLITS_PATH = DATA_ROOT / "chord170" / "splits.json"
PSEUDO_DIR = DATA_ROOT / "chord170" / "pseudo_v2"
W1_ROOT = DATA_ROOT / "pseudo_label" / "w1"
STRATIFIED_SOURCES = ("idmt_smt_guitar", "rwc")


def _hash_score(track_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{track_id}".encode()).hexdigest()


def _normalise_quality(label: str) -> str | None:
    parsed = parse_annotation_label(label)
    if parsed is None:
        return None
    return parsed[1]


def _quality_profiles(intervals_by_track: dict[str, list]) -> dict[str, set[str]]:
    profiles: dict[str, set[str]] = {}
    for track_id, intervals in intervals_by_track.items():
        qualities: set[str] = set()
        for _start, _end, label in intervals:
            quality = _normalise_quality(label)
            if quality is not None:
                qualities.add(quality)
        profiles[track_id] = qualities
    return profiles


def _annotation_tracks(source: str) -> dict[str, list]:
    if source == "idmt_smt_guitar":
        return idmt_chord_labels(REAL_DATASETS[source] / "raw" / "audio" / "dataset4")
    if source == "rwc":
        return rwc_chord_labels(REAL_DATASETS[source] / "raw" / "chords" / "RWC-P")
    raise ValueError(source)


def _cqt_track_ids(source: str) -> list[str]:
    cqt_dir = REAL_DATASETS[source] / "processed" / "cqt"
    ids: list[str] = []
    for path in sorted(cqt_dir.glob("*.npz")):
        try:
            import numpy as np

            ids.append(_decode(np.load(path)["track_id"]))
        except Exception:
            continue
    return ids


def _stratified_holdout(
    track_ids: list[str],
    profiles: dict[str, set[str]],
    *,
    val_frac: float,
    test_frac: float,
    seed: int,
) -> tuple[list[str], list[str]]:
    """Pick (test, val) tracks with quality coverage.

    Rarity-first greedy: each quality with ≥2 tracks contributes one test
    representative; remaining slots are filled by deterministic hash order.
    Then the same for val from the remaining tracks.
    """
    n = len(track_ids)
    n_test = max(1, int(round(n * test_frac)))
    n_val = max(1, int(round(n * val_frac)))
    ordered = sorted(track_ids, key=lambda t: _hash_score(t, seed))
    quality_tracks: dict[str, list[str]] = defaultdict(list)
    for track in ordered:
        for quality in profiles.get(track, set()):
            quality_tracks[quality].append(track)
    rarity = sorted(quality_tracks, key=lambda q: (len(quality_tracks[q]), q))

    selected_test: list[str] = []
    for quality in rarity:
        if len(selected_test) >= n_test:
            break
        if len(quality_tracks[quality]) < 2:
            continue
        for candidate in quality_tracks[quality]:
            if candidate not in selected_test:
                selected_test.append(candidate)
                break
    for candidate in ordered:
        if len(selected_test) >= n_test:
            break
        if candidate not in selected_test:
            selected_test.append(candidate)

    remaining = [t for t in ordered if t not in selected_test]
    selected_val: list[str] = []
    for quality in rarity:
        if len(selected_val) >= n_val:
            break
        if len(quality_tracks[quality]) < 3:
            continue
        for candidate in quality_tracks[quality]:
            if candidate in remaining and candidate not in selected_val:
                selected_val.append(candidate)
                break
    for candidate in remaining:
        if len(selected_val) >= n_val:
            break
        if candidate not in selected_val:
            selected_val.append(candidate)
    return selected_test, selected_val


def _existing_splits(source: str) -> dict[str, str]:
    import numpy as np

    splits: dict[str, str] = {}
    for path in sorted((REAL_DATASETS[source] / "processed" / "cqt").glob("*.npz")):
        try:
            data = np.load(path)
            track_id = _decode(data["track_id"])
            split = _decode(data["split"]) if "split" in data.files else "train"
        except Exception:
            continue
        splits[track_id] = split
    return splits


def _pseudo_splits() -> dict[str, str]:
    import numpy as np

    splits: dict[str, str] = {}
    if not PSEUDO_DIR.exists():
        return splits
    for path in sorted((PSEUDO_DIR / "processed" / "cqt").glob("*.npz")):
        try:
            data = np.load(path)
            track_id = _decode(data["track_id"])
            split = _decode(data["split"]) if "split" in data.files else "train"
        except Exception:
            continue
        splits[track_id] = split
    return splits


def _pseudo_real_id(track_id: str) -> str | None:
    """Map a W1/IDMT pseudo track id to the real IDMT CQT track id.

    ``idmt_raw:dataset4/<recording>/<speed>/<style>/audio/<stem>`` →
    ``<style>_<stem>`` (the id used by the IDMT CQT cache / parser).
    """
    if not track_id.startswith("idmt_raw:"):
        return None
    rel = track_id.split("idmt_raw:", 1)[1]
    parts = rel.split("/")
    if "dataset4" not in parts or "audio" not in parts:
        return None
    try:
        style = parts[parts.index("audio") - 1]
        stem = Path(parts[-1]).stem
    except (ValueError, IndexError):
        return None
    return f"{style}_{stem}"


def build_splits(
    *,
    val_frac: float = 0.10,
    test_frac: float = 0.10,
    seed: int = 0,
) -> dict:
    result: dict = {
        "config": {
            "val_frac": val_frac,
            "test_frac": test_frac,
            "seed": seed,
            "stratified_sources": list(STRATIFIED_SOURCES),
            "method": "quality-rarity-first greedy + deterministic hash fill",
        },
        "splits": {},
        "stats": {},
        "excluded": {},
    }

    for source in ("guitarset", "guitar_techs", "egset12"):
        result["splits"][source] = _existing_splits(source)

    excluded_pseudo: list[str] = []
    for source in STRATIFIED_SOURCES:
        track_ids = _cqt_track_ids(source)
        if not track_ids:
            result["stats"][source] = {"status": "no_cqt_cache"}
            continue
        annotations = _annotation_tracks(source)
        profiles = _quality_profiles(annotations)
        test, val = _stratified_holdout(
            track_ids, profiles, val_frac=val_frac, test_frac=test_frac, seed=seed
        )
        mapping: dict[str, str] = {}
        for track in track_ids:
            mapping[track] = "test" if track in test else ("val" if track in val else "train")
        result["splits"][source] = mapping
        held_out = set(test) | set(val)
        # Quality coverage of the held-out test.
        test_quality = Counter()
        for track in test:
            for quality in profiles.get(track, set()):
                test_quality[quality] += 1
        train_quality = Counter()
        for track in track_ids:
            if track not in held_out:
                for quality in profiles.get(track, set()):
                    train_quality[quality] += 1
        result["stats"][source] = {
            "n_tracks": len(track_ids),
            "n_train": len(track_ids) - len(test) - len(val),
            "n_val": len(val),
            "n_test": len(test),
            "test_quality_coverage": dict(sorted(test_quality.items())),
            "train_quality_coverage": dict(sorted(train_quality.items())),
        }

    pseudo = _pseudo_splits()
    held_out_real: set[str] = set()
    for source in STRATIFIED_SOURCES:
        mapping = result["splits"].get(source, {})
        held_out_real.update(t for t, s in mapping.items() if s in ("val", "test"))
    cleaned: dict[str, str] = {}
    for track_id, split in pseudo.items():
        real_id = _pseudo_real_id(track_id)
        if real_id and real_id in held_out_real:
            cleaned[track_id] = "exclude"
            excluded_pseudo.append(track_id)
        else:
            cleaned[track_id] = split
    result["splits"]["pseudo_v2"] = cleaned
    result["excluded"]["pseudo_v2"] = excluded_pseudo
    result["stats"]["pseudo_v2"] = {
        "n_tracks": len(cleaned),
        "excluded_for_leakage": len(excluded_pseudo),
    }

    # Global leakage check: a track id must not appear under two eval splits
    # within a source (the same id in different sources is namespaced).
    overlaps = []
    for source, mapping in result["splits"].items():
        by_split: dict[str, set[str]] = defaultdict(set)
        for track_id, split in mapping.items():
            by_split[split].add(track_id)
        for a in by_split:
            for b in by_split:
                if a < b and by_split[a] & by_split[b]:
                    overlaps.append({"source": source, "splits": [a, b],
                                     "count": len(by_split[a] & by_split[b])})
    result["leakage_overlaps"] = overlaps
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--val-frac", type=float, default=0.10)
    parser.add_argument("--test-frac", type=float, default=0.10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=SPLITS_PATH)
    args = parser.parse_args(argv)

    result = build_splits(val_frac=args.val_frac, test_frac=args.test_frac, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result["stats"], indent=2))
    print(f"excluded pseudo tracks (leakage): {len(result['excluded']['pseudo_v2'])}")
    print(f"leakage overlaps: {len(result['leakage_overlaps'])}")
    print(f"splits written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
