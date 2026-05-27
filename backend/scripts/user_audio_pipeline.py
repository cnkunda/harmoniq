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

from app.chord_vocab import CHORD_INTERVALS, CHORD_TO_IDX

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

# Diatonic interval name → semitone offset (JAAH interval notation support)
_INTERVAL_TO_SEMITONE: dict[str, int] = {
    "1": 0,
    "b2": 1, "2": 2, "#2": 3,
    "b3": 3, "3": 4,
    "4": 5, "#4": 6, "b5": 6,
    "5": 7, "#5": 8, "b6": 8,
    "6": 9, "bb7": 9, "b7": 10,
    "7": 11,
    "b9": 13, "9": 14, "#9": 15,
    "11": 17, "#11": 18,
    "b13": 20, "13": 21,
}


def _build_interval_reverse_map() -> dict[frozenset[int], str]:
    rev: dict[frozenset[int], str] = {}
    for quality, intervals in CHORD_INTERVALS.items():
        reduced = frozenset(iv % 12 for iv in intervals if iv % 12 != 0)
        rev[reduced] = quality
    return rev


_INTERVAL_REVERSE_MAP = _build_interval_reverse_map()


def _parse_interval_notation(interval_str: str) -> str | None:
    """Parse JAAH interval notation like '(b3,5,b7,11)' to chord quality."""
    if not interval_str or not interval_str.startswith("("):
        return None
    content = interval_str.strip("()")
    parts = [p.strip() for p in content.split(",") if p.strip()]
    if not parts:
        return None
    semitones: set[int] = set()
    for p in parts:
        st = _INTERVAL_TO_SEMITONE.get(p)
        if st is None:
            return None
        st_mod = st % 12
        if st_mod != 0:
            semitones.add(st_mod)
    if not semitones:
        return None
    key = frozenset(semitones)
    if key in _INTERVAL_REVERSE_MAP:
        return _INTERVAL_REVERSE_MAP[key]
    best_q: str | None = None
    best_score = -1.0
    for reduced_set, q in _INTERVAL_REVERSE_MAP.items():
        overlap = len(key & reduced_set)
        penalty = len(reduced_set - key)
        score = overlap - 0.5 * penalty
        if score > best_score:
            best_score = score
            best_q = q
    if best_q is not None and best_score >= 2.0:
        return best_q
    return None


def _parse_lab_label(label: str) -> str | None:
    """Parse a .lab chord label to 277-class format.

    Handles Harte syntax, shorthand notation,
    and JAAH interval notation (e.g. 'F:(b3,5,b7,11)').
    """
    if not label or label == "N":
        return None
    label = label.strip()
    if not label:
        return None

    # Parse root + quality (do NOT strip parentheses before colon split)
    if ":" in label:
        parts = label.split(":", 1)
        root_raw, quality_raw = parts[0], parts[1]

        # Handle JAAH interval notation: F:(b3,5,b7,11)
        if quality_raw.startswith("("):
            quality = _parse_interval_notation(quality_raw)
            if quality is None:
                return None
        else:
            # Strip parenthesized extensions from quality only
            if "(" in quality_raw:
                quality_raw = quality_raw[: quality_raw.index("(")]
            if "/" in quality_raw:
                quality_raw = quality_raw.split("/")[0]
            quality_raw = quality_raw.strip()
            quality = QUALITY_NORM.get(quality_raw, quality_raw)
    else:
        # Shorthand: 'C', 'Am', 'Bb7', 'Am7(b5)'
        root_raw = label[0]
        quality_raw = label[1:]
        if len(label) > 1 and label[1] in ("#", "b"):
            root_raw = label[:2]
            quality_raw = label[2:]
        # Strip parenthesized extensions and bass notes from shorthand quality
        if "(" in quality_raw:
            quality_raw = quality_raw[: quality_raw.index("(")]
        if "/" in quality_raw:
            quality_raw = quality_raw.split("/")[0]
        quality_raw = quality_raw.strip()
        quality = QUALITY_NORM.get(quality_raw, quality_raw)

    if root_raw in _FLAT_TO_SHARP:
        root_raw = _FLAT_TO_SHARP[root_raw]
    if root_raw not in ROOT_NOTES:
        return None
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
