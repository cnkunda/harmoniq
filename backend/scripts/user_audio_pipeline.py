"""User-supplied audio + .lab annotation preprocessing bridge (Commit 101 Phase 4).

Accepts a directory of user-provided audio files and matching .lab annotation
files, extracts CQT features aligned with chord labels.

Usage:
    python scripts/user_audio_pipeline.py <audio_dir> <lab_dir> [--output-dir OUTPUT_DIR]

    <audio_dir> — directory with .wav/.mp3 files (user's own audio copies)
    <lab_dir>   — directory with .lab annotation files (matching filenames by stem)

The script NEVER downloads copyrighted audio. The user must supply their own
audio files. Annotation files (.lab) are freely available from:
  - Isophonics: http://isophonics.net/
  - McGill Billboard: https://ddmal.ca/research/The_McGill_Billboard_Project/

Output:
    <output_dir>/cqt/<stem>.npz — CQT features + labels matching GuitarSet format
"""

import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_TO_IDX

# Inference pipeline constants (must match chord_inference.py)
TARGET_SR = 44100
HOP_SEC = 0.1
BINS_PER_OCTAVE = 12
NUM_OCTAVES = 3
CHROMA_BINS = BINS_PER_OCTAVE * NUM_OCTAVES  # 36
BASS_BINS = 4
FEATURE_DIM = CHROMA_BINS + BASS_BINS  # 40
WINDOW = 128
HOP_FRAMES = 64
N_CHORD_IDX = CHORD_TO_IDX.get("N", CHROMA_BINS * BASS_BINS - 1)

# Quality normalization (from build_empirical_transition_matrix)
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
    "Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#",
}

ROOT_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
CHORD_QUALITIES = list(QUALITY_NORM.keys()) + [
    "7", "maj7", "min7", "dim7", "sus2", "sus4", "7sus4",
    "6", "min6", "7#9", "7b9", "7#5", "7b5", "alt7",
    "9", "min9", "maj9", "11", "13",
]


def _parse_lab_label(label: str) -> str | None:
    """Parse a .lab chord label to 277-class format."""
    if not label or label == "N":
        return None
    label = label.strip()
    if "(" in label:
        label = label[: label.index("(")]
    if "/" in label:
        label = label.split("/")[0]
    label = label.strip()
    if not label or label == "N":
        return None
    if ":" in label:
        parts = label.split(":", 1)
        root_raw, quality_raw = parts[0], parts[1]
    else:
        root_raw = label[0]
        quality_raw = label[1:]
        if len(label) > 1 and label[1] in ("#", "b"):
            root_raw = label[:2]
            quality_raw = label[2:]
    if root_raw in _FLAT_TO_SHARP:
        root_raw = _FLAT_TO_SHARP[root_raw]
    if root_raw not in ROOT_NOTES:
        return None
    quality = QUALITY_NORM.get(quality_raw, quality_raw)
    if quality not in CHORD_QUALITIES:
        quality = "maj"
    return f"{root_raw}:{quality}"


