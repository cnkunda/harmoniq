"""Phase 4 teacher comparison: MT3-template vs BTC labels on IDMT dataset4.

Both teachers are scored against the IDMT dataset4 chord annotations at the
same window centres (the W1 pseudo-label windows), in the 170-class space:

* MT3-template: the W1 pseudo-label stored per window (277→170).
* BTC: the 170-class timeline interval covering the window centre.

Metrics: exact / root / majmin accuracy with bootstrap 95% confidence
intervals over tracks. Writes a JSON report and prints a comparison table.

Usage (from backend/)::

    python scripts/compare_teachers.py \
        --btc-dir /tmp/btc_timelines \
        --out ../docs/audit/amt/chord170_phase4_teacher_compare.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_labels import parse_annotation_label, pitch_class_from_name  # noqa: E402
from app.chord_vocab_170 import (  # noqa: E402
    CHORD_TO_IDX_170,
    MAP_277_TO_170_TABLE,
    N_IDX_170,
    ROOTS_12,
)
from scripts.btc_teacher import btc_chord_to_170  # noqa: E402
from scripts.chord_data_v2 import _decode, _w1_kept_centers  # noqa: E402
from scripts.eval_chord_170 import bootstrap_ci, macro_f1  # noqa: E402

W1_ROOT = _BACKEND_DIR / "data" / "pseudo_label" / "w1"
IDMT_ROOT = _BACKEND_DIR / "data" / "idmt_smt_guitar" / "raw" / "audio"
_MAP_TABLE = np.asarray(MAP_277_TO_170_TABLE, dtype=np.int64)


def _safe_id(track_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in track_id)


def _annotation_intervals(csv_path: Path) -> list[tuple[float, float, str]]:
    entries: list[tuple[float, str]] = []
    for line in csv_path.read_text().splitlines():
        parts = line.strip().split(",")
        if len(parts) < 2 or ":" not in parts[1]:
            continue
        try:
            start = float(parts[0])
        except ValueError:
            continue
        chord = parts[1].split(":", 1)[1].strip()
        if chord:
            entries.append((start, chord))
    entries.sort(key=lambda item: item[0])
    intervals = []
    for index, (start, chord) in enumerate(entries):
        end = entries[index + 1][0] if index + 1 < len(entries) else start + 2.0
        intervals.append((start, end, chord))
    return intervals


def _annotation_label_at(intervals, time_s: float) -> int:
    for start, end, label in intervals:
        if start <= time_s < end:
            parsed = parse_annotation_label(label)
            if parsed is None:
                return N_IDX_170
            root, quality, _bass = parsed
            pc = pitch_class_from_name(root)
            if pc is None:
                return N_IDX_170
            return CHORD_TO_IDX_170[f"{ROOTS_12[pc]}:{quality}"]
    return N_IDX_170


def _btc_label_at(events, time_s: float) -> int:
    for event in events:
        if float(event["start"]) <= time_s < float(event["end"]):
            label = btc_chord_to_170(str(event["chord"]))
            if label is None or label == "X":
                return N_IDX_170
            if label == "N":
                return N_IDX_170
            return CHORD_TO_IDX_170[label]
    return N_IDX_170


def _root_of(idx: int) -> int:
    return -1 if idx >= N_IDX_170 else int(idx) % 12


def _majmin_of(idx: int) -> int:
    if idx >= N_IDX_170:
        return 24
    from app.chord_vocab_170 import map_170_to_mirex25

    return map_170_to_mirex25(int(idx))


def _accuracy_sets(gt: np.ndarray, pred: np.ndarray) -> dict:
    roots_gt = np.array([_root_of(int(i)) for i in gt])
    roots_pred = np.array([_root_of(int(i)) for i in pred])
    majmin_gt = np.array([_majmin_of(int(i)) for i in gt])
    majmin_pred = np.array([_majmin_of(int(i)) for i in pred])
    return {
        "exact": (gt == pred).astype(np.float64),
        "root": (roots_gt == roots_pred).astype(np.float64),
        "majmin": (majmin_gt == majmin_pred).astype(np.float64),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--btc-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path,
                        default=_BACKEND_DIR / ".." / "docs" / "audit" / "amt"
                        / "chord170_phase4_teacher_compare.json")
    parser.add_argument("--n-boot", type=int, default=1000)
    args = parser.parse_args(argv)

    results: dict[str, dict[str, list]] = {
        "mt3": {"exact": [], "root": [], "majmin": []},
        "btc": {"exact": [], "root": [], "majmin": []},
    }
    per_track: dict[str, dict] = {}
    track_ids: list[str] = []
    n_windows = 0
    skipped = 0

    for btc_path in sorted(Path(args.btc_dir).rglob("*.json")):
        payload = json.loads(btc_path.read_text())
        track_id = str(payload.get("track_id", ""))
        if not track_id.startswith("idmt_raw:dataset4/"):
            skipped += 1
            continue
        safe = _safe_id(track_id)
        labels_path = W1_ROOT / "labels" / f"{safe}.json"
        npz_path = W1_ROOT / "processed" / "cqt" / f"{safe}.npz"
        if not labels_path.exists() or not npz_path.exists():
            skipped += 1
            continue
        w1 = json.loads(labels_path.read_text())
        npz = np.load(npz_path)
        centres = _w1_kept_centers(w1, npz["labels"].shape[0])
        if centres is None:
            skipped += 1
            continue

        rel = track_id.split("idmt_raw:", 1)[1]  # dataset4/<...>/audio/<name>
        csv_path = IDMT_ROOT / rel.replace("/audio/", "/annotation/chords/")
        csv_path = csv_path.with_suffix(".csv")
        if not csv_path.exists():
            skipped += 1
            continue
        intervals = _annotation_intervals(csv_path)
        events = payload.get("events", [])

        gt = np.array([_annotation_label_at(intervals, float(c)) for c in centres])
        mt3 = _MAP_TABLE[npz["labels"].astype(np.int64)]
        btc = np.array([_btc_label_at(events, float(c)) for c in centres])

        for name, pred in (("mt3", mt3), ("btc", btc)):
            sets = _accuracy_sets(gt, pred)
            for metric, values in sets.items():
                results[name][metric].extend(values.tolist())
        per_track[track_id] = {
            "n_windows": int(len(gt)),
            "gt_n_rate": float(np.mean(gt == N_IDX_170)),
            "mt3_exact": float(np.mean(mt3 == gt)),
            "btc_exact": float(np.mean(btc == gt)),
            "mt3_macro_f1": macro_f1(gt, mt3),
            "btc_macro_f1": macro_f1(gt, btc),
        }
        track_ids.extend([track_id] * len(gt))
        n_windows += len(gt)

    report: dict = {
        "n_tracks": len(per_track),
        "n_windows": n_windows,
        "skipped": skipped,
        "teachers": {},
        "per_track": per_track,
    }
    for name in ("mt3", "btc"):
        arrays = {metric: np.asarray(values) for metric, values in results[name].items()}
        report["teachers"][name] = {
            metric: float(values.mean()) if len(values) else 0.0
            for metric, values in arrays.items()
        }
        # Bootstrap over tracks on the exact-accuracy vector.
        exact_by_track = defaultdict(list)
        for track, value in zip(track_ids, arrays["exact"]):
            exact_by_track[track].append(float(value))
        track_means = np.array([np.mean(v) for v in exact_by_track.values()])
        if len(track_means):
            rng = np.random.default_rng(0)
            samples = [track_means[rng.integers(0, len(track_means), len(track_means))].mean()
                       for _ in range(args.n_boot)]
            report["teachers"][name]["exact_ci95"] = [
                float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))
            ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))

    print(f"Teacher comparison on IDMT dataset4 ({report['n_tracks']} tracks, "
          f"{report['n_windows']} windows, {skipped} skipped)")
    print(f"{'teacher':8s} {'exact':>8s} {'95% CI':>18s} {'root':>8s} {'majmin':>8s}")
    for name, values in report["teachers"].items():
        ci = values.get("exact_ci95", [0, 0])
        print(f"{name:8s} {values['exact']:8.3f} [{ci[0]:.3f}, {ci[1]:.3f}] "
              f"{values['root']:8.3f} {values['majmin']:8.3f}")
    print(f"report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
