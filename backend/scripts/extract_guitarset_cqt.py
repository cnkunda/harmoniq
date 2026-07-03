"""Extract CQT features from GuitarSet audio aligned with chord labels.

Reads mono-pickup-mix WAVs and per-song JSON timelines (from parse_guitarset.py),
aligns 144-bin CQT features with chord labels at 0.1s frame resolution.

Usage:
    python scripts/extract_guitarset_cqt.py [--data-dir DATA_DIR] [--force]

Output:
    Per-song .npz files in <data_dir>/guitarset/processed/cqt/ containing:
        features: (T, 128, 40) — overlapping CQT windows
        labels:   (T,) — chord class indices matching center frame of each window
        frame_times: (T,) — center time of each window
        track_id: str
        player_id: str
        split: str  — 'train', 'val', or 'test' (by player)

Train/val/test split (by player, no artist overlap):
    Train: players 00, 01, 02, 03
    Val:   player 04
    Test:  player 05
"""

import json
from pathlib import Path
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_TO_IDX, ROOT_NOTES, NUM_CLASSES

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "guitarset" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "guitarset" / "processed"

# Inference pipeline constants (must match chord_inference.py)
from app.cqt_constants import (TARGET_SR, HOP_SEC, BINS_PER_OCTAVE, NUM_OCTAVES,
                                CHROMA_BINS, BASS_BINS, FEATURE_DIM, WINDOW, HOP_FRAMES)

N_CHORD_IDX = CHORD_TO_IDX.get("N", NUM_CLASSES - 1)

# Player split (no artist overlap)
PLAYER_SPLIT = {
    "00": "train", "01": "train", "02": "train", "03": "train",
    "04": "val",
    "05": "test",
}


def _extract_cqt(y: np.ndarray, sr: int) -> np.ndarray:
    """Compute 144-bin CQT features matching chord_inference.py exactly."""
    import librosa

    hop = int(sr * HOP_SEC)
    cqt = librosa.cqt(y=y, sr=sr, hop_length=hop, n_bins=CHROMA_BINS,
                      bins_per_octave=BINS_PER_OCTAVE)
    cqt = np.abs(cqt)
    cqt = cqt.T.astype(np.float32)

    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    features = cqt / norms
    return features


def _frame_labels_from_timeline(timeline: list[dict], num_frames: int) -> np.ndarray:
    """Assign a chord label to each CQT frame by finding the chord covering that frame's time.

    Uses forward-biased boundary handling: a frame is labeled with whichever
    chord occupies >50% of the frame's time span. Ties (50/50) are assigned
    to the NEW chord (forward bias) to capture transients.

    Args:
        timeline: List of {start, end, chord} dicts from parse_guitarset.py
        num_frames: Number of 0.1s CQT frames

    Returns:
        Array of shape (num_frames,) with chord class indices.
    """
    labels = np.full(num_frames, N_CHORD_IDX, dtype=np.int32)

    for entry in timeline:
        start_t = entry["start"]
        end_t = entry["end"]
        chord = entry["chord"]

        chord_idx = CHORD_TO_IDX.get(chord, N_CHORD_IDX)

        # Frame indices covering this chord
        frame_start = int(start_t / HOP_SEC)
        frame_end = int(end_t / HOP_SEC)

        for f in range(frame_start, min(frame_end, num_frames)):
            frame_t = f * HOP_SEC
            frame_end_t = frame_t + HOP_SEC

            # Compute overlap
            overlap_start = max(frame_t, start_t)
            overlap_end = min(frame_end_t, end_t)
            overlap = max(0, overlap_end - overlap_start)
            frame_dur = HOP_SEC

            if overlap >= frame_dur * 0.5:
                labels[f] = chord_idx

    return labels


