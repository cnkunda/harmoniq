"""Phase 3 training for the 170-class chord model (chord + bass heads).

Architecture (v1.0.3 encoder, 170-class heads):

    Input (128, 144) → CircularCqtPad → Conv1D 64 k3 → Conv1D 128 k3
    → BatchNorm → MultiHeadAttention(4, key_dim=64) + residual → LayerNorm
    → BiLSTM(128, seq) → BiLSTM(128) → Dense(256, ReLU) → Dropout(0.3)
    ├─ chord_probs: Dense(170, softmax)
    └─ bass_probs:  Dense(13, softmax)

Training recipe (program spec):
  * chord CE with label smoothing, bass CE weighted 0.35 (no hard presence gate)
  * temperature resampling τ=0.3 + source balancing, N never up-weighted
  * augmentation: pitch shift (CQT bin roll with label/bass remap), random
    gain, additive noise, SpecAugment masks (mixup intentionally not used)
  * cosine LR (AdamW, gradient clipping), mixed precision on GPU
  * checkpoint selection on validation WCSR MIREX (same metric as deployment)
    with patience; CSV log has a fixed header (never truncates)
  * 0 synthetic pretraining epochs by default (≤10 allowed); Phase 4 ablates

Artifacts (``--out-dir``): best.keras, final.keras, training_log.csv,
metrics.json (best-epoch report), per_class.json, confusion.npy, config.json
(args + git SHA + versions).

Usage (from backend/)::

    python scripts/train_chord_170.py --config configs/chord170_base.yaml
    python scripts/train_chord_170.py --epochs 2 --limit-train 200 --out-dir /tmp/chord170_smoke
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

import tensorflow as tf  # noqa: E402

from app.chord_labels import pitch_shift_labels  # noqa: E402
from app.chord_vocab_170 import (  # noqa: E402
    BASS_X_IDX,
    CHORD_VOCAB_170 as CHORD_LABELS,
    N_IDX_170,
    NUM_CLASSES_170,
    NUM_CLASSES_BASS,
    QUALITIES_14,
)
from scripts import chord_data_v2 as chord_data  # noqa: E402
from scripts.chord_data_v2 import sampling_probabilities  # noqa: E402
from scripts.eval_chord_170 import evaluate_arrays, macro_f1  # noqa: E402

WINDOW = 128
FEATURE_DIM = 144
BINS_PER_OCTAVE = 24
BINS_PER_SEMITONE = BINS_PER_OCTAVE // 12  # 2 bins per semitone (24 bins/octave)

SOURCE_DIRS = {
    "guitarset": "guitarset",
    "egset12": "egset12",
    "guitar_techs": "guitar_techs",
    "idmt_smt_guitar": "idmt_smt_guitar",
    "rwc": "rwc",
    "pseudo_v2": "chord170/pseudo_v2",
}


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


@tf.keras.utils.register_keras_serializable(package="harmoniq")
class CircularCqtPad(tf.keras.layers.Layer):
    """Circular padding on the CQT time axis (v1.0.3 encoder front end)."""

    def call(self, x):
        return tf.concat([x[:, -1:, :], x, x[:, :1, :]], axis=1)

    def compute_output_shape(self, input_shape):
        return (input_shape[0], input_shape[1] + 2, input_shape[2])


def build_model(
    window: int = WINDOW,
    feature_dim: int = FEATURE_DIM,
    num_chords: int = NUM_CLASSES_170,
    num_bass: int = NUM_CLASSES_BASS,
) -> tf.keras.Model:
    """Build the 170-class chord + 13-class bass CRNN."""
    inputs = tf.keras.Input(shape=(window, feature_dim), name="cqt_window")
    x = CircularCqtPad(name="circular_cqt_pad")(inputs)

    x = tf.keras.layers.Conv1D(64, kernel_size=3, padding="same", activation="relu",
                               name="conv1d_64")(x)
    x = tf.keras.layers.Conv1D(128, kernel_size=3, padding="same", activation="relu",
                               name="conv1d_128")(x)
    x = tf.keras.layers.BatchNormalization(name="bn_cnn")(x)

    attention = tf.keras.layers.MultiHeadAttention(
        num_heads=4, key_dim=64, name="self_attention"
    )
    attended = attention(x, x)
    x = tf.keras.layers.LayerNormalization(epsilon=1e-6, name="attention_layernorm")(
        x + attended
    )

    x = tf.keras.layers.Bidirectional(
        tf.keras.layers.LSTM(128, return_sequences=True), name="bilstm_1"
    )(x)
    x = tf.keras.layers.Bidirectional(
        tf.keras.layers.LSTM(128, return_sequences=False), name="bilstm_2"
    )(x)
    x = tf.keras.layers.Dense(256, activation="relu", name="dense_256")(x)
    x = tf.keras.layers.Dropout(0.3, name="dropout")(x)

    chord = tf.keras.layers.Dense(num_chords, activation="softmax", name="chord_probs")(x)
    bass = tf.keras.layers.Dense(num_bass, activation="softmax", name="bass_probs")(x)
    return tf.keras.Model(inputs=inputs, outputs={"chord_probs": chord, "bass_probs": bass},
                          name="chord_crnn_170")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_split(
    data_root: Path,
    sources: list[str],
    split: str,
    *,
    limit_tracks: int = 0,
) -> dict | None:
    """Load and concatenate one split across sources."""
    feats, labels, bass, conf, tracks, centres, srcs = [], [], [], [], [], [], []
    for source in sources:
        data_dir = data_root / SOURCE_DIRS[source]
        loaded = chord_data.load_dataset_dir_170(data_dir, split, limit_tracks=limit_tracks)
        if len(loaded["labels170"]) == 0:
            continue
        feats.append(loaded["features"])
        labels.append(loaded["labels170"])
        bass.append(loaded["bass_labels"])
        conf.append(loaded["confidence"])
        tracks.extend(loaded["track_ids"])
        centres.append(loaded["center_times"])
        srcs.extend([source] * len(loaded["labels170"]))
    if not feats:
        return None
    features = np.concatenate(feats)
    if features.shape[1:] != (WINDOW, FEATURE_DIM):
        raise ValueError(f"unexpected feature shape {features.shape}; expected (*, {WINDOW}, {FEATURE_DIM})")
    return {
        "features": features.astype(np.float32),
        "labels170": np.concatenate(labels),
        "bass_labels": np.concatenate(bass),
        "confidence": np.concatenate(conf),
        "track_ids": tracks,
        "center_times": np.concatenate(centres),
        "sources": np.asarray(srcs),
    }


# ---------------------------------------------------------------------------
# Augmentation
# ---------------------------------------------------------------------------


def _renormalise(features: np.ndarray) -> np.ndarray:
    norms = features.sum(axis=2, keepdims=True).clip(1e-8, None)
    return (features / norms).astype(np.float32)


def augment_batch(
    features: np.ndarray,
    chord: np.ndarray,
    bass: np.ndarray,
    rng: np.random.Generator,
    *,
    pitch_shift_range: int = 3,
    specaug_p: float = 0.5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """On-the-fly augmentation: pitch shift, gain, noise, SpecAugment."""
    features = features.copy()
    chord = chord.copy()
    bass = bass.copy()

    # Pitch shift: roll the 144 CQT bins (24 per octave) and remap labels.
    shifts = rng.integers(-pitch_shift_range, pitch_shift_range + 1, size=len(features))
    for index, shift in enumerate(shifts):
        if shift:
            features[index] = np.roll(features[index], int(shift) * BINS_PER_SEMITONE, axis=1)
            c_arr, b_arr = pitch_shift_labels(
                chord[index:index + 1], bass[index:index + 1], int(shift)
            )
            chord[index] = c_arr[0]
            bass[index] = b_arr[0]

    # Random gain + additive noise, then re-L1-normalise per frame.
    gain = rng.uniform(0.85, 1.15, size=(len(features), 1, 1)).astype(np.float32)
    features *= gain
    noise_sigma = rng.uniform(0.0, 0.02, size=(len(features), 1, 1)).astype(np.float32)
    features += rng.normal(0.0, 1.0, size=features.shape).astype(np.float32) * noise_sigma
    features = np.clip(features, 0.0, None)

    # SpecAugment: mask a frequency band and/or a time band.
    if rng.random() < specaug_p:
        for index in range(len(features)):
            if rng.random() < 0.5:
                width = int(rng.integers(1, 9))
                start = int(rng.integers(0, FEATURE_DIM - width))
                features[index, :, start:start + width] = 0.0
            if rng.random() < 0.5:
                width = int(rng.integers(1, 13))
                start = int(rng.integers(0, WINDOW - width))
                features[index, start:start + width, :] = 0.0
    return _renormalise(features), chord, bass


class ChordSequence(tf.keras.utils.Sequence):
    """Resampling + augmentation sequence (probabilities refreshed per epoch)."""

    def __init__(
        self,
        features: np.ndarray,
        chord: np.ndarray,
        bass: np.ndarray,
        probabilities: np.ndarray,
        *,
        batch_size: int,
        seed: int,
        augment: bool = True,
    ):
        super().__init__()
        self.features = features
        self.chord = chord
        self.bass = bass
        self.probabilities = probabilities
        self.batch_size = batch_size
        self.seed = seed
        self.augment = augment
        self.epoch = 0
        self.rng = np.random.default_rng(seed)

    def __len__(self) -> int:
        return max(1, int(np.ceil(len(self.features) / self.batch_size)))

    def __getitem__(self, index: int):
        indices = self.rng.choice(
            len(self.features), size=self.batch_size,
            replace=len(self.features) < self.batch_size,
            p=self.probabilities,
        )
        features = self.features[indices]
        chord = self.chord[indices]
        bass = self.bass[indices]
        if self.augment:
            features, chord, bass = augment_batch(features, chord, bass, self.rng)
        chord_onehot = tf.keras.utils.to_categorical(chord, num_classes=NUM_CLASSES_170)
        bass_onehot = tf.keras.utils.to_categorical(bass, num_classes=NUM_CLASSES_BASS)
        return features, {"chord_probs": chord_onehot, "bass_probs": bass_onehot}

    def on_epoch_end(self) -> None:
        self.epoch += 1
        self.rng = np.random.default_rng(self.seed + self.epoch)


# ---------------------------------------------------------------------------
# Validation callback (checkpoint metric = WCSR MIREX)
# ---------------------------------------------------------------------------


class ValidationCheckpoint(tf.keras.callbacks.Callback):
    """Per-epoch WCSR/macro-F1 validation, CSV logging, best-checkpoint saving."""

    HEADER = [
        "epoch", "loss", "chord_loss", "bass_loss", "train_acc", "train_macro_f1", "val_macro_f1",
        "val_wcsr_mirex", "val_wcsr_root", "val_wcsr_tetrads",
        "val_bass_acc", "val_slash_acc", "val_ece", "lr",
    ]

    def __init__(
        self,
        val_data: dict,
        out_dir: Path,
        *,
        patience: int = 12,
        batch_size: int = 256,
        train_sample: dict | None = None,
    ):
        super().__init__()
        self.val_data = val_data
        self.train_sample = train_sample
        self.out_dir = out_dir
        self.patience = patience
        self.batch_size = batch_size
        self.best_metric = -np.inf
        self.best_epoch = -1
        self.epochs_since_improvement = 0
        self.log_path = out_dir / "training_log.csv"
        self.lines_written = 0

    def _predict(self, features: np.ndarray):
        outputs = self.model.predict(features, batch_size=self.batch_size, verbose=0)
        chord = np.asarray(outputs["chord_probs"], dtype=np.float32)
        bass = np.asarray(outputs["bass_probs"], dtype=np.float32)
        return chord, bass

    def _evaluate(self) -> dict:
        chord_probs, bass_probs = self._predict(self.val_data["features"])
        return evaluate_arrays(
            self.val_data["labels170"], chord_probs.argmax(axis=1),
            self.val_data["bass_labels"], bass_probs.argmax(axis=1),
            chord_probs, self.val_data["track_ids"], self.val_data["center_times"],
            list(self.val_data["sources"]),
        )

    def on_epoch_end(self, epoch: int, logs: dict | None = None) -> None:
        logs = logs or {}
        started = time.time()
        report = self._evaluate()
        train_acc = train_f1 = ""
        if self.train_sample is not None:
            train_probs, _ = self._predict(self.train_sample["features"])
            train_pred = train_probs.argmax(axis=1)
            train_acc = float(np.mean(train_pred == self.train_sample["labels170"]))
            train_f1 = macro_f1(self.train_sample["labels170"], train_pred)
        entry = {
            "epoch": epoch + 1,
            "loss": logs.get("loss", ""),
            "chord_loss": logs.get("chord_probs_loss", ""),
            "bass_loss": logs.get("bass_probs_loss", ""),
            "train_acc": train_acc,
            "train_macro_f1": train_f1,
            "val_macro_f1": report["macro_f1"],
            "val_wcsr_mirex": report["wcsr"]["mirex"],
            "val_wcsr_root": report["wcsr"]["root"],
            "val_wcsr_tetrads": report["wcsr"]["tetrads"],
            "val_bass_acc": report.get("bass", {}).get("chord_frames", 0.0),
            "val_slash_acc": report.get("slash", {}).get("slash_acc", 0.0),
            "val_ece": report["ece"],
            "lr": float(tf.keras.backend.get_value(self.model.optimizer.learning_rate)),
        }
        with open(self.log_path, "a", encoding="utf-8") as handle:
            if self.lines_written == 0:
                handle.write(",".join(self.HEADER) + "\n")
            handle.write(",".join(str(entry[key]) for key in self.HEADER) + "\n")
        self.lines_written += 1
        print(
            f"    train acc={train_acc if train_acc != '' else 'n/a'} "
            f"val macroF1={report['macro_f1']:.4f} "
            f"WCSR-mirex={report['wcsr']['mirex']:.4f} "
            f"bass={entry['val_bass_acc']:.4f} ece={report['ece']:.4f} "
            f"({time.time() - started:.0f}s)",
            flush=True,
        )

        metric = report["wcsr"]["mirex"]
        if metric > self.best_metric:
            self.best_metric = metric
            self.best_epoch = epoch + 1
            self.epochs_since_improvement = 0
            self.model.save(self.out_dir / "best.keras")
            (self.out_dir / "metrics.json").write_text(json.dumps(
                {"epoch": self.best_epoch, "metric": "val_wcsr_mirex",
                 "metric_value": metric, **report}, indent=2))
            chord_pred = None
            chord_probs, bass_probs = self._predict(self.val_data["features"])
            chord_pred = chord_probs.argmax(axis=1)
            confusion = np.zeros((NUM_CLASSES_170, NUM_CLASSES_170), dtype=np.int64)
            np.add.at(confusion, (self.val_data["labels170"], chord_pred), 1)
            np.save(self.out_dir / "confusion.npy", confusion)
            per_class = {}
            for cls in np.unique(self.val_data["labels170"]):
                mask = self.val_data["labels170"] == cls
                per_class[str(int(cls))] = {
                    "label": (CHORD_LABELS[int(cls)] if int(cls) < N_IDX_170 else "N/X"),
                    "support": int(mask.sum()),
                    "recall": float(np.mean(chord_pred[mask] == cls)),
                }
            (self.out_dir / "per_class.json").write_text(json.dumps(per_class, indent=2))
            print(f"    saved best checkpoint (epoch {self.best_epoch})", flush=True)
        else:
            self.epochs_since_improvement += 1
            if self.epochs_since_improvement >= self.patience:
                print(
                    f"    early stopping: no WCSR-MIREX improvement for "
                    f"{self.patience} epochs",
                    flush=True,
                )
                self.model.stop_training = True



# ---------------------------------------------------------------------------
# Training entry point
# ---------------------------------------------------------------------------


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_BACKEND_DIR, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def load_config(path: Path | None) -> dict:
    if path is None:
        return {}
    text = Path(path).read_text()
    if path.suffix in (".yaml", ".yml"):
        import yaml

        return yaml.safe_load(text) or {}
    return json.loads(text)


def _configure_device(requested: str) -> bool:
    """Select GPU vs CPU and enable mixed precision only on a usable GPU.

    ``auto`` requires compute capability >= 7.0 for mixed-precision LSTM
    kernels (WSL's GTX 1050 at 6.1 fails JIT compilation, so it falls back
    to CPU). Modal A10G (8.6) takes the GPU path.
    """
    gpus = tf.config.list_physical_devices("GPU")
    use_gpu = bool(gpus) and requested != "cpu"
    if use_gpu and requested == "auto":
        try:
            details = tf.config.experimental.get_device_details(gpus[0])
            cc = details.get("compute_capability", (0, 0))
            use_gpu = tuple(cc) >= (7, 0)
            print(f"  GPU detected: {details.get('device_name', gpus[0].name)} cc={cc}", flush=True)
        except Exception:
            use_gpu = False
    if not use_gpu:
        try:
            tf.config.set_visible_devices([], "GPU")
        except Exception:
            pass
        print("  Running on CPU (float32)", flush=True)
        return False
    tf.keras.mixed_precision.set_global_policy("mixed_float16")
    print(f"  GPU: {len(gpus)} device(s); mixed_float16 enabled", flush=True)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--data-root", type=Path, default=_BACKEND_DIR / "data")
    parser.add_argument("--sources", default=None,
                        help="comma list (default: all real + pseudo_v2)")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--learning-rate", type=float, default=None)
    parser.add_argument("--label-smoothing", type=float, default=None)
    parser.add_argument("--bass-loss-weight", type=float, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--patience", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--limit-train", type=int, default=0)
    parser.add_argument("--limit-val-tracks", type=int, default=0)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "gpu"])
    parser.add_argument("--no-augment", action="store_true")
    args = parser.parse_args(argv)

    config = {
        "sources": ["guitarset", "guitar_techs", "egset12", "idmt_smt_guitar", "rwc", "pseudo_v2"],
        "epochs": 60,
        "batch_size": 64,
        "learning_rate": 1e-3,
        "weight_decay": 1e-4,
        "label_smoothing": 0.07,
        "bass_loss_weight": 0.35,
        "temperature": 0.3,
        "patience": 12,
        "seed": 1,
        "synthetic_epochs": 0,
    }
    config.update(load_config(args.config))
    for key, value in {
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "label_smoothing": args.label_smoothing,
        "bass_loss_weight": args.bass_loss_weight,
        "temperature": args.temperature,
        "patience": args.patience,
        "seed": args.seed,
    }.items():
        if value is not None:
            config[key] = value
    if args.sources:
        config["sources"] = [s.strip() for s in args.sources.split(",") if s.strip()]

    out_dir = args.out_dir or (
        _BACKEND_DIR / "runs" / "chord170" / time.strftime("run-%Y%m%d-%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading data (sources={config['sources']})", flush=True)
    train = load_split(args.data_root, config["sources"], "train",
                       limit_tracks=args.limit_train)
    val = load_split(args.data_root, config["sources"], "val",
                     limit_tracks=args.limit_val_tracks)
    if train is None or val is None:
        raise SystemExit("No train/val windows found — run the data prepare step first.")
    print(
        f"  train: {len(train['labels170'])} windows / {len(set(train['track_ids']))} tracks\n"
        f"  val  : {len(val['labels170'])} windows / {len(set(val['track_ids']))} tracks",
        flush=True,
    )

    tf.keras.utils.set_random_seed(int(config["seed"]))
    use_gpu = _configure_device(args.device)

    model = build_model()
    optimizer = tf.keras.optimizers.AdamW(
        learning_rate=tf.keras.optimizers.schedules.CosineDecay(
            initial_learning_rate=float(config["learning_rate"]),
            decay_steps=int(config["epochs"]) * max(
                1, int(np.ceil(len(train["labels170"]) / int(config["batch_size"])))
            ),
            alpha=0.01,
        ),
        weight_decay=float(config["weight_decay"]),
        clipnorm=1.0,
    )
    model.compile(
        optimizer=optimizer,
        loss={
            "chord_probs": tf.keras.losses.CategoricalCrossentropy(
                label_smoothing=float(config["label_smoothing"])
            ),
            "bass_probs": tf.keras.losses.CategoricalCrossentropy(),
        },
        loss_weights={"chord_probs": 1.0, "bass_probs": float(config["bass_loss_weight"])},
        metrics={
            "chord_probs": [tf.keras.metrics.CategoricalAccuracy(name="acc")],
            "bass_probs": [tf.keras.metrics.CategoricalAccuracy(name="acc")],
        },
    )

    probabilities = sampling_probabilities(
        train["labels170"], train["sources"], temperature=float(config["temperature"])
    )
    sequence = ChordSequence(
        train["features"], train["labels170"], train["bass_labels"], probabilities,
        batch_size=int(config["batch_size"]), seed=int(config["seed"]),
        augment=not args.no_augment,
    )
    n_train_sample = min(512, len(train["labels170"]))
    callback = ValidationCheckpoint(
        val, out_dir, patience=int(config["patience"]),
        batch_size=max(256, int(config["batch_size"])),
        train_sample={
            "features": train["features"][:n_train_sample],
            "labels170": train["labels170"][:n_train_sample],
        },
    )

    (out_dir / "config.json").write_text(json.dumps({
        **config,
        "git_sha": _git_sha(),
        "tf_version": tf.__version__,
        "n_train_windows": int(len(train["labels170"])),
        "n_val_windows": int(len(val["labels170"])),
        "train_sources": {str(k): int(v) for k, v in
                          zip(*np.unique(train["sources"], return_counts=True))},
        "val_sources": {str(k): int(v) for k, v in
                        zip(*np.unique(val["sources"], return_counts=True))},
    }, indent=2))

    history = model.fit(
        sequence,
        epochs=int(config["epochs"]),
        callbacks=[callback],
        verbose=2,
    )
    model.save(out_dir / "final.keras")
    (out_dir / "history.json").write_text(json.dumps(
        {k: [float(x) for x in v] for k, v in history.history.items()}, indent=2))
    print(f"Training complete. Artifacts in {out_dir}", flush=True)
    if callback.best_metric > -np.inf:
        print(f"Best val WCSR-MIREX={callback.best_metric:.4f} "
              f"(epoch {callback.best_epoch})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
