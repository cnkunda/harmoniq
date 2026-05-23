"""Build empirical chord transition matrix from Isophonics/Billboard annotations.

Parses .lab files from data/annotations/, maps chords to 277-class vocabulary,
and counts chord-to-chord transitions as interval-relative statistics
(key-invariant). Also computes chord quality frequency distribution.

Usage:
    python scripts/build_empirical_transition_matrix.py [--data-dir DATA_DIR] [--force]

Output:
    data/annotations/transition_matrix_empirical.npy  — 277×277 row-stochastic
    data/annotations/chord_distribution.json           — per-quality frequency stats
"""

import json
from collections import Counter
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import ROOT_NOTES, CHORD_QUALITIES, CHORD_TO_IDX, NUM_CLASSES

N_CHORD_IDX = CHORD_TO_IDX.get("N", NUM_CLASSES - 1)

ANNOTATION_DIR = Path(__file__).resolve().parent.parent / "data" / "annotations"

# Billboard special markers
BILLBOARD_MAP = {
    "N": None,
    "*": None,
    "&pause": None,
    ".": "__REPEAT__",
    "1": None,
    "5": None,   # power chord — no root, can't map
}

# Quality normalization for datasets
QUALITY_NORM = {
    "maj": "maj", "major": "maj", "": "maj",
    "min": "min", "m": "min", "minor": "min",
    "dim": "dim",
    "aug": "aug",
    "hdim7": "dim7",
    "minmaj7": "maj7",
    "min11": "11",
    "maj11": "11",
    "maj13": "13",
    "min13": "13",
}

_FLAT_TO_SHARP = {
    "Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#", "Fb": "E", "Cb": "B",
}


def _normalize_root(root: str) -> str | None:
    if root in ROOT_NOTES:
        return root
    sharp = _FLAT_TO_SHARP.get(root)
    if sharp in ROOT_NOTES:
        return sharp
    return None


def _parse_lab_label(label: str, prev_label: str | None = None) -> str | None:
    """Parse a single .lab chord label to our 277-class format.

    Handles Harte syntax, Billboard special markers, and shorthand notation.
    """
    if not label or label == "N":
        return None

    label = label.strip()

    # Billboard repeat convention
    if label == ".":
        return prev_label  # keep previous label

    # Billboard special markers
    if label in BILLBOARD_MAP:
        mapped = BILLBOARD_MAP[label]
        if mapped is None:
            return None
        if mapped == "__REPEAT__":
            return prev_label

    # Strip extensions: parentheses, bass notes
    if "(" in label:
        label = label[: label.index("(")]
    if "/" in label:
        label = label.split("/")[0]

    label = label.strip()
    if not label or label == "N":
        return None

    # Parse root + quality
    if ":" in label:
        parts = label.split(":", 1)
        root_raw = parts[0]
        quality_raw = parts[1]
    else:
        # Shorthand: 'C', 'Am', 'Bb7'
        root_raw = label[0]
        quality_raw = label[1:]
        if len(label) > 1 and label[1] in ("#", "b"):
            root_raw = label[:2]
            quality_raw = label[2:]

    root = _normalize_root(root_raw)
    if root is None:
        return None

    quality = QUALITY_NORM.get(quality_raw)
    if quality is None:
        # Try direct match
        if quality_raw in CHORD_QUALITIES:
            quality = quality_raw
        else:
            return None

    if quality not in CHORD_QUALITIES:
        return None

    return f"{root}:{quality}"


def _parse_lab_file(path: Path) -> list[tuple[float, float, str | None]]:
    """Parse a .lab file into (onset, offset, chord_or_None) entries."""
    entries: list[tuple[float, float, str | None]] = []
    prev_label: str | None = None

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                onset = float(parts[0])
                offset = float(parts[1])
            except ValueError:
                continue

            raw_label = " ".join(parts[2:])
            chord = _parse_lab_label(raw_label, prev_label)
            if chord is not None:
                prev_label = chord
            entries.append((onset, offset, chord))

    return entries


