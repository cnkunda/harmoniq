"""Extract CQT features from IDMT-SMT-Guitar audio aligned with chord labels.

Reads IDMT WAV files and per-clip JSON timelines (from parse_idmt_smt_guitar.py),
extracts 144-bin CQT features matching the GuitarSet format,
with added instrument and style metadata for per-source loss weighting.

Usage:
    python scripts/extract_idmt_cqt.py [--data-dir DATA_DIR] [--force]

Output:
    Per-clip .npz files in <data_dir>/idmt_smt_guitar/processed/cqt/ containing:
        features: (T, 128, 40) — overlapping CQT windows
        labels:   (T,) — chord class indices
        frame_times: (T,) — center time of each window
        track_id: str — clip identifier
        instrument: str — acoustic/electric_clean/electric_distortion
        style: str — strum/arpeggio/picked/muted
        source: str — always "idmt"
        loss_weight: float — per-source loss weight for training
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_TO_IDX, NUM_CLASSES

# Constants matching chord_inference.py exactly
from app.cqt_constants import (TARGET_SR, HOP_SEC, BINS_PER_OCTAVE, NUM_OCTAVES,
                                CHROMA_BINS, BASS_BINS, FEATURE_DIM, WINDOW, HOP_FRAMES)

N_CHORD_IDX = CHORD_TO_IDX.get("N", NUM_CLASSES - 1)

# Per-source loss weight for IDMT data (clean real audio, full weight)
IDMT_LOSS_WEIGHT = 1.0


def extract_cqt(y: np.ndarray, sr: int) -> np.ndarray:
    """Compute 144-bin CQT features.

    Matches chord_inference.py _extract_features exactly.
    """
    import librosa

    hop = int(sr * HOP_SEC)
    cqt = librosa.cqt(y=y, sr=sr, hop_length=hop, n_bins=CHROMA_BINS,
                      bins_per_octave=BINS_PER_OCTAVE)
    cqt = np.abs(cqt).T.astype(np.float32)
    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    features = cqt / norms
    return features


def frame_labels_from_timeline(
    timeline: list[dict], num_frames: int
) -> np.ndarray:
    """Assign chord label to each CQT frame, forward-biased boundary handling."""
    labels = np.full(num_frames, N_CHORD_IDX, dtype=np.int32)

    for entry in timeline:
        if entry.get("chord") is None:
            continue
        start_t = entry["start"]
        end_t = entry["end"]
        chord_idx = CHORD_TO_IDX.get(entry["chord"], N_CHORD_IDX)

        f_start = max(0, int(start_t / HOP_SEC) - 1)
        f_end = min(num_frames, int(end_t / HOP_SEC) + 2)

        for f in range(f_start, f_end):
            f_t = f * HOP_SEC
            f_end_t = f_t + HOP_SEC
            overlap = max(0, min(f_end_t, end_t) - max(f_t, start_t))
            if overlap >= HOP_SEC * 0.5:
                labels[f] = chord_idx

    return labels


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


def process_clip(
    audio_path: Path, timeline_path: Path, output_dir: Path, force: bool = False
) -> dict | None:
    """Process one IDMT audio clip + timeline pair.

    Returns dict with track metadata or None on failure.
    """
    import librosa
    import soundfile as sf

    clip_id = timeline_path.stem
    out_path = output_dir / f"{clip_id}.npz"

    if not force and out_path.exists():
        return {"track_id": clip_id, "status": "cached"}

    # Load timeline
    try:
        with open(timeline_path) as f:
            timeline = json.load(f)
    except Exception as e:
        print(f"  [WARN] Could not load timeline {timeline_path.name}: {e}")
        return None

    # Extract metadata from first segment
    instrument = timeline[0].get("instrument", "acoustic") if timeline else "acoustic"
    style = timeline[0].get("style", "strum") if timeline else "strum"

    # Load audio
    try:
        y, sr = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
    except Exception as e:
        print(f"  [WARN] Could not load audio {audio_path.name}: {e}")
        return None

    # Extract CQT
    features = extract_cqt(y, sr)
    num_frames = len(features)

    # Frame-level labels
    frame_labels = frame_labels_from_timeline(timeline, num_frames)

    # Build windows
    windows, window_labels = build_windows(features, frame_labels)

    # Save
    output_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        features=windows,
        labels=window_labels,
        frame_times=np.arange(len(windows), dtype=np.float32) * HOP_FRAMES * HOP_SEC,
        track_id=clip_id,
        instrument=instrument,
        style=style,
        source="idmt",
        loss_weight=IDMT_LOSS_WEIGHT,
        split="train",
    )

    labeled = int((window_labels != N_CHORD_IDX).sum())
    print(f"  {clip_id}: {len(windows)} windows, {labeled}/{len(windows)} labeled, "
          f"instrument={instrument}, style={style}")
    return {"track_id": clip_id, "path": str(out_path), "windows": len(windows)}


def main(data_dir: Path, force: bool = False) -> None:
    raw_dir = data_dir / "idmt_smt_guitar" / "raw" / "audio"
    timelines_dir = data_dir / "idmt_smt_guitar" / "processed" / "timelines"
    output_dir = data_dir / "idmt_smt_guitar" / "processed" / "cqt"

    if not raw_dir.exists() or not timelines_dir.exists():
        print("IDMT data/timelines not found. Run parse_idmt_smt_guitar.py first")
        print(f"  Audio: {raw_dir}")
        print(f"  Timelines: {timelines_dir}")
        return

    timeline_files = sorted(timelines_dir.glob("*.json"))
    if not timeline_files:
        print(f"No timeline files found in {timelines_dir}")
        return

    print(f"Found {len(timeline_files)} timeline files")
    print(f"Output: {output_dir}")

    results = []
    for tlf in timeline_files:
        clip_id = tlf.stem
        # Try to locate matching audio file
        audio_candidates = list(raw_dir.rglob(f"{clip_id}.wav"))
        if not audio_candidates:
            # Try without subdirectory prefix
            audio_candidates = list(raw_dir.rglob("*.wav"))
            # Filter by stem match
            audio_candidates = [a for a in audio_candidates
                                if a.stem == clip_id or a.stem in clip_id]
        if not audio_candidates:
            print(f"  [SKIP] {clip_id}: no matching audio file")
            continue

        audio_path = audio_candidates[0]
        result = process_clip(audio_path, tlf, output_dir, force=force)
        if result:
            results.append(result)

    print(f"\nProcessed {len(results)}/{len(timeline_files)} clips")
    if results:
        total_windows = sum(r.get("windows", 0) for r in results if "windows" in r)
        print(f"Total windows extracted: {total_windows}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Extract CQT features from IDMT-SMT-Guitar dataset")
    parser.add_argument("--data-dir", type=Path,
                        default=Path(__file__).resolve().parent.parent / "data",
                        help="Data directory root")
    parser.add_argument("--force", action="store_true",
                        help="Re-extract existing CQT features")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
