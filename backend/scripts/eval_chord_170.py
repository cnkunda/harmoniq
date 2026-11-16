"""Phase 3 evaluation for the 170-class chord model.

Window-level evaluation: every window is scored as an interval
``[centre, centre + hop)`` carrying its label, so mir_eval's WCSR metrics
(root / majmin / thirds / triads / sevenths / tetrads / MIREX) are computed
exactly as on a chord timeline. Windows are grouped per track (centres are
track-relative) and aggregated duration-weighted.

Also reports: macro-F1 over the 170 classes, per-quality precision/recall/F1,
bass accuracy, slash-chord accuracy (root-position and inversion separately),
top-k accuracy, duration-weighted ECE, and per-source breakdowns.

Pure metric functions here import only numpy + mir_eval; TensorFlow is
imported lazily by the checkpoint loader / predictor.
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

from app.chord_vocab_170 import (  # noqa: E402
    BASS_VOCAB,
    BASS_X_IDX,
    CHORD_VOCAB_170,
    N_IDX_170,
    NUM_CLASSES_170,
    QUALITIES_14,
    ROOTS_12,
    X_IDX_170,
)

# Semitone interval above the chord root → mir_eval/Harte scale degree.
_SEMITONE_TO_DEGREE = {
    0: "1", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4",
    6: "b5", 7: "5", 8: "b6", 9: "6", 10: "b7", 11: "7",
}

# mir_eval WCSR keys we report.
_WCSR_KEYS = ("root", "majmin", "thirds", "triads", "sevenths", "tetrads", "mirex")


def _decode_label(chord_idx: int) -> tuple[str | None, str | None]:
    """Split a 170-class index into (root, quality); (None, None) for N/X."""
    if chord_idx in (N_IDX_170, X_IDX_170):
        return None, None
    root, quality = CHORD_VOCAB_170[chord_idx].split(":", 1)
    return root, quality


def label_to_harte(
    chord_idx: int,
    bass_idx: int | None = None,
    *,
    include_bass: bool = True,
) -> str:
    """Convert (chord_idx, bass_idx) to a mir_eval/Harte chord label.

    Bass is emitted as a scale degree relative to the root (mir_eval's
    required syntax: ``C:maj/3``, never ``C:maj/E``). Unknown bass and
    root-position bass emit the plain label.
    """
    if chord_idx == N_IDX_170:
        return "N"
    if chord_idx == X_IDX_170:
        return "X"
    root, quality = _decode_label(chord_idx)
    assert root is not None and quality is not None
    label = f"{root}:{quality}"
    if not include_bass or bass_idx is None or bass_idx == BASS_X_IDX:
        return label
    bass_pc = int(bass_idx) % 12
    root_pc = ROOTS_12.index(root)
    semitones = (bass_pc - root_pc) % 12
    if semitones == 0:
        return label
    return f"{label}/{_SEMITONE_TO_DEGREE[semitones]}"


def window_intervals(centres: np.ndarray, hop_s: float = 6.4) -> np.ndarray:
    """Build non-overlapping interval bounds for ordered window centres."""
    centres = np.asarray(centres, dtype=np.float64)
    if centres.size == 0:
        return np.zeros((0, 2), dtype=np.float64)
    order = np.argsort(centres, kind="stable")
    centres = centres[order]
    # De-duplicate identical centres; keep the first.
    keep = np.ones(len(centres), dtype=bool)
    keep[1:] = centres[1:] != centres[:-1]
    centres = centres[keep]
    starts = centres
    ends = centres + hop_s
    # Ensure positive length and monotonicity.
    ends = np.maximum(ends, starts + 1e-3)
    if len(starts) > 1:
        ends[:-1] = np.minimum(ends[:-1], starts[1:])
    return np.stack([starts, ends], axis=1)


def _normalise_label_for_mireval(label: str) -> str:
    """mir_eval does not accept our ``X`` label — score it as no-chord."""
    return "N" if label == "X" else label


def wcsr_metrics(
    ref_labels: np.ndarray,
    est_labels: np.ndarray,
    centres: np.ndarray,
    *,
    hop_s: float = 6.4,
) -> dict[str, float]:
    """Compute mir_eval WCSR metrics for one track (ordered windows)."""
    import mir_eval

    if len(ref_labels) == 0:
        return {key: 0.0 for key in _WCSR_KEYS}
    order = np.argsort(centres, kind="stable")
    intervals = window_intervals(np.asarray(centres)[order], hop_s)
    # window_intervals de-duplicates; mirror that on the labels.
    uniq_mask = np.ones(len(intervals), dtype=bool)
    # Rebuild labels aligned to the de-duplicated, sorted order.
    centres_sorted = np.asarray(centres, dtype=np.float64)[order]
    keep = np.ones(len(centres_sorted), dtype=bool)
    keep[1:] = centres_sorted[1:] != centres_sorted[:-1]
    ref = [_normalise_label_for_mireval(str(x)) for x in np.asarray(ref_labels)[order][keep]]
    est = [_normalise_label_for_mireval(str(x)) for x in np.asarray(est_labels)[order][keep]]
    try:
        scores = mir_eval.chord.evaluate(intervals, ref, intervals, est)
    except Exception:
        return {key: 0.0 for key in _WCSR_KEYS}
    return {key: float(scores.get(key, 0.0)) for key in _WCSR_KEYS}


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int = NUM_CLASSES_170) -> float:
    """Macro F1 over classes present in either prediction or truth."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    if len(y_true) == 0:
        return 0.0
    f1s: list[float] = []
    classes = np.unique(np.concatenate([y_true, y_pred]))
    for cls in classes:
        tp = int(np.sum((y_pred == cls) & (y_true == cls)))
        fp = int(np.sum((y_pred == cls) & (y_true != cls)))
        fn = int(np.sum((y_pred != cls) & (y_true == cls)))
        denom = 2 * tp + fp + fn
        f1s.append(2 * tp / denom if denom else 0.0)
    return float(np.mean(f1s))


