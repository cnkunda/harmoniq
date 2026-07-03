"""Pseudo-label bootstrapping for H-GAIN chord model (Commit 104b).

Narrows the synthetic-to-real domain gap by:
1. Loading the trained CRNN
2. Running inference on unlabeled real guitar audio
3. Filtering for high-confidence predictions
4. Saving pseudo-labeled data for hybrid retraining

Usage:
    python scripts/pseudo_label_pipeline.py \\
        --audio-dir data/unlabeled \\
        --model-path app/chord_model.keras \\
        --output data/pseudo_labels.npz \\
        --confidence 0.6

    python scripts/pseudo_label_pipeline.py \\
        --audio-dir data/unlabeled \\
        --retrain \\
        --real-data-dir data/guitarset
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WINDOW = 128
HOP_FRAMES = 64
from app.cqt_constants import CHROMA_BINS, BASS_BINS, FEATURE_DIM, BINS_PER_OCTAVE, TARGET_SR, HOP_SEC


def load_model(model_path: str | Path) -> object:
    """Load the CRNN chord model from a .keras file.

    The model was saved as a Keras 3 (.keras) file, so we load it
    with the standalone ``keras`` module (not ``tf.keras`` which routes
    to Keras 2 / tf_keras and cannot deserialize Keras 3 layer metadata).
    """
    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    # Must set backend before first keras import
    import os
    os.environ["KERAS_BACKEND"] = "tensorflow"
    import keras

    # Lazy import for the Lambda layer's function to avoid circular TF init
    from scripts.build_chord_tflite import _circular_cqt_pad

    model = keras.models.load_model(
        str(model_path),
        custom_objects={"_circular_cqt_pad": _circular_cqt_pad},
    )
    # Ensure the model runs in inference mode
    import tensorflow as tf
    _ = tf.constant(0)  # trigger TF init

    print(f"  [LOADED] {model_path.name}")
    return model


def extract_cqt_features(audio_path: Path) -> np.ndarray:
    """Extract CQT features and build sliding windows for inference.

    Returns:
        np.ndarray of shape (T_windows, WINDOW, FEATURE_DIM).
    """
    import librosa

    y, sr = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
    hop = int(TARGET_SR * HOP_SEC)

    cqt = librosa.cqt(y=y, sr=sr, hop_length=hop, n_bins=CHROMA_BINS, bins_per_octave=BINS_PER_OCTAVE)
    cqt = np.abs(cqt).T.astype(np.float32)

    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    features = cqt / norms

    # Build sliding windows with 50% overlap
    pad = np.zeros((WINDOW // 2, FEATURE_DIM), dtype=np.float32)
    padded = np.concatenate([pad, features, pad], axis=0)
    T = len(features)
    T_overlap = (T + HOP_FRAMES - 1) // HOP_FRAMES
    windows = np.zeros((T_overlap, WINDOW, FEATURE_DIM), dtype=np.float32)
    for k in range(T_overlap):
        start = k * HOP_FRAMES
        windows[k] = padded[start : start + WINDOW]

    return windows


def pseudo_label_audio(
    audio_path: Path,
    model: object,
    confidence_threshold: float = 0.6,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Run inference on one audio file and return confident pseudo-labels.

    Returns:
        (features, labels, retention_rate) where features are the raw sliding
        windows (not filtered) and labels contain -1 for low-confidence frames.
    """
    windows = extract_cqt_features(audio_path)
    if len(windows) == 0:
        return np.array([], dtype=np.float32), np.array([], dtype=np.int32), 0.0

    probs = model.predict(windows, verbose=0)
    max_probs = np.max(probs, axis=1)
    predictions = np.argmax(probs, axis=1).astype(np.int32)

    confident = max_probs >= confidence_threshold
    labels = np.where(confident, predictions, -1)

    retention = float(confident.mean())
    n_confident = int(confident.sum())
    print(f"  {audio_path.name}: {len(windows)} windows, "
          f"{n_confident} kept ({retention:.1%})")

    return windows, labels, retention


def scan_audio_directory(audio_dir: Path) -> list[Path]:
    """Recursively find audio files in a directory."""
    extensions = {".wav", ".mp3", ".flac", ".m4a", ".ogg"}
    files = sorted(
        p for p in audio_dir.rglob("*")
        if p.suffix.lower() in extensions
    )
    return files


def run_pseudo_label(
    model: object,
    audio_files: list[Path],
    confidence: float = 0.6,
) -> tuple[np.ndarray, np.ndarray]:
    """Pseudo-label all audio files and aggregate results."""
    all_windows: list[np.ndarray] = []
    all_labels: list[np.ndarray] = []
    total_retained = 0
    total_windows = 0

    for audio_path in audio_files:
        windows, labels, retention = pseudo_label_audio(
            audio_path, model, confidence
        )
        if len(windows) == 0:
            continue

        # Only keep confident frames
        mask = labels != -1
        kept = mask.sum()
        if kept > 0:
            all_windows.append(windows[mask])
            all_labels.append(labels[mask])

        total_windows += len(windows)
        total_retained += int(kept)

    if not all_windows:
        print("  No confident pseudo-labels found. Try lowering --confidence.")
        return np.array([], dtype=np.float32), np.array([], dtype=np.int32)

    X = np.concatenate(all_windows, axis=0).astype(np.float32)
    y = np.concatenate(all_labels, axis=0).astype(np.int32)

    print(f"\n  Pseudo-label summary: {total_retained}/{total_windows} frames "
          f"({total_retained / max(total_windows, 1):.1%})")
    print(f"  Unique chord classes: {len(np.unique(y))}")

    return X, y