def process_pair(audio_path: Path, lab_path: Path, output_dir: Path) -> dict | None:
    """Process one audio + .lab pair.

    Returns dict with track metadata or None on failure.
    """
    import librosa

    stem = audio_path.stem

    # Check .lab file exists
    if not lab_path.exists():
        print(f"  [SKIP] {stem}: .lab file not found at {lab_path}")
        return None

    # Load .lab file
    entries: list[tuple[float, float, str | None]] = []
    with open(lab_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                onset, offset = float(parts[0]), float(parts[1])
            except ValueError:
                continue
            label = _parse_lab_label(" ".join(parts[2:]))
            entries.append((onset, offset, label))

    if not entries:
        print(f"  [WARN] No valid annotations in {lab_path.name}")
        return None

    # Load audio
    try:
        y, sr = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
    except Exception as e:
        print(f"  [WARN] Could not load audio {audio_path.name}: {e}")
        return None

    # Check duration
    audio_dur = len(y) / sr
    last_annot_end = max(e[1] for e in entries)
    if abs(audio_dur - last_annot_end) > last_annot_end * 0.1:
        print(f"  [WARN] {stem}: audio ({audio_dur:.1f}s) vs annotations ({last_annot_end:.1f}s)"
              f" mismatch >10%, may be different version")

    # Extract CQT
    hop = int(sr * HOP_SEC)
    cqt = librosa.cqt(y=y, sr=sr, hop_length=hop, n_bins=CHROMA_BINS,
                      bins_per_octave=BINS_PER_OCTAVE)
    cqt = np.abs(cqt).T.astype(np.float32)
    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    cqt = cqt / norms
    bass = cqt[:, :BASS_BINS]
    features = np.concatenate([cqt, bass], axis=1)

    num_frames = len(features)

    # Frame-level labels (forward-biased)
    frame_labels = np.full(num_frames, N_CHORD_IDX, dtype=np.int32)
    for onset, offset, chord in entries:
        if chord is None:
            continue
        chord_idx = CHORD_TO_IDX.get(chord, N_CHORD_IDX)
        f_start = int(onset / HOP_SEC)
        f_end = int(offset / HOP_SEC)
        for f in range(f_start, min(f_end, num_frames)):
            f_t = f * HOP_SEC
            f_end_t = f_t + HOP_SEC
            overlap = max(0, min(f_end_t, offset) - max(f_t, onset))
            if overlap >= HOP_SEC * 0.5:
                frame_labels[f] = chord_idx

    # Build windows with center-frame labels
    pad = np.zeros((WINDOW // 2, FEATURE_DIM), dtype=np.float32)
    padded = np.concatenate([pad, features, pad], axis=0)
    padded_labels = np.concatenate([
        np.full(WINDOW // 2, N_CHORD_IDX, dtype=np.int32),
        frame_labels,
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

    # Save
    out_path = output_dir / f"{stem}.npz"
    output_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        features=windows,
        labels=window_labels,
        frame_times=np.arange(len(window_labels), dtype=np.float32) * HOP_FRAMES * HOP_SEC,
        track_id=stem,
        player_id="user",
        split="user",
    )

    chord_count = int((window_labels != N_CHORD_IDX).sum())
    print(f"  {stem}: {len(windows)} windows, {chord_count}/{len(window_labels)} labeled")
    return {"track_id": stem, "path": str(out_path), "windows": len(windows)}


def main(audio_dir: Path, lab_dir: Path, output_dir: Path) -> None:
    if not audio_dir.exists():
        print(f"Audio directory not found: {audio_dir}")
        sys.exit(1)
    if not lab_dir.exists():
        print(f"Annotation directory not found: {lab_dir}")
        sys.exit(1)

    # Match audio files with .lab files by stem
    audio_files = sorted(audio_dir.glob("*.wav")) + sorted(audio_dir.glob("*.mp3"))
    if not audio_files:
        print(f"No audio files found in {audio_dir}")
        sys.exit(1)

    print(f"Found {len(audio_files)} audio files matching against .lab files in {lab_dir}")

    results = []
    for af in audio_files:
        stem = af.stem
        lf = lab_dir / f"{stem}.lab"
        if not lf.exists():
            print(f"  [SKIP] {stem}: no matching .lab file")
            continue
        result = process_pair(af, lf, output_dir / "cqt")
        if result:
            results.append(result)

    print(f"\nProcessed {len(results)}/{len(audio_files)} pairs")
    print(f"Output: {output_dir / 'cqt'}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Preprocess user-supplied audio + .lab annotations")
    parser.add_argument("audio_dir", type=Path, help="Directory with audio files")
    parser.add_argument("lab_dir", type=Path, help="Directory with .lab annotation files")
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).resolve().parent.parent / "data" / "user_audio",
                        help="Output directory for CQT .npz files")
    args = parser.parse_args()
    main(args.audio_dir, args.lab_dir, args.output_dir)
