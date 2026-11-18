"""Fit post-hoc calibration for a Chord 170 checkpoint (Stage C).

Loads the validation split, predicts, and grid-searches a temperature and
class-prior exponent that maximise supported-class macro-F1 (ties broken by
NLL). The resulting JSON is consumed by ``eval_chord_170.py --calibration``
and can be shipped alongside the checkpoint.

Usage (from backend/)::

    python scripts/calibrate_chord_170.py \
        --checkpoint runs/chord170/.../best.keras \
        --sources guitarset,guitar_techs,idmt_smt_guitar,rwc \
        --out runs/chord170/.../calibration.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from scripts import chord_data_v2 as data  # noqa: E402
from scripts.eval_chord_170 import (  # noqa: E402
    apply_calibration,
    expected_calibration_error,
    fit_calibration,
    load_model,
    macro_f1,
    map_native_to_mirex25,
    predict_arrays,
)

SOURCE_DIRS = {
    "guitarset": "guitarset",
    "egset12": "egset12",
    "guitar_techs": "guitar_techs",
    "idmt_smt_guitar": "idmt_smt_guitar",
    "rwc": "rwc",
    "pseudo_v2": "chord170/pseudo_v2",
    "pseudo_btc": "chord170/pseudo_btc",
    "slakh": "chord170/slakh",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=_BACKEND_DIR / "data")
    parser.add_argument("--sources", default="guitarset,guitar_techs,idmt_smt_guitar,rwc")
    parser.add_argument("--split", default="val")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--feature-stats", type=Path, default=None)
    parser.add_argument("--feature-normalize", default="none", choices=["none", "track"])
    parser.add_argument("--crop-window", type=int, default=128)
    args = parser.parse_args(argv)

    features, labels, tracks = [], [], []
    for name in [s.strip() for s in args.sources.split(",") if s.strip()]:
        loaded = data.load_dataset_dir_170(args.data_root / SOURCE_DIRS[name],
                                           args.split, source=name,
                                           normalize=args.feature_normalize,
                                           crop_window=args.crop_window)
        if len(loaded["labels170"]) == 0:
            continue
        features.append(loaded["features"])
        labels.append(loaded["labels170"])
        tracks.extend(loaded["track_ids"])
    if not features:
        print("No validation windows found.", file=sys.stderr)
        return 1
    X = np.concatenate(features)
    if args.feature_stats is not None:
        stats = np.load(args.feature_stats)
        X = ((X - stats["mean"]) / stats["std"]).astype(np.float32)
    y = np.concatenate(labels)

    model = load_model(args.checkpoint)
    probs, _bass = predict_arrays(model, X, args.batch_size)
    params = fit_calibration(probs, y)
    calibrated = apply_calibration(probs, params)
    before = macro_f1(y, probs.argmax(axis=1), labels=np.unique(y))
    after = macro_f1(y, calibrated.argmax(axis=1), labels=np.unique(y))
    payload = {
        **params,
        "split": args.split,
        "sources": sorted({s for s in args.sources.split(",") if s.strip()}),
        "n_windows": int(len(y)),
        "macro_f1_supported_before": float(before),
        "macro_f1_supported_after": float(after),
        "ece_before": expected_calibration_error(probs, y),
        "ece_after": expected_calibration_error(calibrated, y),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2))
    print(json.dumps({k: payload[k] for k in (
        "temperature", "prior_exponent", "macro_f1_supported_before",
        "macro_f1_supported_after", "ece_before", "ece_after")}, indent=2))
    print(f"calibration written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
