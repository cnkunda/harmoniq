"""VST synthetic audio pipeline: render MIDI → guitar audio → CQT features.

This is the primary synthetic data generation script for Commit 105 Phase 2.
It takes MIDI files (from generate_synthetic_midi.py), renders them through
the scipy-based guitar tone synthesizer, and extracts 144-bin CQT
features matching the training pipeline format.

Usage:
    python scripts/render_synthetic_guitar.py [--data-dir DATA_DIR] [--force] [--workers 4]
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_TO_IDX, NUM_CLASSES
from app.synth_guitar import (
    render_chord,
    render_melody_note,
    render_to_wav,
    apply_random_gain_shift,
    apply_random_eq_shift,
    TARGET_SR,
)
from app.reverb_ir import apply_random_reverb

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MIDI_DIR = DATA_DIR / "vst_synthetic" / "midi"
WAV_DIR = DATA_DIR / "vst_synthetic" / "wav"
CQT_DIR = DATA_DIR / "vst_synthetic" / "processed" / "cqt"

# CQT extraction constants (matching chord_inference.py)
from app.cqt_constants import (HOP_SEC, BINS_PER_OCTAVE, NUM_OCTAVES,
                                CHROMA_BINS, BASS_BINS, FEATURE_DIM, WINDOW, HOP_FRAMES)

N_CHORD_IDX = CHORD_TO_IDX.get("N", NUM_CLASSES - 1)

# Per-source loss weight for VST synthetic data
VST_LOSS_WEIGHT = 0.3


def extract_cqt(y: np.ndarray, sr: int) -> np.ndarray:
    """Compute 144-bin CQT features matching chord_inference.py."""
    import librosa

    hop = int(sr * HOP_SEC)
    cqt = librosa.cqt(y=y, sr=sr, hop_length=hop, n_bins=CHROMA_BINS,
                      bins_per_octave=BINS_PER_OCTAVE)
    cqt = np.abs(cqt).T.astype(np.float32)
    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    features = cqt / norms
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


def render_midi_to_chord_label(midi_path: Path) -> tuple[str, str] | None:
    """Extract chord label info from MIDI filename.

    MIDI filenames follow pattern: Root_quality_posX_octN.mid
    or prog_NNNN_bpmXXX.mid

    Returns (chord_label, sample_type) or None for progressions/melodies.
    """
    stem = midi_path.stem

    # Chord sample
    parts = stem.split("_")
    if len(parts) >= 4 and parts[0] in [
        "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"
    ]:
        root = parts[0]
        quality = parts[1]
        return (f"{root}:{quality}", "chord")

    return None


def render_chord_wav(
    midi_path: Path, wav_path: Path, label: str,
) -> None:
    """Render a single chord MIDI to WAV using the guitar synth.

    Args:
        midi_path: Path to MIDI file
        wav_path: Path for output WAV
        label: Chord label (e.g. "C:maj")
    """
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))

    if not pm.instruments:
        return

    notes = pm.instruments[0].notes
    if not notes:
        return

    duration = max(n.end for n in notes) + 1.0  # 1s trailing silence

    # Extract root MIDI note and quality
    root_midi = notes[0].pitch
    quality = label.split(":")[1] if ":" in label else "maj"

    from app.chord_vocab import CHORD_INTERVALS
    intervals = CHORD_INTERVALS.get(quality, [0, 4, 7])

    # Render chord via synth
    audio = render_chord(root_midi, intervals, duration, style="strum")

    # Apply random gain and EQ shift for variation
    audio = apply_random_gain_shift(audio, (-2.0, 2.0))
    audio = apply_random_eq_shift(audio)

    # Apply random reverb
    audio = apply_random_reverb(audio)

    render_to_wav(audio, wav_path)


def render_progression_wav(midi_path: Path, wav_path: Path) -> None:
    """Render a chord progression MIDI to WAV."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))

    if not pm.instruments or not pm.instruments[0].notes:
        return

    notes = pm.instruments[0].notes
    duration = max(n.end for n in notes) + 1.0

    # Render each chord separately
    audio = np.zeros(int(TARGET_SR * duration), dtype=np.float32)

    # Group notes by start time
    from collections import defaultdict
    time_groups: dict[float, list[int]] = defaultdict(list)
    for note in notes:
        time_groups[round(note.start, 2)].append(note.pitch)

    for start_time, group_notes in sorted(time_groups.items()):
        if not group_notes:
            continue

        chord_duration = duration - start_time - 0.5  # Remaining time
        root_midi = min(group_notes)
        # Use intervals relative to root
        intervals = sorted(set(n - root_midi for n in group_notes))

        chord_audio = render_chord(
            root_midi, intervals,
            max(chord_duration, 0.5),
            style="strum",
        )

        start_sample = int(TARGET_SR * start_time)
        end_sample = start_sample + len(chord_audio)
        if end_sample > len(audio):
            end_sample = len(audio)
        audio[start_sample:end_sample] += chord_audio[:end_sample - start_sample]

    # Normalize, apply effects
    peak = np.max(np.abs(audio))
    if peak > 0.001:
        audio = audio / peak * 0.95
    audio = apply_random_gain_shift(audio, (-2.0, 2.0))
    audio = apply_random_reverb(audio)

    render_to_wav(audio, wav_path)


