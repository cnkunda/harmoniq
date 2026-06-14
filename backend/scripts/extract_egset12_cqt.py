"""Extract CQT features from EGSet12 audio aligned with chord labels.

Reads WAVs and per-track JSON timelines (from parse_egset12.py), aligns
36-bin CQT + 4-bin bass features with chord labels at 0.1s frame resolution.

All 12 tracks are used as training data (no test hold-back since the dataset
is small and intended for diverse style coverage).

Usage:
    python scripts/extract_egset12_cqt.py [--data-dir DATA_DIR] [--force]

Output:
    Per-track .npz files in <data_dir>/egset12/processed/cqt/ containing:
        features:    (T, 128, 40) — overlapping CQT windows
        labels:      (T,) — chord class indices matching center frame
        frame_times: (T,) — center time of each window
        track_id:    str
        split:       str  — 'train' for all tracks
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_TO_IDX

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "egset12" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "egset12" / "processed"

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


def _resample_if_needed(y: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
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
    """Assign a chord label to each CQT frame using >50% overlap."""
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
    """Build overlapping windows with center-frame labels."""
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


def process_song(audio_path: Path, timeline_path: Path, output_dir: Path,
                 force: bool = False) -> dict | None:
    """Process a single EGSet12 song."""
    if not audio_path.exists():
        return None
    if not timeline_path.exists():
        return None

    track_id = audio_path.stem

    out_path = output_dir / f"{track_id}.npz"
    if out_path.exists() and not force:
        return {"track_id": track_id, "status": "cached", "path": str(out_path)}

    with open(timeline_path) as f:
        timeline = json.load(f)

    if not timeline:
        return None

    import librosa
    try:
        y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    except Exception as e:
        print(f"  [WARN] Could not load {audio_path.name}: {e}")
        return None

    # EGSet12 is 48kHz; resample to 44.1kHz
    y, sr = _resample_if_needed(y, sr)

    features = _extract_cqt(y, sr)
    num_frames = len(features)

    frame_labels = _frame_labels_from_timeline(timeline, num_frames)
    windows, window_labels, window_times = _build_windows(features, frame_labels)

    output_dir.mkdir(parents=True, exist_ok=True)
    # Commit 148 Phase 1d: reserve tracks 03, 07, 11 for test split
    split = "test" if track_id in ("03", "07", "11") else "train"
    np.savez_compressed(
        out_path,
        features=windows,
        labels=window_labels,
        frame_times=window_times,
        track_id=track_id,
        split=split,
        loss_weight=1.0,
    )

    labeled = window_labels[window_labels != N_CHORD_IDX]
    print(f"  {track_id}: {len(windows)} windows, "
          f"{len(labeled)}/{len(window_labels)} labeled, train")

    return {"track_id": track_id, "status": "processed", "path": str(out_path),
            "num_windows": len(windows)}


def main(data_dir: Path, force: bool = False) -> None:
    raw = data_dir / "egset12" / "raw"
    proc = data_dir / "egset12" / "processed"

    timelines_dir = proc / "timelines"
    cqt_dir = proc / "cqt"

    if not timelines_dir.exists():
        print(f"Timelines directory not found: {timelines_dir}")
        print("Run parse_egset12.py first.")
        return

    # Find all WAVs with matching timelines
    wavs = sorted(raw.glob("*.wav"))
    if not wavs:
        print(f"No WAV files found in {raw}")
        return

    print(f"Found {len(wavs)} audio files, extracting CQT features...")

    results = []
    for wav in wavs:
        track_id = wav.stem
        tl_path = timelines_dir / f"{track_id}.json"
        result = process_song(wav, tl_path, cqt_dir, force=force)
        if result:
            results.append(result)

    # Summary
    total_windows = sum(r.get("num_windows", 0) for r in results
                        if r.get("status") == "processed")

    print(f"\nProcessing complete.")
    print(f"  Songs processed: {len(results)}")
    print(f"  Total training windows: {total_windows}")
    print(f"  Output: {cqt_dir}/")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract EGSet12 CQT features")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent.parent / "data",
                        help="Data directory root")
    parser.add_argument("--force", action="store_true", help="Re-extract existing files")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