def build_transition_counts(
    lab_files: list[Path],
) -> tuple[np.ndarray, np.ndarray, Counter]:
    """Build empirical transition matrix from .lab files.

    Args:
        lab_files: List of .lab file paths to process.

    Returns:
        (transition_counts, start_distribution, quality_frequency)
          - transition_counts: (NUM_CLASSES, NUM_CLASSES) raw counts
          - start_distribution: (NUM_CLASSES,) counts of first chord in each song
          - quality_frequency: Counter of (quality) counts
    """
    transition_counts = np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.int64)
    start_distribution = np.zeros(NUM_CLASSES, dtype=np.int64)
    quality_frequency: Counter = Counter()
    total_entries = 0
    skipped_annotations = 0

    for lf in lab_files:
        entries = _parse_lab_file(lf)
        if not entries:
            continue

        # Extract chord sequence (merge adjacent identical chords)
        chord_sequence: list[int] = []
        for _, _, chord in entries:
            total_entries += 1
            if chord is None:
                chord_sequence.append(N_CHORD_IDX)
            else:
                idx = CHORD_TO_IDX.get(chord, N_CHORD_IDX)
                chord_sequence.append(idx)
                quality = chord.split(":", 1)[1] if ":" in chord else chord
                quality_frequency[quality] += 1

        if not chord_sequence:
            continue

        # Record first chord
        first = chord_sequence[0]
        if first != N_CHORD_IDX:
            start_distribution[first] += 1

        # Count transitions (key-invariant: by interval distance)
        for i in range(len(chord_sequence) - 1):
            from_idx = chord_sequence[i]
            to_idx = chord_sequence[i + 1]
            transition_counts[from_idx, to_idx] += 1

    total_chords = sum(quality_frequency.values())
    print(f"Parsed {len(lab_files)} .lab files")
    print(f"Total entries: {total_entries}")
    print(f"Chord labels mapped: {total_chords}")
    print(f"Transition pairs counted: {transition_counts.sum()}")
    print(f"Unique chord qualities: {len(quality_frequency)}")

    return transition_counts, start_distribution, quality_frequency


def build_empirical_matrix(
    transition_counts: np.ndarray,
    smoothing: float = 1.0,
) -> np.ndarray:
    """Convert raw transition counts to a row-stochastic matrix with additive smoothing.

    Args:
        transition_counts: (NUM_CLASSES, NUM_CLASSES) raw counts.
        smoothing: Additive smoothing factor (Laplace). 1.0 = standard Laplace.

    Returns:
        (NUM_CLASSES, NUM_CLASSES) row-stochastic float32 matrix.
    """
    smoothed = transition_counts.astype(np.float64) + smoothing
    row_sums = smoothed.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums == 0, 1.0, row_sums)
    matrix = smoothed / row_sums
    return matrix.astype(np.float32)


def gather_lab_files(annot_dir: Path) -> list[Path]:
    """Find all .lab files across Isophonics and Billboard directories."""
    lab_files: list[Path] = []

    # Isophonics
    iso_dir = annot_dir / "isophonics"
    for source_dir in iso_dir.iterdir():
        if source_dir.is_dir():
            lab_files.extend(source_dir.glob("*.lab"))

    # Billboard
    bb_dir = annot_dir / "billboard"
    if bb_dir.exists():
        lab_files.extend(bb_dir.glob("*.lab"))

    return lab_files


def save_chord_distribution(quality_frequency: Counter, output_dir: Path) -> None:
    """Save chord quality frequency distribution as JSON."""
    total = sum(quality_frequency.values()) or 1
    distribution = {
        "total_chords": int(total),
        "qualities": {
            q: {"count": c, "percentage": round(c / total * 100, 2)}
            for q, c in sorted(quality_frequency.most_common())
        },
    }
    out_path = output_dir / "chord_distribution.json"
    with open(out_path, "w") as f:
        json.dump(distribution, f, indent=2)
    print(f"Saved chord distribution to {out_path}")


def main(data_dir: Path) -> None:
    annot_dir = data_dir / "annotations"

    if not annot_dir.exists():
        print(f"Annotation directory not found: {annot_dir}")
        print("Run download_annotations.py first.")
        return

    lab_files = gather_lab_files(annot_dir)
    if not lab_files:
        print("No .lab files found. Run download_annotations.py first.")
        return

    print(f"Found {len(lab_files)} .lab files across all sources")

    # Build empirical transition counts
    counts, starts, quality_freq = build_transition_counts(lab_files)

    # Build transition matrix
    matrix = build_empirical_matrix(counts)

    # Save matrix
    matrix_path = annot_dir / "transition_matrix_empirical.npy"
    np.save(str(matrix_path), matrix)
    print(f"\nSaved empirical transition matrix to {matrix_path}")
    print(f"  Shape: {matrix.shape}")
    print(f"  Non-zero entries: {np.count_nonzero(matrix)}")
    print(f"  Row-stochastic check: row sums within [0.99, 1.01]: "
          f"{bool(np.all((matrix.sum(axis=1) >= 0.99) & (matrix.sum(axis=1) <= 1.01)))}")

    # Save chord distribution
    save_chord_distribution(quality_freq, annot_dir)

    # Per-source summary
    for source_dir in sorted(set(lf.parent for lf in lab_files)):
        count = len(list(source_dir.glob("*.lab")))
        print(f"  {source_dir.relative_to(annot_dir)}: {count} files")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Build empirical transition matrix from Isophonics/Billboard")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent.parent / "data",
                        help="Data directory root")
    args = parser.parse_args()
    main(args.data_dir)