def render_melody_wav(midi_path: Path, wav_path: Path) -> None:
    """Render a single-note melody MIDI to WAV."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))

    if not pm.instruments or not pm.instruments[0].notes:
        return

    notes = pm.instruments[0].notes
    duration = max(n.end for n in notes) + 1.0

    audio = np.zeros(int(TARGET_SR * duration), dtype=np.float32)

    for note in notes:
        note_audio = render_melody_note(
            note.pitch,
            max(note.end - note.start, 0.1),
            velocity=np.clip(note.velocity / 127.0, 0.3, 1.0),
        )
        start_sample = int(TARGET_SR * note.start)
        end_sample = start_sample + len(note_audio)
        if end_sample > len(audio):
            end_sample = len(audio)
        if end_sample > start_sample:
            audio[start_sample:end_sample] += note_audio[:end_sample - start_sample]

    peak = np.max(np.abs(audio))
    if peak > 0.001:
        audio = audio / peak * 0.95
    audio = apply_random_gain_shift(audio, (-2.0, 2.0))

    render_to_wav(audio, wav_path)


def extract_cqt_from_wav(
    wav_path: Path,
    label: str | None,
    sample_type: str,
    output_dir: Path,
    force: bool = False,
) -> dict | None:
    """Extract CQT features from WAV and save as .npz.

    Returns metadata dict or None on failure.
    """
    import librosa

    stem = wav_path.stem
    out_path = output_dir / f"{stem}.npz"

    if not force and out_path.exists():
        return {"track_id": stem, "status": "cached"}

    # Load audio
    y, sr = librosa.load(str(wav_path), sr=TARGET_SR, mono=True)

    # Extract CQT
    features = extract_cqt(y, sr)

    # Create labels
    if label and ":" in label:
        chord_idx = CHORD_TO_IDX.get(label, N_CHORD_IDX)
    else:
        chord_idx = N_CHORD_IDX

    num_frames = len(features)
    frame_labels = np.full(num_frames, chord_idx, dtype=np.int32)

    # Build windows
    windows, window_labels = build_windows(features, frame_labels)

    # Save
    output_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        features=windows,
        labels=window_labels,
        frame_times=np.arange(len(windows), dtype=np.float32) * HOP_FRAMES * HOP_SEC,
        track_id=stem,
        source="vst",
        sample_type=sample_type,
        loss_weight=VST_LOSS_WEIGHT,
    )

    return {"track_id": stem, "path": str(out_path), "windows": len(windows)}


def _process_one_midi(
    midi_path: Path,
    midi_type: str,
    wav_dir: Path,
    cqt_dir: Path,
    force: bool = False,
) -> dict | None:
    """Process one MIDI file: render WAV + extract CQT.

    Args:
        midi_path: Path to MIDI file
        midi_type: 'chord', 'progression', or 'melody'
        wav_dir: Output WAV directory
        cqt_dir: Output CQT .npz directory
        force: Re-process existing files

    Returns:
        Metadata dict or None on failure.
    """
    stem = midi_path.stem
    wav_path = wav_dir / f"{stem}.wav"

    try:
        label_info = render_midi_to_chord_label(midi_path)
        label = label_info[0] if label_info else None

        # Render WAV
        if not force and wav_path.exists():
            pass  # Already rendered
        elif midi_type == "chord" and label:
            render_chord_wav(midi_path, wav_path, label)
        elif midi_type == "progression":
            render_progression_wav(midi_path, wav_path)
        elif midi_type == "melody":
            render_melody_wav(midi_path, wav_path)

        # Extract CQT
        result = extract_cqt_from_wav(wav_path, label, midi_type, cqt_dir, force=force)
        return result

    except Exception as e:
        print(f"  [WARN] Failed to process {stem}: {e}")
        return None


def main(
    data_dir: Path,
    force: bool = False,
    workers: int = 1,
) -> None:
    midi_dir = data_dir / "vst_synthetic" / "midi"
    wav_dir = data_dir / "vst_synthetic" / "wav"
    cqt_dir = data_dir / "vst_synthetic" / "processed" / "cqt"

    # Collect all MIDI files by type
    midi_files = {
        "chord": sorted((midi_dir / "chords").glob("*.mid")),
        "progression": sorted((midi_dir / "progressions").glob("*.mid")),
        "melody": sorted((midi_dir / "melodies").glob("*.mid")),
    }

    total = sum(len(files) for files in midi_files.values())
    if total == 0:
        print("No MIDI files found. Run generate_synthetic_midi.py first.")
        print(f"  Expected MIDI dirs: {midi_dir}/chords/, progressions/, melodies/")
        return

    print(f"Found {total} MIDI files to render:")
    for mtype, files in midi_files.items():
        print(f"  {mtype}: {len(files)}")

    results: list[dict] = []
    if workers > 1 and total > 100:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = []
            for mtype, files in midi_files.items():
                for midi_path in files:
                    future = executor.submit(
                        _process_one_midi, midi_path, mtype,
                        wav_dir / mtype, cqt_dir, force,
                    )
                    futures.append(future)

            for i, future in enumerate(as_completed(futures)):
                result = future.result()
                if result:
                    results.append(result)
                if (i + 1) % 500 == 0:
                    print(f"  Processed {i + 1}/{total}")
    else:
        for mtype, files in midi_files.items():
            sub_wav_dir = wav_dir / mtype
            sub_wav_dir.mkdir(parents=True, exist_ok=True)

            for midi_path in files:
                result = _process_one_midi(
                    midi_path, mtype, sub_wav_dir, cqt_dir, force,
                )
                if result:
                    results.append(result)

    total_windows = sum(r.get("windows", 0) for r in results if "windows" in r)
    print(f"\nProcessed {len(results)}/{total} files")
    print(f"Total CQT windows: {total_windows}")
    print(f"CQT output: {cqt_dir}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Render synthetic guitar audio from MIDI and extract CQT features")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    parser.add_argument("--force", action="store_true",
                        help="Re-render existing files")
    parser.add_argument("--workers", type=int, default=1,
                        help="Number of parallel workers")
    args = parser.parse_args()
    main(args.data_dir, force=args.force, workers=args.workers)
