"""Extract CQT features from JAAH audio aligned with chord annotations.

Optional: requires user-supplied Smithsonian audio files. If audio is
not available, annotations can still be used for transition matrix
and chord distribution statistics.

Usage:
    # Annotations-only (for transition matrix — already downloaded):
    python scripts/extract_jaah_cqt.py

    # With user-supplied audio:
    python scripts/extract_jaah_cqt.py --audio-dir /path/to/smithsonian/audio

    # Force re-extraction:
    python scripts/extract_jaah_cqt.py --audio-dir /path --force

Output:
    (with audio) data/jaah/processed/cqt/<stem>.npz  — CQT windows
    (without audio) prints instructions only

.npz format (matching GuitarSet):
    features: (T, 128, 40) — overlapping CQT windows
    labels:   (T,) — chord class indices
    split:    str — 'train' or 'val' (80/20 file-based split)
"""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_TO_IDX
from app.cqt_constants import (HOP_SEC, BINS_PER_OCTAVE, NUM_OCTAVES,
                                CHROMA_BINS, BASS_BINS, FEATURE_DIM)
from scripts.user_audio_pipeline import _parse_lab_label, N_CHORD_IDX

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ANNOTATION_DIR = DATA_DIR / "annotations" / "jaah"
OUTPUT_DIR = DATA_DIR / "jaah" / "processed" / "cqt"


def extract_cqt_from_audio(audio_path: Path) -> np.ndarray:
    """Compute 144-bin CQT features matching chord_inference.py.

    Args:
        audio_path: Path to WAV/MP3 file.

    Returns:
        features: (T, CHROMA_BINS) array where T is number of frames
                  at 0.1s hop resolution.
    """
    import librosa

    y, sr = librosa.load(str(audio_path), sr=44100, mono=True)

    hop = int(44100 * HOP_SEC)
    cqt = np.abs(
        librosa.cqt(
            y,
            sr=sr,
            hop_length=hop,
            n_bins=CHROMA_BINS,
            bins_per_octave=BINS_PER_OCTAVE,
            fmin=librosa.note_to_hz('C1'),  # ~32.7 Hz
        )
    )
    cqt = cqt.T.astype(np.float32)

    # Normalize each frame
    row_sums = cqt.sum(axis=1, keepdims=True)
    cqt = np.divide(cqt, row_sums, where=row_sums > 0, out=np.zeros_like(cqt))

    return cqt.astype(np.float32)


def frame_labels_from_lab(
    lab_path: Path, n_frames: int, duration: float
) -> np.ndarray:
    """Align .lab annotations to 0.1s frame grid.

    Args:
        lab_path: Path to .lab file.
        n_frames: Number of CQT frames.
        duration: Audio duration in seconds.

    Returns:
        labels: (n_frames,) array of class indices.
    """
    labels = np.full(n_frames, N_CHORD_IDX, dtype=np.int32)

    with open(lab_path) as f:
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

            chord = _parse_lab_label(" ".join(parts[2:]))
            if chord is None:
                continue

            chord_idx = CHORD_TO_IDX.get(chord, N_CHORD_IDX)

            # Convert time to frame indices
            start_frame = max(0, min(n_frames - 1, int(onset / HOP_SEC)))
            end_frame = max(0, min(n_frames - 1, int(offset / HOP_SEC)))

            labels[start_frame : end_frame + 1] = chord_idx

    return labels