def retrain_with_pseudo_labels(
    pseudo_X: np.ndarray,
    pseudo_y: np.ndarray,
    guitarset_data_dir: str | None = None,
    temperature: float = 0.3,
):
    """Retrain the chord model with mixed GuitarSet + pseudo-labeled data.

    Saves pseudo-labels to a temporary structured CQT directory and passes
    it to the multi-source training pipeline with loss_weight=vst_loss_weight
    (default 0.3, matching VST synthetic confidence level).
    """
    from scripts.build_chord_tflite import run_pipeline

    print(f"\n{'=' * 50}")
    print("Hybrid Retraining with Pseudo-Labels")
    print(f"  Pseudo-labeled frames: {len(pseudo_X)}")
    print(f"{'=' * 50}")

    # Save pseudo-labels to a temporary structured CQT directory
    import tempfile
    pseudo_dir = Path(tempfile.mkdtemp(prefix="pseudo_labels_"))
    cqt_dir = pseudo_dir / "processed" / "cqt"
    cqt_dir.mkdir(parents=True, exist_ok=True)
    pseudo_path = cqt_dir / "pseudo_labels.npz"
    np.savez_compressed(
        str(pseudo_path),
        features=pseudo_X,
        labels=pseudo_y,
        split=b"train",
        source=b"pseudo",
    )
    print(f"\n  Saved pseudo-labels to {pseudo_path}")

    # Run the full training pipeline with pseudo-labels as a dedicated source
    # (loss_weight is applied by run_pipeline via vst_loss_weight)
    run_pipeline(
        guitarset_data_dir=guitarset_data_dir,
        pseudo_data_dir=str(pseudo_dir),
        youtube_data_dir=None,
        damp_data_dir=None,
        vst_loss_weight=0.3,
        empirical_matrix_path=None,
        temperature=temperature,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pseudo-label unlabeled guitar audio for H-GAIN bootstrapping"
    )
    parser.add_argument(
        "--audio-dir", type=str, required=True,
        help="Directory containing unlabeled audio files (.wav, .mp3, .flac)"
    )
    parser.add_argument(
        "--model-path", type=str,
        default=str(Path(__file__).resolve().parent.parent / "app" / "chord_model.keras"),
        help="Path to trained .keras model (default: app/chord_model.keras)"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Save pseudo-labels to this .npz path"
    )
    parser.add_argument(
        "--confidence", type=float, default=0.6,
        help="Confidence threshold for label retention (default: 0.6)"
    )
    parser.add_argument(
        "--retrain", action="store_true",
        help="After pseudo-labeling, retrain with mixed real+pseudo data"
    )
    parser.add_argument(
        "--real-data-dir", type=str, default=None,
        help="Real GuitarSet data directory (for retraining)"
    )
    parser.add_argument(
        "--temperature", type=float, default=0.3,
        help="Temperature for quality resampling (default: 0.3)"
    )

    args = parser.parse_args(argv)

    # Load model
    print(f"\nPseudo-Label Pipeline")
    print(f"{'=' * 50}")
    print(f"  Model: {args.model_path}")
    print(f"  Audio: {args.audio_dir}")
    print(f"  Confidence threshold: {args.confidence}")
    model = load_model(args.model_path)

    # Scan audio directory
    audio_dir = Path(args.audio_dir)
    if not audio_dir.exists():
        print(f"  ERROR: Audio directory not found: {audio_dir}", file=sys.stderr)
        return 1

    audio_files = scan_audio_directory(audio_dir)
    if not audio_files:
        print(f"  ERROR: No audio files found in {audio_dir}", file=sys.stderr)
        return 1

    print(f"  Found {len(audio_files)} audio files")

    # Generate pseudo-labels
    print(f"\n[1/2] Generating pseudo-labels...")
    X, y = run_pseudo_label(model, audio_files, args.confidence)
    if len(X) == 0:
        print("  No pseudo-labels generated. Exiting.")
        return 1

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(str(output_path), features=X, labels=y)
        output_size = output_path.stat().st_size / 1024 / 1024
        print(f"\n  Saved {len(X)} pseudo-labeled windows to {output_path} ({output_size:.1f} MB)")

    # Retrain
    if args.retrain:
        print(f"\n[2/2] Hybrid retraining...")
        retrain_with_pseudo_labels(
            X, y,
            guitarset_data_dir=args.real_data_dir,
            temperature=args.temperature,
        )

    print(f"\n{'=' * 50}")
    print(f"DONE — {len(X)} pseudo-labeled windows from {len(audio_files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