def _build_windows(features: np.ndarray,
                   frame_labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Build overlapping windows with center-frame labels.

    Each window is labeled by the chord at its CENTER frame (index WINDOW//2),
    matching the triangular inference weighting.

    Returns:
        (windows, labels) arrays.
    """
    T = len(features)
    pad = np.zeros((WINDOW // 2, FEATURE_DIM), dtype=np.float32)
    padded = np.concatenate([pad, features, pad], axis=0)
    padded_labels = np.concatenate([
        np.full(WINDOW // 2, N_CHORD_IDX, dtype=np.int32),
        frame_labels,
        np.full(WINDOW // 2, N_CHORD_IDX, dtype=np.int32),
    ])

    T_overlap = (T + HOP_FRAMES - 1) // HOP_FRAMES
    windows = np.zeros((T_overlap, WINDOW, FEATURE_DIM), dtype=np.float32)
    window_labels = np.full(T_overlap, N_CHORD_IDX, dtype=np.int32)

    for k in range(T_overlap):
        start = k * HOP_FRAMES
        windows[k] = padded[start: start + WINDOW]
        # Label = chord at center of window
        center = start + WINDOW // 2
        if center < len(padded_labels):
            window_labels[k] = padded_labels[center]

    return windows, window_labels


def process_song(audio_path: Path, timeline_path: Path, output_dir: Path,
                 force: bool = False) -> dict | None:
    """Process a single GuitarSet song: load audio, extract CQT, align labels.

    Returns:
        Dict with track metadata, or None if processing fails.
    """
    track_id = audio_path.stem

    # Load timeline
    if not timeline_path.exists():
        print(f"  [WARN] No timeline for {track_id}, skipping")
        return None

    # Check for existing output
    out_path = output_dir / f"{track_id}.npz"
    if out_path.exists() and not force:
        return {"track_id": track_id, "status": "cached", "path": str(out_path)}

    with open(timeline_path, "r") as f:
        timeline = json.load(f)

    if not timeline:
        print(f"  [WARN] Empty timeline for {track_id}, skipping")
        return None

    # Load audio
    import librosa
    try:
        y, sr = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
    except Exception as e:
        print(f"  [WARN] Could not load {audio_path}: {e}")
        return None

    # Extract CQT features
    features = _extract_cqt(y, sr)
    num_frames = len(features)

    # Frame-level labels
    frame_labels = _frame_labels_from_timeline(timeline, num_frames)

    # Build windows with center-frame labels
    windows, window_labels = _build_windows(features, frame_labels)

    # Player and split
    player_id = track_id.split("_")[0]
    split = PLAYER_SPLIT.get(player_id, "train")

    # Save
    output_dir.mkdir(parents=True, exist_ok=True)
    frame_times = np.arange(len(frame_labels), dtype=np.float32) * HOP_SEC
    np.savez_compressed(
        out_path,
        features=windows,
        labels=window_labels,
        frame_times=np.arange(len(window_labels), dtype=np.float32) * HOP_FRAMES * HOP_SEC,
        track_id=track_id,
        player_id=player_id,
        split=split,
        loss_weight=1.0,
    )

    chord_labels = window_labels[window_labels != N_CHORD_IDX]
    print(f"  {track_id}: {len(windows)} windows, "
          f"{len(chord_labels)}/{len(window_labels)} labeled frames, "
          f"split={split}")

    return {"track_id": track_id, "status": "processed", "path": str(out_path),
            "split": split, "num_windows": len(windows)}


def main(data_dir: Path, force: bool = False) -> None:
    raw = data_dir / "guitarset" / "raw"
    proc = data_dir / "guitarset" / "processed"

    audio_dir = raw / "audio_mono-mix"
    timeline_dir = proc / "timelines"
    cqt_dir = proc / "cqt"

    if not audio_dir.exists() or not timeline_dir.exists():
        print(f"Required directories not found.")
        print(f"  Audio: {audio_dir} {'✓' if audio_dir.exists() else '✗'}")
        print(f"  Timelines: {timeline_dir} {'✓' if timeline_dir.exists() else '✗'}")
        print("Run download_guitarset.py and parse_guitarset.py first.")
        return

    # Find all WAVs
    wavs = sorted(audio_dir.rglob("*.wav"))
    if not wavs:
        print(f"No WAV files found in {audio_dir}")
        return

    print(f"Found {len(wavs)} audio files, extracting CQT features...")

    # Filter to tracks that have timelines (strip _mix suffix from audio filenames)
    results = []
    for wav in wavs:
        track_id = wav.stem
        tl_stem = track_id.replace("_mix", "")
        tl_path = timeline_dir / f"{tl_stem}.json"
        result = process_song(wav, tl_path, cqt_dir, force=force)
        if result:
            results.append(result)

    # Summary
    by_split: Counter = Counter()
    total_windows = 0
    for r in results:
        if r["status"] == "processed":
            by_split[r.get("split", "unknown")] += 1
            total_windows += r.get("num_windows", 0)

    print(f"\nProcessing complete.")
    print(f"  Songs processed: {sum(by_split.values())} / {len(results)} total")
    print(f"  Train: {by_split.get('train', 0)}, Val: {by_split.get('val', 0)}, Test: {by_split.get('test', 0)}")
    print(f"  Total training windows: {total_windows}")
    print(f"  Output: {cqt_dir}/")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract GuitarSet CQT features")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent.parent / "data",
                        help="Data directory root")
    parser.add_argument("--force", action="store_true", help="Re-extract existing files")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
