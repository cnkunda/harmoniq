"""Extract CQT features from RWC-P audio aligned with chord labels.

Reads WAVs and per-track JSON timelines (from parse_rwc.py), aligns
144-bin CQT features with chord labels at 0.1s frame resolution.

All 100 tracks are used as training data (split='train'). The .npz
intentionally omits loss_weight so the training CLI
(--rwc-loss-weight) remains authoritative.

Usage:
    python scripts/extract_rwc_cqt.py [--data-dir DATA_DIR] [--force]

Output:
    Per-track .npz files in <data_dir>/rwc/processed/cqt/ containing:
        features: (T, 128, 144) — overlapping CQT windows
        labels:   (T,) — chord class indices matching the center frame
        frame_times: (T,) — center time of each window
        track_id: str
        split: str — 'train' for all tracks
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_TO_IDX, NUM_CLASSES
from app.cqt_constants import (TARGET_SR, HOP_SEC, BINS_PER_OCTAVE,
                               CHROMA_BINS, FEATURE_DIM, WINDOW, HOP_FRAMES)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

N_CHORD_IDX = CHORD_TO_IDX.get("N", NUM_CLASSES - 1)


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
    """Assign a chord label to each CQT frame using >50% overlap."""
    labels = np.full(num_frames, N_CHORD_IDX, dtype=np.int32)

    for entry in timeline:
        start_t = entry["start"]
        end_t = entry["end"]
        chord = entry["chord"]

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
                   frame_labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
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

    return windows, window_labels


def process_song(audio_path: Path, timeline_path: Path, output_dir: Path,
                 force: bool = False) -> dict | None:
    """Process one RWC-P track: load audio, extract CQT, align labels."""
    track_id = audio_path.stem

    if not timeline_path.exists():
        print(f"  [WARN] No timeline for {track_id}, skipping")
        return None

    out_path = output_dir / f"{track_id}.npz"
    if out_path.exists() and not force:
        return {"track_id": track_id, "status": "cached", "path": str(out_path)}

    with open(timeline_path, "r") as f:
        timeline = json.load(f)

    if not timeline:
        print(f"  [WARN] Empty timeline for {track_id}, skipping")
        return None

    import librosa
    try:
        y, sr = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
    except Exception as e:
        print(f"  [WARN] Could not load {audio_path}: {e}")
        return None

    features = _extract_cqt(y, sr)
    frame_labels = _frame_labels_from_timeline(timeline, len(features))
    windows, window_labels = _build_windows(features, frame_labels)

    output_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        features=windows,
        labels=window_labels,
        frame_times=np.arange(len(window_labels), dtype=np.float32) * HOP_FRAMES * HOP_SEC,
        track_id=track_id,
        split="train",
    )

    labeled = window_labels[window_labels != N_CHORD_IDX]
    print(f"  {track_id}: {len(windows)} windows, "
          f"{len(labeled)}/{len(window_labels)} labeled, split=train")

    return {"track_id": track_id, "status": "processed", "path": str(out_path),
            "num_windows": len(windows)}


def main(data_dir: Path, force: bool = False) -> None:
    raw = data_dir / "rwc" / "raw"
    proc = data_dir / "rwc" / "processed"

    audio_dir = raw / "audio" / "RWC-P"
    timeline_dir = proc / "timelines"
    cqt_dir = proc / "cqt"

    if not audio_dir.exists() or not timeline_dir.exists():
        print("Required directories not found.")
        print(f"  Audio: {audio_dir} {'✓' if audio_dir.exists() else '✗'}")
        print(f"  Timelines: {timeline_dir} {'✓' if timeline_dir.exists() else '✗'}")
        print("Run download_rwc.py (--download-audio) and parse_rwc.py first.")
        return

    wavs = sorted(audio_dir.glob("*.wav"))
    if not wavs:
        print(f"No WAV files found in {audio_dir}")
        return

    print(f"Found {len(wavs)} audio files, extracting CQT features...")

    results = []
    for wav in wavs:
        tl_path = timeline_dir / f"{wav.stem}.json"
        result = process_song(wav, tl_path, cqt_dir, force=force)
        if result:
            results.append(result)

    total_windows = sum(r.get("num_windows", 0) for r in results
                        if r["status"] == "processed")

    print("\nProcessing complete.")
    print(f"  Songs processed: {len(results)}")
    print(f"  Total training windows: {total_windows}")
    print(f"  Output: {cqt_dir}/")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract RWC-P CQT features")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    parser.add_argument("--force", action="store_true", help="Re-extract existing files")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