def sliding_windows(
    features: np.ndarray,
    labels: np.ndarray,
    window: int = 128,
    hop: int = 64,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract overlapping windows with center-frame labels.

    Args:
        features: (T, FEATURE_DIM) CQT features.
        labels: (T,) frame labels.
        window: Window size in frames (128 = 12.8s).
        hop: Hop between windows (64 = 50% overlap).

    Returns:
        (windows, window_labels) arrays.
    """
    T = features.shape[0]
    windows: list[np.ndarray] = []
    window_labels: list[np.ndarray] = []

    for start in range(0, T - window + 1, hop):
        end = start + window
        center = start + window // 2

        windows.append(features[start:end])
        window_labels.append(labels[center])

    if not windows:
        return np.array([]), np.array([])

    return np.stack(windows, axis=0), np.array(window_labels, dtype=np.int32)


def process_jaah_track(
    lab_path: Path,
    audio_dir: Path | None,
    output_dir: Path,
    force: bool = False,
) -> dict | None:
    """Process one JAAH track: extract CQT from audio and align with .lab.

    Args:
        lab_path: Path to .lab annotation file.
        audio_dir: Directory containing Smithsonian audio (or None).
        output_dir: Output directory for .npz files.
        force: Re-extract even if .npz exists.

    Returns:
        dict with track metadata, or None on failure.
    """
    stem = lab_path.stem
    output_path = output_dir / f"{stem}.npz"

    if output_path.exists() and not force:
        return {"stem": stem, "status": "skipped"}

    if audio_dir is None:
        return {"stem": stem, "status": "no_audio"}

    # Find matching audio file
    audio_path: Path | None = None
    for ext in [".wav", ".mp3", ".flac", ".m4a"]:
        candidate = audio_dir / f"{stem}{ext}"
        if candidate.exists():
            audio_path = candidate
            break
    # Also try without stem prefix
    if audio_path is None:
        for ext in [".wav", ".mp3", ".flac", ".m4a"]:
            for f in audio_dir.glob(f"*{ext}"):
                if stem.lower() in f.stem.lower():
                    audio_path = f
                    break
            if audio_path is not None:
                break

    if audio_path is None:
        print(f"  [SKIP] {stem}: no audio file found in {audio_dir}")
        return {"stem": stem, "status": "no_audio"}

    try:
        features = extract_cqt_from_audio(audio_path)
    except Exception as e:
        print(f"  [FAIL] {stem}: CQT extraction error: {e}")
        return {"stem": stem, "status": "cqt_error"}

    duration = features.shape[0] * HOP_SEC
    labels = frame_labels_from_lab(lab_path, features.shape[0], duration)

    windows, window_labels = sliding_windows(features, labels)

    if len(windows) == 0:
        print(f"  [SKIP] {stem}: too short ({duration:.1f}s)")
        return {"stem": stem, "status": "too_short"}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        str(output_path),
        features=windows,
        labels=window_labels,
        track_id=stem,
        split="train",  # Will be reassigned by load_real_data
    )
    print(f"  [OK]   {stem}: {len(windows)} windows, {duration:.1f}s")

    return {
        "stem": stem,
        "status": "ok",
        "windows": len(windows),
        "duration_s": round(duration, 1),
    }


def main(audio_dir: Path | None, force: bool = False) -> None:
    """Run JAAH CQT extraction for all tracks.

    Args:
        audio_dir: Optional path to Smithsonian audio files.
        force: Re-extract existing .npz files.
    """
    if not ANNOTATION_DIR.exists():
        print(f"JAAH annotation directory not found: {ANNOTATION_DIR}")
        print("Run 'python scripts/download_jaah.py' first.")
        return

    lab_files = sorted(ANNOTATION_DIR.glob("*.lab"))
    if not lab_files:
        print(f"No .lab files found in {ANNOTATION_DIR}")
        return

    print(f"Found {len(lab_files)} JAAH .lab files")

    if audio_dir is None or not audio_dir.exists():
        print()
        print("No audio directory specified or directory not found.")
        print("JAAH annotations can still be used for:")
        print("  - Building empirical transition matrix (run build_empirical_transition_matrix.py)")
        print("  - Chord quality distribution analysis")
        print()
        print(f"To extract CQT features for training, supply Smithsonian audio:")
        print(f"  python scripts/extract_jaah_cqt.py --audio-dir /path/to/audio")
        return

    print(f"Audio directory: {audio_dir}")
    print(f"Output directory: {OUTPUT_DIR}")
    print()

    results: list[dict] = []
    for lab_path in lab_files:
        result = process_jaah_track(lab_path, audio_dir, OUTPUT_DIR, force)
        results.append(result)

    stats = {
        "ok": sum(1 for r in results if r and r.get("status") == "ok"),
        "skipped": sum(1 for r in results if r and r.get("status") == "skipped"),
        "no_audio": sum(1 for r in results if r and r.get("status") == "no_audio"),
        "cqt_error": sum(1 for r in results if r and r.get("status") == "cqt_error"),
        "too_short": sum(1 for r in results if r and r.get("status") == "too_short"),
    }

    print()
    print(f"Results: {stats['ok']} ok, {stats['skipped']} skipped, "
          f"{stats['no_audio']} no audio, {stats['cqt_error']} errors, "
          f"{stats['too_short']} too short")
    total_windows = sum(
        r.get("windows", 0) for r in results if r and r.get("status") == "ok"
    )
    if total_windows:
        print(f"Total windows extracted: {total_windows}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Extract CQT features from JAAH audio (optional, requires user-supplied audio)")
    parser.add_argument("--audio-dir", type=Path, default=None,
                        help="Directory containing Smithsonian audio files")
    parser.add_argument("--force", action="store_true",
                        help="Force re-extraction of existing .npz files")
    args = parser.parse_args()
    main(args.audio_dir, args.force)
