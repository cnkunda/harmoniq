#!/usr/bin/env python3
"""Prepare retraining data from user corrections (Commit 110).

Consumes exported corrections (JSON or CSV) and generates augmented
training data for chord inference retraining. The output follows the
same format expected by build_chord_tflite.py.

Usage:
    cd backend && python scripts/prepare_retraining_data.py \
        --corrections-file corrections_export.json \
        --output-dir data/retraining \
        --augment

    Or aggregate corrections from all persisted jobs:
    cd backend && python scripts/prepare_retraining_data.py \
        --from-jobs \
        --output-dir data/retraining
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np

# Force TensorFlow backend and CPU mode before any TF imports
os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("harmoniq.prepare_retraining_data")

# ---------------------------------------------------------------------------
# Vocabulary (mirrors build_chord_tflite.py)
# ---------------------------------------------------------------------------

ROOT_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

CHORD_INTERVALS = {
    "maj":  [0, 4, 7],
    "min":  [0, 3, 7],
    "7":    [0, 4, 7, 10],
    "maj7": [0, 4, 7, 11],
    "min7": [0, 3, 7, 10],
    "9":    [0, 4, 7, 10, 14],
    "min9": [0, 3, 7, 10, 14],
    "maj9": [0, 4, 7, 11, 14],
    "11":   [0, 4, 7, 10, 14, 17],
    "13":   [0, 4, 7, 10, 14, 17, 21],
    "7#9":  [0, 4, 7, 10, 15],
    "7b9":  [0, 4, 7, 10, 13],
    "7#5":  [0, 4, 8, 10],
    "7b5":  [0, 4, 6, 10],
    "alt7": [0, 4, 6, 8, 10, 13, 15],
    "sus2":  [0, 2, 7],
    "sus4":  [0, 5, 7],
    "7sus4": [0, 5, 7, 10],
    "dim":   [0, 3, 6],
    "dim7":  [0, 3, 6, 9],
    "aug":   [0, 4, 8],
    "6":     [0, 4, 7, 9],
    "min6":  [0, 3, 7, 9],
}

# Flat list: (root_idx, quality) → chord_label
CHORD_CLASS_MAP = []
for qi, quality in enumerate(sorted(CHORD_INTERVALS.keys())):
    for ri, root in enumerate(ROOT_NOTES):
        CHORD_CLASS_MAP.append((ri, quality))

NUM_CLASSES = len(CHORD_CLASS_MAP)  # 276
NO_CHORD_IDX = NUM_CLASSES  # 277

# CQT params (matches build_chord_tflite.py)
HOP_LENGTH = 512
SR = 22050
N_BINS = 36
BINS_PER_OCTAVE = 12


def parse_chord_label(label: str) -> tuple[int, str] | None:
    """Parse 'Gmaj7' → (7, 'maj7'). Returns None on failure."""
    label = label.strip()
    if not label or label.lower() in ("nc", "n chord", "none", ""):
        return None
    # Extract root
    root_str = ""
    rest = label
    if len(label) >= 2 and label[1] in ("#", "b"):
        root_str = label[:2]
        rest = label[2:]
    else:
        root_str = label[0]
        rest = label[1:]

    # Handle flats
    if "b" in root_str:
        flat_map = {"Cb": 11, "Db": 1, "Eb": 3, "Fb": 4, "Gb": 6, "Ab": 8, "Bb": 10}
        root_idx = flat_map.get(root_str, -1)
    else:
        root_idx = ROOT_NOTES.index(root_str) if root_str in ROOT_NOTES else -1

    if root_idx < 0:
        return None

    quality = rest if rest else "maj"
    # Normalize quality aliases
    quality_map = {"m": "min", "minor": "min", "major": "maj", "dom": "7", "dom7": "7"}
    quality = quality_map.get(quality, quality)

    if quality not in CHORD_INTERVALS:
        return None

    return (root_idx, quality)


def chord_to_class_index(root_idx: int, quality: str) -> int:
    """Map (root_idx, quality) to flat class index."""
    for i, (ri, q) in enumerate(CHORD_CLASS_MAP):
        if ri == root_idx and q == quality:
            return i
    return NO_CHORD_IDX


def make_cqt_template(root_idx: int, quality: str) -> np.ndarray:
    """Create a 36-bin CQT template for one chord."""
    intervals = CHORD_INTERVALS.get(quality, [0])
    template = np.zeros(N_BINS, dtype=np.float32)
    for interval in intervals:
        pc = (root_idx + interval) % 12
        bin_idx = int(pc * (N_BINS / 12))
        bin_idx = min(bin_idx, N_BINS - 1)
        template[bin_idx] = 1.0
    # Normalize
    norm = np.linalg.norm(template)
    if norm > 0:
        template /= norm
    return template


def augment_chord_template(
    template: np.ndarray,
    rng: np.random.RandomState,
    pitch_shift_range: int = 2,
    dropout_rate: float = 0.15,
) -> np.ndarray:
    """Apply augmentation to a chord CQT template."""
    augmented = template.copy()

    # Pitch shift
    shift = rng.randint(-pitch_shift_range, pitch_shift_range + 1)
    if shift != 0:
        augmented = np.roll(augmented, shift)

    # Missing note dropout
    mask = rng.random(N_BINS) > dropout_rate
    augmented *= mask

    # Normalize
    norm = np.linalg.norm(augmented)
    if norm > 0:
        augmented /= norm

    return augmented


def load_corrections_from_json(filepath: Path) -> list[dict]:
    """Load corrections from exported JSON file."""
    with open(filepath) as f:
        data = json.load(f)

    if isinstance(data, dict) and "data" in data:
        return data["data"] if isinstance(data["data"], list) else []
    if isinstance(data, list):
        return data
    return []


def load_corrections_from_csv(filepath: Path) -> list[dict]:
    """Load corrections from exported CSV file."""
    with open(filepath) as f:
        reader = csv.DictReader(f)
        return [row for row in reader]


def load_corrections_from_jobs(data_dir: Path) -> list[dict]:
    """Aggregate corrections from all persisted jobs."""
    jobs_dir = data_dir / "jobs"
    if not jobs_dir.exists():
        logger.warning("No jobs directory at %s", jobs_dir)
        return []

    all_corrections = []
    for job_dir in jobs_dir.iterdir():
        if not job_dir.is_dir():
            continue
        corrections_path = job_dir / "corrections.json"
        if corrections_path.exists():
            try:
                with open(corrections_path) as f:
                    corrections = json.load(f)
                if isinstance(corrections, list):
                    for c in corrections:
                        c["_job_id"] = job_dir.name
                    all_corrections.extend(corrections)
            except Exception as e:
                logger.warning("Failed to load corrections from %s: %s", job_dir.name, e)

    logger.info("Loaded %d corrections from %d jobs", len(all_corrections), len(list(jobs_dir.iterdir())))
    return all_corrections


def corrections_to_training_data(
    corrections: list[dict],
    augment: bool = True,
    augment_factor: int = 5,
) -> tuple[list[np.ndarray], list[int]]:
    """Convert chord corrections to (features, labels) training pairs.

    Only chord corrections produce training data for chord inference.
    Solo note and voicing corrections are logged but skipped for now.
    """
    X: list[np.ndarray] = []
    y: list[int] = []
    rng = np.random.RandomState(42)

    skipped = 0
    for c in corrections:
        ctype = c.get("correction_type", "")
        if ctype != "chord":
            skipped += 1
            continue

        corrected = c.get("corrected_value", {})
        chord_label = corrected.get("chord", "")
        parsed = parse_chord_label(str(chord_label))
        if parsed is None:
            logger.debug("Skipping unparseable chord label: %s", chord_label)
            skipped += 1
            continue

        root_idx, quality = parsed
        class_idx = chord_to_class_index(root_idx, quality)
        template = make_cqt_template(root_idx, quality)

        # Original template (negative example — what the model got wrong)
        original = c.get("original_value", {})
        orig_label = original.get("chord", "")
        orig_parsed = parse_chord_label(str(orig_label))
        if orig_parsed is not None:
            orig_root, orig_quality = orig_parsed
            orig_template = make_cqt_template(orig_root, orig_quality)
            X.append(orig_template)
            y.append(chord_to_class_index(orig_root, orig_quality))

        # Corrected template (positive example)
        X.append(template)
        y.append(class_idx)

        # Augmented copies of the corrected template
        if augment:
            for _ in range(augment_factor):
                aug = augment_chord_template(template, rng)
                X.append(aug)
                y.append(class_idx)

    logger.info(
        "Converted %d chord corrections → %d samples (skipped %d non-chord)",
        len(corrections) - skipped,
        len(X),
        skipped,
    )
    return X, y


def save_training_data(
    X: list[np.ndarray],
    y: list[int],
    output_dir: Path,
) -> None:
    """Save training data as numpy arrays (compatible with build_chord_tflite)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    X_arr = np.array(X, dtype=np.float32)
    y_arr = np.array(y, dtype=np.int32)

    np.save(output_dir / "retraining_X.npy", X_arr)
    np.save(output_dir / "retraining_y.npy", y_arr)

    # Also save metadata
    metadata = {
        "num_samples": len(X),
        "num_classes": NUM_CLASSES,
        "feature_dim": N_BINS,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "user_corrections",
    }
    with open(output_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Saved %d samples to %s", len(X), output_dir)
    logger.info("  X shape: %s, y shape: %s", X_arr.shape, y_arr.shape)


def print_class_distribution(y: list[int]) -> None:
    """Print class distribution summary."""
    from collections import Counter
    counts = Counter(y)
    total = len(y)
    logger.info("Class distribution (%d samples, %d unique classes):", total, len(counts))
    for idx, count in sorted(counts.items(), key=lambda x: -x[1])[:10]:
        if idx < NUM_CLASSES:
            root, quality = CHORD_CLASS_MAP[idx]
            label = f"{ROOT_NOTES[root]}{quality}"
        else:
            label = "NC"
        logger.info("  %s: %d (%.1f%%)", label, count, 100 * count / total)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare retraining data from user corrections")
    parser.add_argument("--corrections-file", type=str, help="Path to exported corrections (JSON or CSV)")
    parser.add_argument("--from-jobs", action="store_true", help="Aggregate corrections from all persisted jobs")
    parser.add_argument("--data-dir", type=str, default="data", help="Data directory for --from-jobs mode")
    parser.add_argument("--output-dir", type=str, default="data/retraining", help="Output directory")
    parser.add_argument("--augment", action="store_true", help="Apply data augmentation")
    parser.add_argument("--augment-factor", type=int, default=5, help="Augmentation copies per sample")
    args = parser.parse_args()

    if not args.corrections_file and not args.from_jobs:
        parser.error("Either --corrections-file or --from-jobs is required")

    # Load corrections
    if args.corrections_file:
        filepath = Path(args.corrections_file)
        if not filepath.exists():
            logger.error("File not found: %s", filepath)
            sys.exit(1)
        if filepath.suffix == ".csv":
            corrections = load_corrections_from_csv(filepath)
        else:
            corrections = load_corrections_from_json(filepath)
    else:
        data_dir = Path(args.data_dir)
        corrections = load_corrections_from_jobs(data_dir)

    if not corrections:
        logger.warning("No corrections found. Nothing to do.")
        sys.exit(0)

    logger.info("Loaded %d total corrections", len(corrections))

    # Convert to training data
    X, y = corrections_to_training_data(
        corrections,
        augment=args.augment,
        augment_factor=args.augment_factor,
    )

    if not X:
        logger.warning("No training samples generated (no chord corrections found).")
        sys.exit(0)

    # Print distribution
    print_class_distribution(y)

    # Save
    output_dir = Path(args.output_dir)
    save_training_data(X, y, output_dir)


if __name__ == "__main__":
    main()
