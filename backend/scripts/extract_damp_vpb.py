"""Extract CQT features from DAMP-VPB dataset with heuristic chord labels.

DAMP-VPB provides CREPE-based f0 pitch tracks. This script:
1. Groups pitch tracks into 50ms analysis frames
2. Converts f0 → pitch class → histogram
3. Matches histogram to chord vocabulary
4. Only accepts frames where heuristic confidence > 0.9
5. Extracts 36-bin CQT features matching the training pipeline

Usage:
    python scripts/extract_damp_vpb.py [--data-dir DATA_DIR] [--force]

Output:
    Per-song .npz files in <data_dir>/damp_vpb/processed/cqt/ containing:
        features: (T, 128, 40) — overlapping CQT windows
        labels: (T,) — chord class indices
        frame_times: (T,)
        confidence: (T,) — heuristic match confidence
        source: str — always "damp"
        loss_weight: float — per-source loss weight (0.15 default)
"""

from __future__ import annotations

import csv
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import (
    ROOT_NOTES, CHORD_INTERVALS, CHORD_TO_IDX,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "damp_vpb" / "raw"
OUTPUT_DIR = DATA_DIR / "damp_vpb" / "processed" / "cqt"

# CQT extraction constants (matching chord_inference.py)
TARGET_SR = 44100
HOP_SEC = 0.1
BINS_PER_OCTAVE = 12
NUM_OCTAVES = 3
CHROMA_BINS = BINS_PER_OCTAVE * NUM_OCTAVES  # 36
BASS_BINS = 4
FEATURE_DIM = CHROMA_BINS + BASS_BINS  # 40
WINDOW = 128
HOP_FRAMES = 64  # 50% overlap

N_CHORD_IDX = CHORD_TO_IDX.get("N", CHROMA_BINS * BASS_BINS - 1)

# Analysis frame duration for pitch-to-chord grouping
ANALYSIS_FRAME_SEC = 0.05  # 50ms

# Per-source loss weight for DAMP data (noisy labels → lower weight)
DAMP_LOSS_WEIGHT = 0.15


def _freq_to_pitch_class(freq_hz: float) -> int | None:
    """Convert frequency in Hz to pitch class (0=C, 1=C#, ..., 11=B).

    Returns None for unvoiced or out-of-range frequencies.
    """
    if freq_hz <= 0 or not np.isfinite(freq_hz):
        return None
    # MIDI note number
    midi = 12 * np.log2(freq_hz / 440.0) + 69
    if midi < 20 or midi > 108:  # Below E0 or above C8 — not guitar range
        return None
    return int(round(midi)) % 12


def _build_pc_histogram(
    pitch_classes: list[int],
    n_bins: int = 12,
) -> np.ndarray:
    """Build pitch class histogram from a list of pitch class values.

    Returns normalized histogram (sums to 1).
    """
    histogram = np.zeros(n_bins, dtype=np.float64)
    for pc in pitch_classes:
        if pc is not None:
            histogram[pc] += 1.0
    total = histogram.sum()
    if total > 0:
        histogram = histogram / total
    return histogram


def _match_chord_from_histogram(
    histogram: np.ndarray,
    confidence_threshold: float = 0.9,
) -> tuple[str | None, float]:
    """Match a pitch class histogram to the closest chord in vocabulary.

    Strategy:
    1. For each chord in vocabulary, compute expected pitch class template
    2. Compute cosine similarity between histogram and each template
    3. Return best match with confidence

    Confidence = best_similarity / (best_similarity + second_best_similarity)
    which gives a well-calibrated score in [0.5, 1.0].

    Args:
        histogram: (12,) pitch class histogram
        confidence_threshold: Minimum confidence to accept match

    Returns:
        (chord_label, confidence) tuple, or (None, 0) if below threshold.
    """
    best_score = 0.0
    best_chord: str | None = None
    second_best_score = 0.0

    for chord_name, chord_idx in CHORD_TO_IDX.items():
        if chord_name == "N":
            continue

        # Build template for this chord
        parts = chord_name.split(":")
        if len(parts) != 2:
            continue
        root_str, quality = parts
        if root_str not in ROOT_NOTES or quality not in CHORD_INTERVALS:
            continue

        root = ROOT_NOTES.index(root_str)
        intervals = CHORD_INTERVALS[quality]

        # Create binary template (which pitch classes are in this chord)
        template = np.zeros(12, dtype=np.float64)
        for interval in intervals:
            pc = (root + interval) % 12
            template[pc] = 1.0
        template = template / template.sum()

        # Cosine similarity
        dot = np.dot(histogram, template)
        norm = np.linalg.norm(histogram) * np.linalg.norm(template)
        score = dot / (norm + 1e-10)

        if score > best_score:
            second_best_score = best_score
            best_score = score
            best_chord = chord_name
        elif score > second_best_score:
            second_best_score = score

    # Confidence: how much better is best vs second best
    confidence = best_score / (best_score + second_best_score + 1e-10)

    if confidence >= confidence_threshold and best_chord is not None:
        return best_chord, float(confidence)
    return None, 0.0


def parse_pitch_file(pitch_path: Path) -> np.ndarray:
    """Parse a DAMP pitch annotation file.

    Expected format: CSV with columns [time_seconds, frequency_hz, ...]
    or F0 file with [time, freq] pairs.

    Returns array of (time_seconds, frequency_hz) pairs.
    """
    pitch_data: list[tuple[float, float]] = []

    try:
        with open(pitch_path) as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 2:
                    continue
                try:
                    t = float(row[0].strip())
                    freq = float(row[1].strip())
                    if freq > 0 and np.isfinite(freq):
                        pitch_data.append((t, freq))
                except (ValueError, IndexError):
                    continue
    except Exception as e:
        print(f"  [WARN] Could not parse {pitch_path.name}: {e}")
        return np.array([])

    return np.array(pitch_data, dtype=np.float64)


def group_pitch_to_frames(
    pitch_data: np.ndarray,
    frame_duration: float = ANALYSIS_FRAME_SEC,
) -> list[float]:
    """Group pitch data into analysis frames and compute chord labels.

    Returns list of chord indices (or N_CHORD_IDX for unlabeled frames).
    """
    if len(pitch_data) == 0:
        return []

    times = pitch_data[:, 0]
    freqs = pitch_data[:, 1]
    max_time = times[-1]
    n_frames = max(1, int(np.ceil(max_time / frame_duration)))

    chord_indices: list[int] = []
    for frame_idx in range(n_frames):
        start_t = frame_idx * frame_duration
        end_t = start_t + frame_duration

        # Get pitches in this frame
        mask = (times >= start_t) & (times < end_t)
        frame_freqs = freqs[mask]

        if len(frame_freqs) < 3:  # Too few data points
            chord_indices.append(N_CHORD_IDX)
            continue

        # Convert to pitch classes
        pcs = [_freq_to_pitch_class(f) for f in frame_freqs]
        pcs = [pc for pc in pcs if pc is not None]

        if len(pcs) < 3:
            chord_indices.append(N_CHORD_IDX)
            continue

        # Build histogram
        histogram = _build_pc_histogram(pcs)

        # Match to chord
        chord_label, confidence = _match_chord_from_histogram(
            histogram, confidence_threshold=0.9
        )

        if chord_label is not None and confidence >= 0.9:
            chord_idx = CHORD_TO_IDX.get(chord_label, N_CHORD_IDX)
        else:
            chord_idx = N_CHORD_IDX

        chord_indices.append(chord_idx)

    return chord_indices


def extract_cqt(y: np.ndarray, sr: int) -> np.ndarray:
    """Compute 36-bin CQT + 4-bin bass features."""
    import librosa

    hop = int(sr * HOP_SEC)
    cqt = librosa.cqt(y=y, sr=sr, hop_length=hop, n_bins=CHROMA_BINS,
                      bins_per_octave=BINS_PER_OCTAVE)
    cqt = np.abs(cqt).T.astype(np.float32)
    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    cqt = cqt / norms
    bass = cqt[:, :BASS_BINS]
    features = np.concatenate([cqt, bass], axis=1)
    return features


def build_windows(
    features: np.ndarray, labels: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Build overlapping windows with center-frame labels."""
    num_frames = len(features)
    pad = np.zeros((WINDOW // 2, FEATURE_DIM), dtype=np.float32)
    padded = np.concatenate([pad, features, pad], axis=0)
    padded_labels = np.concatenate([
        np.full(WINDOW // 2, N_CHORD_IDX, dtype=np.int32),
        labels,
        np.full(WINDOW // 2, N_CHORD_IDX, dtype=np.int32),
    ])

    T_overlap = (num_frames + HOP_FRAMES - 1) // HOP_FRAMES
    windows = np.zeros((T_overlap, WINDOW, FEATURE_DIM), dtype=np.float32)
    window_labels = np.full(T_overlap, N_CHORD_IDX, dtype=np.int32)

    for k in range(T_overlap):
        start = k * HOP_FRAMES
        windows[k] = padded[start: start + WINDOW]
        center = start + WINDOW // 2
        if center < len(padded_labels):
            window_labels[k] = padded_labels[center]

    return windows, window_labels


def process_file(
    audio_path: Path,
    pitch_path: Path,
    output_dir: Path,
    force: bool = False,
) -> dict | None:
    """Process one DAMP audio + pitch pair.

    Returns metadata dict or None on failure.
    """
    import librosa

    stem = audio_path.stem
    out_path = output_dir / f"{stem}.npz"

    if not force and out_path.exists():
        return {"track_id": stem, "status": "cached"}

    # Parse pitch data
    pitch_data = parse_pitch_file(pitch_path)
    if len(pitch_data) < 10:
        return None

    # Group pitches into analysis frames → chord labels
    frame_chords = group_pitch_to_frames(pitch_data)
    if not frame_chords:
        return None

    # Load audio
    try:
        y, sr = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
    except Exception as e:
        print(f"  [WARN] Could not load {audio_path.name}: {e}")
        return None

    # Extract CQT
    features = extract_cqt(y, sr)
    num_cqt_frames = len(features)

    # Map analysis frame labels to CQT frame labels
    analysis_frames_per_cqt = max(1, int(HOP_SEC / ANALYSIS_FRAME_SEC))
    cqt_labels = np.full(num_cqt_frames, N_CHORD_IDX, dtype=np.int32)
    for i in range(num_cqt_frames):
        analysis_idx = min(
            len(frame_chords) - 1,
            int(i * analysis_frames_per_cqt),
        )
        if analysis_idx >= 0 and analysis_idx < len(frame_chords):
            cqt_labels[i] = frame_chords[analysis_idx]

    # Count labeled frames
    n_labeled = int((cqt_labels != N_CHORD_IDX).sum())
    labeled_ratio = n_labeled / max(1, num_cqt_frames)

    # Skip files with too few labeled frames
    if labeled_ratio < 0.1:
        return None

    # Build windows
    windows, window_labels = build_windows(features, cqt_labels)

    # Save
    output_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        features=windows,
        labels=window_labels,
        frame_times=np.arange(len(windows), dtype=np.float32) * HOP_FRAMES * HOP_SEC,
        track_id=stem,
        source="damp",
        loss_weight=DAMP_LOSS_WEIGHT,
        labeled_frames=n_labeled,
        total_frames=num_cqt_frames,
    )

    print(f"  {stem}: {len(windows)} windows, {n_labeled}/{num_cqt_frames} labeled "
          f"({labeled_ratio:.0%})")
    return {"track_id": stem, "windows": len(windows), "labeled": n_labeled}


def main(data_dir: Path, force: bool = False) -> None:
    raw_dir = data_dir / "damp_vpb" / "raw"
    output_dir = data_dir / "damp_vpb" / "processed" / "cqt"

    if not raw_dir.exists():
        print(f"DAMP raw directory not found: {raw_dir}")
        print("Run download_damp_vpb.py first")
        return

    # Find audio + pitch pairs
    audio_files = sorted(raw_dir.rglob("*.wav"))
    pitch_files = sorted(
        list(raw_dir.rglob("*.csv")) +
        list(raw_dir.rglob("*.f0")) +
        list(raw_dir.rglob("*.pitch"))
    )

    if not audio_files:
        print(f"No audio files found in {raw_dir}")
        return

    print(f"Found {len(audio_files)} audio files, {len(pitch_files)} pitch files")
    print(f"Output: {output_dir}")

    # Match audio to pitch files by stem
    pitch_by_stem: dict[str, Path] = {}
    for pf in pitch_files:
        pitch_by_stem[pf.stem] = pf

    results = []
    for af in audio_files:
        stem = af.stem
        pf = pitch_by_stem.get(stem)
        if pf is None:
            continue

        result = process_file(af, pf, output_dir, force=force)
        if result:
            results.append(result)

    total_labeled = sum(r.get("labeled", 0) for r in results if "labeled" in r)
    print(f"\nProcessed {len(results)}/{len(audio_files)} files")
    print(f"Total labeled frames: {total_labeled}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Extract CQT + heuristic chord labels from DAMP-VPB")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    parser.add_argument("--force", action="store_true",
                        help="Re-extract existing files")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