def per_quality_report(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, dict]:
    """Precision/recall/F1 per chord quality (root-agnostic classes)."""
    true_quality = np.array([
        _decode_label(int(i))[1] or ("N" if int(i) == N_IDX_170 else "X")
        for i in y_true
    ])
    pred_quality = np.array([
        _decode_label(int(i))[1] or ("N" if int(i) == N_IDX_170 else "X")
        for i in y_pred
    ])
    report: dict[str, dict] = {}
    for quality in list(QUALITIES_14) + ["N", "X"]:
        tp = int(np.sum((pred_quality == quality) & (true_quality == quality)))
        fp = int(np.sum((pred_quality == quality) & (true_quality != quality)))
        fn = int(np.sum((pred_quality != quality) & (true_quality == quality)))
        support = int(np.sum(true_quality == quality))
        if support == 0 and fp == 0:
            continue
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        report[quality] = {
            "support": support,
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
        }
    return report


def bass_accuracy(
    bass_true: np.ndarray,
    bass_pred: np.ndarray,
    chord_true: np.ndarray,
) -> dict:
    """Bass accuracy overall, on known-bass frames, and on chord frames."""
    chord_mask = (chord_true != N_IDX_170) & (chord_true != X_IDX_170)
    known = chord_mask & (bass_true != BASS_X_IDX)
    overall = float(np.mean(bass_true == bass_pred)) if len(bass_true) else 0.0
    known_acc = float(np.mean((bass_true == bass_pred)[known])) if known.any() else 0.0
    chord_acc = float(np.mean((bass_true == bass_pred)[chord_mask])) if chord_mask.any() else 0.0
    return {
        "overall": overall,
        "known_bass": known_acc,
        "chord_frames": chord_acc,
        "n_known": int(np.sum(known)),
    }


def slash_accuracy(
    chord_true: np.ndarray,
    chord_pred: np.ndarray,
    bass_true: np.ndarray,
    bass_pred: np.ndarray,
) -> dict:
    """Slash-chord accuracy with root-position and inversion split out."""
    roots = np.array([
        ROOTS_12.index(_decode_label(int(i))[0]) if _decode_label(int(i))[0] else -1
        for i in chord_true
    ])
    is_chord = roots >= 0
    known_bass = is_chord & (bass_true != BASS_X_IDX)
    root_pos = known_bass & (bass_true == roots)
    inversions = known_bass & (bass_true != roots)
    exact = (chord_true == chord_pred) & (bass_true == bass_pred)
    return {
        "root_position_acc": float(np.mean(exact[root_pos])) if root_pos.any() else 0.0,
        "slash_acc": float(np.mean(exact[inversions])) if inversions.any() else 0.0,
        "n_root_position": int(np.sum(root_pos)),
        "n_slash": int(np.sum(inversions)),
    }


