"""Phase 0 baseline evaluation harness — Chord 170 program.

Evaluates every historical chord-model checkpoint on the same GuitarSet
windows with the same MIREX-25 comparison metrics, so the fair baseline,
the v1.0.5 presence-gate regression, and the deployed-head mismatch can be
documented before any new model is trained.

Baselines (evaluated separately — never pooled):
  - ``deployed-keras-chord-head``: backend/app/chord_model.keras, argmax of
    the chord_probs head only (25-class MIREX).
  - ``deployed-keras-presence-gated``: same model, but presence < 0.5 forces
    N — replicates ``extract_chord_predictions`` (build_chord_tflite.py:1895).
    This is the gate whose checkpoint-selection regression must be measured.
  - ``v1.0.3-tflite-277``: archived 277-class/40-bin TFLite (Flex delegate
    required; reported as unavailable when the delegate is absent).
  - ``v1.0.5-tflite-277``: research snapshot chord head only (presence was
    dropped at export, so gated metrics are structurally impossible).

Usage (from backend/)::

    python scripts/eval_chord_baseline.py --split test --limit-tracks 10
    python scripts/eval_chord_baseline.py --split test --out \
        ../docs/audit/amt/chord170_phase0_baseline.json

TF/TFLite imports are deferred into functions so the metric helpers stay
unit-testable without TensorFlow.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

import numpy as np

_SCRIPTS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPTS_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_vocab import (  # noqa: E402
    CHORD_VOCAB,
    MIREX_VOCAB,
    NUM_CLASSES_MIREX,
    mirex_label,
)

GUITARSET_CQT_DIR = _BACKEND_DIR / "data" / "guitarset" / "processed" / "cqt"
GUITARSET_AUDIO_DIR = _BACKEND_DIR / "data" / "guitarset" / "raw" / "audio_mono-mix"
DEPLOYED_KERAS = _BACKEND_DIR / "app" / "chord_model.keras"
V103_TFLITE = _BACKEND_DIR / "research" / "h-gain-v1.0.3" / "chord_model.tflite"
V105_TFLITE = _BACKEND_DIR / "research" / "h-gain-v1.0.5" / "chord_model.tflite"

N_IDX_25 = NUM_CLASSES_MIREX - 1  # 24


# ---------------------------------------------------------------------------
# Window loading
# ---------------------------------------------------------------------------


def list_track_files(cqt_dir: Path, split: str) -> list[Path]:
    """Return sorted .npz window files whose ``split`` matches."""
    files: list[tuple[str, Path]] = []
    for npz_path in sorted(cqt_dir.glob("*.npz")):
        try:
            data = np.load(npz_path)
            track_split = str(data["split"])
        except Exception as exc:
            print(f"  [WARN] skipping {npz_path.name}: {exc}")
            continue
        if track_split == split:
            files.append((npz_path.name, npz_path))
    return [path for _, path in files]


def load_windows(
    cqt_dir: Path,
    split: str,
    *,
    limit_tracks: int = 0,
) -> dict:
    """Load GuitarSet .npz windows for a split.

    Returns dict with features (N, 128, 144), labels277 (N,), track_ids (N,),
    n_tracks. Windows are pooled per-file; the split key is trusted from the
    file (player-level split by construction — no track overlap).
    """
    features: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    track_ids: list[str] = []
    tracks_used = 0
    for npz_path in list_track_files(cqt_dir, split):
        data = np.load(npz_path)
        features.append(data["features"])
        labels.append(data["labels"])
        track_ids.extend([str(data["track_id"])] * data["features"].shape[0])
        tracks_used += 1
        if limit_tracks and tracks_used >= limit_tracks:
            break
    if not features:
        return {
            "features": np.zeros((0, 128, 144), dtype=np.float32),
            "labels277": np.zeros((0,), dtype=np.int64),
            "track_ids": [],
            "n_tracks": 0,
        }
    return {
        "features": np.concatenate(features, axis=0),
        "labels277": np.concatenate(labels, axis=0).astype(np.int64),
        "track_ids": track_ids,
        "n_tracks": tracks_used,
    }


# ---------------------------------------------------------------------------
# Metrics (25-class MIREX comparison space)
# ---------------------------------------------------------------------------


def _to_root(idx_25: int) -> int:
    """Collapse a 25-class index to {0..11} root index, N → 12."""
    if idx_25 == N_IDX_25:
        return 12
    return idx_25 % 12


def chord_metrics_25(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    probs: np.ndarray | None = None,
    top_k: int = 3,
) -> dict:
    """Compute exact/root/macro-F1/top-k/N metrics in the 25-class space.

    Args:
        y_true: (N,) true 25-class indices.
        y_pred: (N,) predicted 25-class indices.
        probs: (N, 25) optional predicted probabilities for top-k accuracy.
        top_k: k for top-k accuracy (needs probs).

    Returns:
        Dict of window counts and metrics.
    """
    y_true = np.asarray(y_true, dtype=np.int64)
    y_pred = np.asarray(y_pred, dtype=np.int64)
    n = len(y_true)
    metrics: dict = {"n_windows": int(n)}
    if n == 0:
        return {**metrics, "exact_accuracy": 0.0, "root_accuracy": 0.0,
                "macro_f1": 0.0, "top3_accuracy": None,
                "n_true_rate": 0.0, "n_pred_rate": 0.0}
    metrics["exact_accuracy"] = float(np.mean(y_true == y_pred))
    root_true = np.array([_to_root(i) for i in y_true])
    root_pred = np.array([_to_root(i) for i in y_pred])
    metrics["root_accuracy"] = float(np.mean(root_true == root_pred))

    macro_f1s: list[float] = []
    classes = np.unique(np.concatenate([y_true, y_pred]))
    for cls in classes:
        tp = int(np.sum((y_pred == cls) & (y_true == cls)))
        fp = int(np.sum((y_pred == cls) & (y_true != cls)))
        fn = int(np.sum((y_pred != cls) & (y_true == cls)))
        denom = 2 * tp + fp + fn
        macro_f1s.append(2 * tp / denom if denom else 0.0)
    metrics["macro_f1"] = float(np.mean(macro_f1s))

    if probs is not None and len(probs) == n:
        topk = np.argsort(-probs, axis=1)[:, :top_k]
        hits = (topk == y_true[:, None]).any(axis=1)
        metrics[f"top{top_k}_accuracy"] = float(np.mean(hits))
    else:
        metrics[f"top{top_k}_accuracy"] = None

    metrics["n_true_rate"] = float(np.mean(y_true == N_IDX_25))
    metrics["n_pred_rate"] = float(np.mean(y_pred == N_IDX_25))
    return metrics


def map_277_to_mirex25(labels277: np.ndarray) -> np.ndarray:
    """Map 277-class label indices to 25-class MIREX indices."""
    return np.array([mirex_label(int(i)) for i in labels277], dtype=np.int64)


def gate_impact(y_true: np.ndarray, y_pred_head: np.ndarray, y_pred_gated: np.ndarray) -> dict:
    """Summarize what the presence gate changed (correct → wrong and vice versa)."""
    forced_n = y_pred_head != y_pred_gated
    was_correct = y_pred_head == y_true
    gated_correct = y_pred_gated == y_true
    return {
        "n_forced_changed": int(np.sum(forced_n)),
        "forced_change_rate": float(np.mean(forced_n)) if len(forced_n) else 0.0,
        "correct_to_wrong": int(np.sum(forced_n & was_correct & ~gated_correct)),
        "wrong_to_correct": int(np.sum(forced_n & ~was_correct & gated_correct)),
        "wrong_to_wrong": int(np.sum(forced_n & ~was_correct & gated_correct) == 0
                              and int(np.sum(forced_n & ~was_correct & ~gated_correct)) or 0),
    }


# ---------------------------------------------------------------------------
# Deployed Keras model (25-class multi-task)
# ---------------------------------------------------------------------------


def _load_keras_model(path: Path):
    """Load a .keras model with the CircularCqtPad custom objects.

    Mirrors the loading path in app/chord_inference.py (config ``optional``
    strip for tf_keras 2.20 compatibility).
    """
    import os

    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
    os.environ["TF_USE_LEGACY_KERAS"] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"  # WSL2 GPU crashes on LSTM init; force CPU
    import tensorflow as tf

    class _CircularPadImpl(tf.keras.layers.Layer):
        def call(self, x):
            return tf.concat([x[:, :, -1:], x, x[:, :, :1]], axis=-1)

        def compute_output_shape(self, input_shape):
            return (input_shape[0], input_shape[1], input_shape[2] + 2)

        def get_config(self):
            return super().get_config()

    def _circular_cqt_pad(x):
        return tf.concat([x[:, :, -1:], x, x[:, :, :1]], axis=-1)

    patched = None
    try:
        with zipfile.ZipFile(path) as zin:
            config = json.loads(zin.read("config.json"))
            changed = False

            def _strip_optional(node) -> None:
                nonlocal changed
                if isinstance(node, dict):
                    if node.get("class_name") == "InputLayer" and isinstance(node.get("config"), dict):
                        if "optional" in node["config"]:
                            node["config"].pop("optional", None)
                            changed = True
                    for value in node.values():
                        _strip_optional(value)
                elif isinstance(node, list):
                    for value in node:
                        _strip_optional(value)

            _strip_optional(config)
            if changed:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".keras", delete=False) as tmp:
                    patched = Path(tmp.name)
                with zipfile.ZipFile(patched, "w", zipfile.ZIP_DEFLATED) as zout:
                    for item in zin.infolist():
                        data = (json.dumps(config).encode()
                                if item.filename == "config.json" else zin.read(item.filename))
                        zout.writestr(item, data)
    except Exception as exc:
        print(f"  [WARN] keras config patch skipped for {path.name}: {exc}")

    load_path = patched or path
    try:
        model = tf.keras.models.load_model(
            str(load_path),
            custom_objects={
                "_circular_cqt_pad": _circular_cqt_pad,
                "CircularCqtPad": _CircularPadImpl,
                "Custom>CircularCqtPad": _CircularPadImpl,
            },
            safe_mode=False,
        )
    finally:
        if patched is not None:
            patched.unlink(missing_ok=True)
    return model


def _model_output_names(model) -> list[str]:
    try:
        return [out.tensoraliasname if hasattr(out, "tensoraliasname") else out.name
                for out in getattr(model, "outputs", [])]
    except Exception:
        return []


def eval_deployed_keras(
    features: np.ndarray,
    labels_mirex: np.ndarray,
    model_path: Path = DEPLOYED_KERAS,
    *,
    batch_size: int = 256,
) -> dict:
    """Evaluate the deployed 25-class multi-task model two ways.

    Returns a dict with separate ``chord_head`` and ``presence_gated`` metric
    blocks plus the gate-impact summary. Presence gating replicates
    ``extract_chord_predictions`` (presence < 0.5 → forced N).
    """
    model = _load_keras_model(model_path)
    outputs: dict = {}
    preds = model.predict(features, batch_size=batch_size, verbose=0)
    if isinstance(preds, dict):
        outputs = preds
    elif isinstance(preds, list):
        for i, out in enumerate(model.outputs):
            outputs[out.name.split("/")[0]] = preds[i]
        # Fall back to positional names when name parsing is ambiguous
        if len(preds) == 3:
            outputs.setdefault("chord_probs", preds[0])
            outputs.setdefault("root_probs", preds[1])
            outputs.setdefault("presence", preds[2])
    else:
        outputs = {"chord_probs": preds}

    chord_probs = np.asarray(outputs["chord_probs"])
    head_pred = np.argmax(chord_probs, axis=1)

    result: dict = {}
    result["chord_head"] = chord_metrics_25(labels_mirex, head_pred, chord_probs)
    if "presence" in outputs:
        presence = np.asarray(outputs["presence"]).flatten()
        gated_pred = head_pred.copy()
        gated_pred[presence < 0.5] = N_IDX_25
        result["presence_gated"] = chord_metrics_25(labels_mirex, gated_pred, None)
        result["gate_impact"] = gate_impact(labels_mirex, head_pred, gated_pred)
        result["presence_low_rate"] = float(np.mean(presence < 0.5))
    else:
        result["presence_gated"] = None
        result["note"] = "no presence head in checkpoint — chord-head-only metrics only"
    return result


# ---------------------------------------------------------------------------
# TFLite baselines (v1.0.3 40-bin, v1.0.5 36-bin) — Flex delegate required
# ---------------------------------------------------------------------------


def _flex_delegate_available() -> tuple[bool, str]:
    """Locate libtensorflowlite_flex.so without globbing the whole tree."""
    import glob as _glob

    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    import tensorflow as tf  # deferred import

    base = Path(tf.__file__).resolve().parent / "lite"
    for pattern in ("**/libtensorflowlite_flex.so", "**/*flex*"):
        hits = _glob.glob(str(base / pattern), recursive=True)
        if hits:
            return True, hits[0]
    return False, ""


def eval_tflite_277(
    features: np.ndarray,
    labels_mirex: np.ndarray,
    model_path: Path,
    label: str,
    *,
    batch_size: int = 256,
) -> dict:
    """Evaluate a 277-class TFLite checkpoint (chord head only) on windows.

    Features must already match the model input width (v1.0.3: 40, v1.0.5:
    36) — see :func:`compute_cqt_36_40`. Returns metrics in MIREX-25 space,
    or ``{"status": "unavailable", ...}`` when Flex is missing.
    """
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    import tensorflow as tf  # deferred import

    if not model_path.exists():        return {"status": "unavailable", "reason": f"artifact missing: {model_path}"}
    ok, flex_path = _flex_delegate_available()
    if not ok:
        return {
            "status": "unavailable",
            "reason": (
                "Flex delegate (libtensorflowlite_flex.so) not installed — "
                "BiLSTM models cannot run in-process. See docs/CHORD_170_PHASE0_BASELINE.md."
            ),
        }
    try:
        from tensorflow.lite.python import interpreter as _interp

        delegate = _interp.load_delegate(flex_path)
        interp = tf.lite.Interpreter(
            model_path=str(model_path), experimental_delegates=[delegate]
        )
        interp.allocate_tensors()
        inp = interp.get_input_details()[0]
        out = interp.get_output_details()[0]
        n_windows = len(features)
        probs277 = np.zeros((n_windows, out["shape"][-1]), dtype=np.float32)
        for start in range(0, n_windows, batch_size):
            end = min(start + batch_size, n_windows)
            interp.set_tensor(inp["index"], features[start:end])
            interp.invoke()
            probs277[start:end] = interp.get_tensor(out["index"])
        pred277 = np.argmax(probs277, axis=1)
        pred25 = map_277_to_mirex25(pred277)
        return {
            "status": "ok",
            "tflite_input_width": int(inp["shape"][-1]),
            "tflite_outputs": [o["shape"][-1] for o in interp.get_output_details()],
            "chord_head": chord_metrics_25(labels_mirex, pred25, None),
            "label": label,
        }
    except Exception as exc:
        return {"status": "unavailable", "reason": f"interpreter failed: {exc}"}


def compute_cqt_36_40(audio_path: Path, track_id: str, width: int) -> np.ndarray:
    """Compute 36/40-bin CQT windows aligned with the stored 144-bin npz.

    Uses the v1.0.3-era feature spec: 36 chroma bins (bins_per_octave=12,
    C1 start) at 0.1 s hop, L1-normalized per frame, plus (width 40) the
    first 4 bins appended as a bass channel. Window geometry matches
    extract_guitarset_cqt.py (128 window, 64 hop, center label).
    """
    import librosa

    y, sr = librosa.load(str(audio_path), sr=44100, mono=True)
    hop = int(sr * 0.1)
    cqt = librosa.cqt(y=y, sr=sr, hop_length=hop, n_bins=36, bins_per_octave=12)
    cqt = np.abs(cqt.T).astype(np.float32)
    if width == 40:
        cqt = np.concatenate([cqt, cqt[:, :4]], axis=1)
    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    feats = cqt / norms

    pad = np.zeros((64, width), dtype=np.float32)
    padded = np.concatenate([pad, feats, pad], axis=0)
    windows = []
    k = 0
    while True:
        start = k * 64
        window = padded[start:start + 128]
        if len(window) < 128:
            break
        windows.append(window)
        k += 1
    return np.stack(windows, axis=0)


def eval_tflite_from_audio(
    track_ids: list[str],
    labels277: np.ndarray,
    model_path: Path,
    label: str,
    width: int,
    audio_dir: Path = GUITARSET_AUDIO_DIR,
    *,
    limit_tracks: int = 0,
) -> dict:
    """Run a 277-class TFLite baseline on recomputed 36/40-bin windows.

    Windows are aligned by construction (same 128/64 geometry and center
    labels as the 144-bin npz), so the stored 277 labels apply unchanged.
    """
    labels_mirex = map_277_to_mirex25(labels277)
    used_tracks = sorted(set(track_ids))[:limit_tracks] if limit_tracks else sorted(set(track_ids))
    keep_mask = np.array([tid in set(used_tracks) for tid in track_ids])
    labels277_k = labels277[keep_mask]
    labels_mirex_k = labels_mirex[keep_mask]
    feats: list[np.ndarray] = []
    y_true_mirex: list[np.ndarray] = []
    per_track_counts: dict[str, int] = {}
    label_iter = iter(labels_mirex_k.tolist())
    for track_id in used_tracks:
        audio_path = audio_dir / f"{track_id}.wav"
        if not audio_path.exists():
            print(f"  [WARN] audio missing for {track_id}")
            continue
        windows = compute_cqt_36_40(audio_path, track_id, width)
        count = int(np.sum(np.array(track_ids) == track_id))
        if count != len(windows):
            print(
                f"  [WARN] {track_id}: {count} stored labels vs {len(windows)} recomputed windows "
                "— skipping track"
            )
            for _ in range(count):
                next(label_iter, None)
            continue
        feats.append(windows)
        y_true_mirex.append(np.array([next(label_iter) for _ in range(count)], dtype=np.int64))
        per_track_counts[track_id] = count
    if not feats:
        return {"status": "unavailable", "reason": "no usable audio/windows"}
    return eval_tflite_277(
        np.concatenate(feats, axis=0),
        np.concatenate(y_true_mirex, axis=0),
        model_path,
        label,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="test", choices=["test", "val", "train"])
    parser.add_argument("--limit-tracks", type=int, default=0)
    parser.add_argument("--models", default="all",
                        choices=["all", "deployed", "v103", "v105"])
    parser.add_argument("--out", type=Path,
                        default=_BACKEND_DIR / "docs" / "audit" / "amt" / "chord170_phase0_baseline.json")
    args = parser.parse_args(argv)

    print(f"Loading GuitarSet windows (split={args.split}, limit={args.limit_tracks or 'none'})")
    windows = load_windows(GUITARSET_CQT_DIR, args.split, limit_tracks=args.limit_tracks)
    n_windows = len(windows["labels277"])
    labels_mirex = map_277_to_mirex25(windows["labels277"])
    print(f"  {windows['n_tracks']} tracks, {n_windows} windows, "
          f"N rate (MIREX truth): {np.mean(labels_mirex == N_IDX_25):.4f}")
    if n_windows == 0:
        print("No windows for split — nothing to evaluate.")
        return 1

    report: dict = {
        "split": args.split,
        "n_tracks": windows["n_tracks"],
        "n_windows": n_windows,
        "n_true_rate_mirex25": float(np.mean(labels_mirex == N_IDX_25)),
        "comparison_space": "MIREX-25 (app.chord_vocab.MIREX_VOCAB)",
        "baselines": {},
    }

    want_all = args.models == "all"
    if want_all or args.models == "deployed":
        print("Evaluating deployed production model (chord-head-only vs presence-gated)")
        report["baselines"]["deployed-keras"] = eval_deployed_keras(
            windows["features"], labels_mirex
        )
        print(f"  chord-head    exact={report['baselines']['deployed-keras']['chord_head']['exact_accuracy']:.4f}")
        if report["baselines"]["deployed-keras"].get("presence_gated"):
            print(f"  presence-gated exact={report['baselines']['deployed-keras']['presence_gated']['exact_accuracy']:.4f}")

    if want_all or args.models == "v103":
        print("Evaluating v1.0.3 (277-class, 40-bin) — requires Flex delegate")
        report["baselines"]["v1.0.3-tflite-277"] = eval_tflite_from_audio(
            windows["track_ids"], windows["labels277"], V103_TFLITE, "v1.0.3", width=40,
            limit_tracks=args.limit_tracks,
        )

    if want_all or args.models == "v105":
        print("Evaluating v1.0.5 (277-class, 36-bin) — requires Flex delegate")
        report["baselines"]["v1.0.5-tflite-277"] = eval_tflite_from_audio(
            windows["track_ids"], windows["labels277"], V105_TFLITE, "v1.0.5", width=36,
            limit_tracks=args.limit_tracks,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(f"Report written to {args.out}")

    print("\n== Summary (MIREX-25 comparison space) ==")
    for name, result in report["baselines"].items():
        if result.get("status") == "unavailable":
            print(f"  {name:32s} UNAVAILABLE — {result['reason'][:80]}")
            continue
        head = result["chord_head"]
        line = (f"  {name:32s} exact={head['exact_accuracy']:.4f} "
                f"root={head['root_accuracy']:.4f} macroF1={head['macro_f1']:.4f}")
        gated = result.get("presence_gated")
        if gated:
            line += f" | gated exact={gated['exact_accuracy']:.4f}"
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
