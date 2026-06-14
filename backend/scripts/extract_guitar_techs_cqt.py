"""Extract CQT features from Guitar-TECHS DI audio aligned with chord labels.

Reads DI (direct input) WAVs and per-track JSON timelines (from
parse_guitar_techs.py), aligns 36-bin CQT + 4-bin bass features with chord
labels at 0.1s frame resolution. Uses DI audio — the cleanest signal.

Only processes tracks that have chord-annotated segments (non-"N" labels).
Scales, techniques, and singlenotes are skipped since they lack chord content.

Usage:
    python scripts/extract_guitar_techs_cqt.py [--data-dir DATA_DIR] [--force]

Output:
    Per-track .npz files in <data_dir>/guitar_techs/processed/cqt/ containing:
        features:    (T, 128, 40) — overlapping CQT windows
        labels:      (T,) — chord class indices matching center frame
        frame_times: (T,) — center time of each window
        track_id:    str
        player:      str
        split:       str  — 'train' for P1/P2, 'val' for P3

Split by player (no artist overlap):
    Train: P1, P2
    Val:   P3 (musical excerpts)
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_TO_IDX

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "guitar_techs" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "guitar_techs" / "processed"

# Feature extraction constants (must match build_chord_tflite.py)
TARGET_SR = 44100
HOP_SEC = 0.1
BINS_PER_OCTAVE = 12
NUM_OCTAVES = 3
CHROMA_BINS = BINS_PER_OCTAVE * NUM_OCTAVES  # 36
BASS_BINS = 4
FEATURE_DIM = CHROMA_BINS + BASS_BINS  # 40
WINDOW = 128
HOP_FRAMES = 64

N_CHORD_IDX = CHORD_TO_IDX.get("N", 276)

# Split by player
PLAYER_SPLIT = {
    "P1": "train",
    "P2": "train",
    "P3": "val",
}


def _resample_if_needed(y: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    """Resample to TARGET_SR if the sample rate differs."""
    if sr == TARGET_SR:
        return y, sr
    import librosa
    y_resampled = librosa.resample(y, orig_sr=sr, target_sr=TARGET_SR)
    return y_resampled, TARGET_SR


def _extract_cqt(y: np.ndarray, sr: int) -> np.ndarray:
    """Compute 36-bin CQT + 4-bin bass features."""
    import librosa

    hop = int(sr * HOP_SEC)
    cqt = librosa.cqt(y=y, sr=sr, hop_length=hop, n_bins=CHROMA_BINS,
                      bins_per_octave=BINS_PER_OCTAVE)
    cqt = np.abs(cqt)
    cqt = cqt.T.astype(np.float32)

    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    cqt = cqt / norms

    bass = cqt[:, :BASS_BINS]
    features = np.concatenate([cqt, bass], axis=1)
    return features


def _frame_labels_from_timeline(timeline: list[dict], num_frames: int) -> np.ndarray:
    """Assign a chord label to each CQT frame."""
    labels = np.full(num_frames, N_CHORD_IDX, dtype=np.int32)

    for entry in timeline:
        start_t = entry["start"]
        end_t = entry["end"]
        chord = entry.get("chord")
        if not chord or chord == "N":
            continue

        chord_idx = CHORD_TO_IDX.get(chord, N_CHORD_IDX)

        frame_start = int(start_t / HOP_SEC)
        frame_end = int(end_t / HOP_SEC)

        for f in range(frame_start, min(frame_end, num_frames)):
            frame_t = f * HOP_SEC
            frame_end_t = frame_t + HOP_SEC
            overlap_start = max(frame_t, start_t)
            overlap_end = min(frame_end_t, end_t)
            overlap = max(0, overlap_end - overlap_start)

            if overlap >= HOP_SEC * 0.5:
                labels[f] = chord_idx

    return labels


def _build_windows(features: np.ndarray,
                   frame_labels: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build overlapping windows with center-frame labels.

    Returns:
        (windows, window_labels, window_times) arrays.
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
        center = start + WINDOW // 2
        if center < len(padded_labels):
            window_labels[k] = padded_labels[center]

    window_times = np.arange(len(window_labels), dtype=np.float32) * HOP_FRAMES * HOP_SEC
    return windows, window_labels, window_times


def process_track(audio_path: Path, timeline_path: Path, output_dir: Path,
                  force: bool = False) -> dict | None:
    """Process a single track."""
    if not audio_path.exists():
        return None
    if not timeline_path.exists():
        return None

    track_id = timeline_path.stem

    out_path = output_dir / f"{track_id}.npz"
    if out_path.exists() and not force:
        return {"track_id": track_id, "status": "cached", "path": str(out_path)}

    with open(timeline_path) as f:
        timeline = json.load(f)

    if not timeline:
        return None

    # Check if any chord annotations exist
    has_chords = any(seg.get("chord") and seg["chord"] != "N" for seg in timeline)
    if not has_chords:
        return None

    import librosa
    try:
        y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    except Exception as e:
        print(f"  [WARN] Could not load {audio_path.name}: {e}")
        return None

    y, sr = _resample_if_needed(y, sr)

    features = _extract_cqt(y, sr)
    num_frames = len(features)

    frame_labels = _frame_labels_from_timeline(timeline, num_frames)
    windows, window_labels, window_times = _build_windows(features, frame_labels)

    # Player and split
    player = track_id.split("_")[0] if track_id.startswith("P") else "P3"
    split = PLAYER_SPLIT.get(player, "train")

    output_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        features=windows,
        labels=window_labels,
        frame_times=window_times,
        track_id=track_id,
        player_id=player,
        split=split,
        loss_weight=1.0,
    )

    labeled = window_labels[window_labels != N_CHORD_IDX]
    print(f"  {track_id}: {len(windows)} windows, "
          f"{len(labeled)}/{len(window_labels)} labeled, "
          f"split={split}")

    return {"track_id": track_id, "status": "processed", "path": str(out_path),
            "split": split, "num_windows": len(windows)}


def main(data_dir: Path, force: bool = False) -> None:
    raw = data_dir / "guitar_techs" / "raw"
    proc = data_dir / "guitar_techs" / "processed"

    timelines_dir = proc / "timelines"
    cqt_dir = proc / "cqt"

    if not timelines_dir.exists():
        print(f"Timelines directory not found: {timelines_dir}")
        print("Run parse_guitar_techs.py first.")
        return

    # Find all timeline files
    timeline_files = sorted(timelines_dir.glob("*.json"))
    if not timeline_files:
        print(f"No timeline files found in {timelines_dir}")
        return

    print(f"Found {len(timeline_files)} timeline files, extracting CQT...")

    results = []
    for tl_path in timeline_files:
        track_id = tl_path.stem

        # Determine the audio path
        # track_id format: P1_chords_Set1_maj, P3_music_01, etc.
        parts = track_id.split("_", 2)
        if len(parts) < 3:
            continue
        player = parts[0]
        category = parts[1]
        label = parts[2] if len(parts) > 2 else ""

        audio_path = (raw / f"{player}_{category}" / "audio" / "directinput"
                      / f"directinput_{label}.wav")

        # For P3_music, the label is numeric (01-12)
        # For singlenotes, it's "allsinglenotes"
        if not audio_path.exists():
            audio_path = (raw / f"{player}_{category}" / "audio" / "directinput"
                          / f"directinput_{label}.wav")

        # Try alternate naming: no_label for single-file categories
        if not audio_path.exists() and not label:
            wavs = sorted((raw / f"{player}_{category}" / "audio" / "directinput").glob("*.wav"))
            if wavs:
                audio_path = wavs[0]

        if not audio_path.exists():
            print(f"  [SKIP] {track_id}: audio not found at {audio_path}")
            continue

        result = process_track(audio_path, tl_path, cqt_dir, force=force)
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
    print(f"  Tracks processed: {sum(by_split.values())} / {len(results)} total")
    print(f"  Train: {by_split.get('train', 0)}, Val: {by_split.get('val', 0)}")
    print(f"  Total training windows: {total_windows}")
    print(f"  Output: {cqt_dir}/")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract Guitar-TECHS CQT features")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent.parent / "data",
                        help="Data directory root")
    parser.add_argument("--force", action="store_true", help="Re-extract existing files")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