def top_k_accuracy(probs: np.ndarray, y_true: np.ndarray, k: int = 3) -> float:
    if len(y_true) == 0:
        return 0.0
    top = np.argsort(-np.asarray(probs), axis=1)[:, :k]
    return float(np.mean((top == np.asarray(y_true)[:, None]).any(axis=1)))


def expected_calibration_error(
    probs: np.ndarray,
    y_true: np.ndarray,
    weights: np.ndarray | None = None,
    n_bins: int = 10,
) -> float:
    """Duration-weighted ECE using the top-class confidence."""
    if len(y_true) == 0:
        return 0.0
    probs = np.asarray(probs)
    confidence = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == np.asarray(y_true)).astype(np.float64)
    if weights is None:
        weights = np.ones(len(y_true), dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    total = weights.sum()
    if total <= 0:
        return 0.0
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for index in range(n_bins):
        lo, hi = bin_edges[index], bin_edges[index + 1]
        mask = (confidence >= lo) & (confidence < hi if index < n_bins - 1 else confidence <= hi)
        if not mask.any():
            continue
        bin_weight = weights[mask].sum()
        if bin_weight <= 0:
            continue
        avg_conf = float(np.sum(confidence[mask] * weights[mask]) / bin_weight)
        avg_acc = float(np.sum(correct[mask] * weights[mask]) / bin_weight)
        ece += (bin_weight / total) * abs(avg_conf - avg_acc)
    return float(ece)


def evaluate_arrays(
    chord_true: np.ndarray,
    chord_pred: np.ndarray,
    bass_true: np.ndarray | None,
    bass_pred: np.ndarray | None,
    chord_probs: np.ndarray,
    track_ids: list[str],
    centres: np.ndarray,
    sources: list[str] | None = None,
    *,
    hop_s: float = 6.4,
) -> dict:
    """Full evaluation report over window-level predictions."""
    chord_true = np.asarray(chord_true)
    chord_pred = np.asarray(chord_pred)
    bass_true = np.asarray(bass_true) if bass_true is not None else None
    bass_pred = np.asarray(bass_pred) if bass_pred is not None else None

    report: dict = {
        "n_windows": int(len(chord_true)),
        "n_tracks": len(set(track_ids)),
        "macro_f1": macro_f1(chord_true, chord_pred),
        "exact_accuracy": float(np.mean(chord_true == chord_pred)) if len(chord_true) else 0.0,
        "top3_accuracy": top_k_accuracy(chord_probs, chord_true, 3),
        "top5_accuracy": top_k_accuracy(chord_probs, chord_true, 5),
        "ece": expected_calibration_error(chord_probs, chord_true),
        "per_quality": per_quality_report(chord_true, chord_pred),
    }

    # WCSR per track, aggregated by window count.
    by_track: dict[str, list[int]] = defaultdict(list)
    for index, track in enumerate(track_ids):
        by_track[track].append(index)
    wcsr_accum = defaultdict(float)
    wcsr_weight = 0
    wcsr_per_track: dict[str, dict] = {}
    for track, indices in by_track.items():
        indices_arr = np.asarray(indices)
        ref = np.array([
            label_to_harte(int(c), int(b) if bass_true is not None else None)
            for c, b in zip(chord_true[indices_arr],
                            bass_true[indices_arr] if bass_true is not None
                            else [None] * len(indices_arr))
        ])
        est = np.array([
            label_to_harte(int(c), int(b) if bass_pred is not None else None)
            for c, b in zip(chord_pred[indices_arr],
                            bass_pred[indices_arr] if bass_pred is not None
                            else [None] * len(indices_arr))
        ])
        track_scores = wcsr_metrics(ref, est, np.asarray(centres)[indices_arr], hop_s=hop_s)
        wcsr_per_track[track] = track_scores
        weight = len(indices_arr)
        wcsr_weight += weight
        for key, value in track_scores.items():
            wcsr_accum[key] += value * weight
    report["wcsr"] = {
        key: (wcsr_accum[key] / wcsr_weight if wcsr_weight else 0.0)
        for key in _WCSR_KEYS
    }

    if bass_true is not None and bass_pred is not None:
        report["bass"] = bass_accuracy(bass_true, bass_pred, chord_true)
        report["slash"] = slash_accuracy(chord_true, chord_pred, bass_true, bass_pred)

    if sources is not None:
        report["per_source"] = {}
        sources_arr = np.asarray(sources)
        for source in sorted(set(sources)):
            mask = sources_arr == source
            if not mask.any():
                continue
            idx = np.flatnonzero(mask)
            report["per_source"][source] = {
                "n_windows": int(mask.sum()),
                "macro_f1": macro_f1(chord_true[idx], chord_pred[idx]),
                "exact_accuracy": float(np.mean(chord_true[idx] == chord_pred[idx])),
                "wcsr_mirex": float(np.mean([
                    wcsr_per_track[t]["mirex"] for t in set(track_ids[i] for i in idx)
                ])) if len(idx) else 0.0,
            }
    return report


# ---------------------------------------------------------------------------
# Checkpoint loading / prediction (TensorFlow imported lazily)
# ---------------------------------------------------------------------------


def load_model(model_path: Path, *, build_fn=None):
    """Load a saved 170-class Keras checkpoint.

    ``build_fn`` is a callable returning the architecture and is only needed
    for older checkpoints that require a full model definition; the .keras
    format carries the architecture.
    """
    import os

    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
    import tensorflow as tf

    from scripts.eval_chord_baseline import keras_config_compat_copy
    from scripts.train_chord_170 import CircularCqtPad

    patched = keras_config_compat_copy(Path(model_path))
    try:
        return tf.keras.models.load_model(
            str(patched or model_path),
            custom_objects={"CircularCqtPad": CircularCqtPad},
            safe_mode=False,
        )
    finally:
        if patched is not None:
            Path(patched).unlink(missing_ok=True)


def predict_arrays(model, features: np.ndarray, batch_size: int = 256) -> tuple[np.ndarray, np.ndarray]:
    """Return (chord_probs, bass_probs) as float32 arrays."""
    outputs = model.predict(features, batch_size=batch_size, verbose=0)
    if isinstance(outputs, dict):
        chord = outputs["chord_probs"]
        bass = outputs.get("bass_probs")
    else:  # list output: chord, bass
        chord, bass = outputs[0], outputs[1] if len(outputs) > 1 else None
    chord = np.asarray(chord, dtype=np.float32)
    bass = (np.asarray(bass, dtype=np.float32) if bass is not None
            else np.zeros((len(chord), len(BASS_VOCAB)), dtype=np.float32))
    return chord, bass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=_BACKEND_DIR / "data")
    parser.add_argument("--sources", default="guitarset,egset12")
    parser.add_argument("--split", default="test")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--batch-size", type=int, default=256)
    args = parser.parse_args(argv)

    from scripts import chord_data_v2 as data

    source_dirs = {
        "guitarset": args.data_root / "guitarset",
        "egset12": args.data_root / "egset12",
        "guitar_techs": args.data_root / "guitar_techs",
        "idmt_smt_guitar": args.data_root / "idmt_smt_guitar",
        "rwc": args.data_root / "rwc",
        "pseudo_v2": args.data_root / "chord170" / "pseudo_v2",
    }
    features, labels, bass, track_ids, centres, sources = [], [], [], [], [], []
    for name in [s.strip() for s in args.sources.split(",") if s.strip()]:
        loaded = data.load_dataset_dir_170(source_dirs[name], args.split)
        if len(loaded["labels170"]) == 0:
            continue
        features.append(loaded["features"])
        labels.append(loaded["labels170"])
        bass.append(loaded["bass_labels"])
        track_ids.extend(loaded["track_ids"])
        centres.append(loaded["center_times"])
        sources.extend([name] * len(loaded["labels170"]))
    if not features:
        print("No windows for the requested sources/split.", file=sys.stderr)
        return 1

    X = np.concatenate(features)
    y = np.concatenate(labels)
    b = np.concatenate(bass)
    c = np.concatenate(centres)
    model = load_model(args.checkpoint)
    chord_probs, bass_probs = predict_arrays(model, X, args.batch_size)
    chord_pred = chord_probs.argmax(axis=1)
    bass_pred = bass_probs.argmax(axis=1)
    report = evaluate_arrays(y, chord_pred, b, bass_pred, chord_probs, track_ids, c, sources)
    report["checkpoint"] = str(args.checkpoint)
    report["split"] = args.split
    report["sources"] = sorted(set(sources))

    print(json.dumps({k: report[k] for k in
                      ("n_windows", "n_tracks", "macro_f1", "exact_accuracy",
                       "top3_accuracy", "ece", "wcsr") if k in report}, indent=2))
    if "bass" in report:
        print("bass:", json.dumps(report["bass"], indent=2))
    if "slash" in report:
        print("slash:", json.dumps(report["slash"], indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2))
        print(f"report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
