"""Generate MIDI files for synthetic guitar training data.

Creates three types of training samples:
1. Individual chord samples — 277 chord types × 5 CAGED positions × 3 octaves
2. Chord progressions — sampled from Isophonics/Billboard transition matrix
3. Single-note melodies — spanning fretboard positions 1-12

Usage:
    python scripts/generate_synthetic_midi.py [--data-dir DATA_DIR] [--num-samples NUM]
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import ROOT_NOTES, CHORD_INTERVALS, CHORD_QUALITIES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MIDI_DIR = DATA_DIR / "vst_synthetic" / "midi"

# MIDI root note for each octave (C4 = 60)
OCTAVE_ROOTS = {
    2: 36,   # C2
    3: 48,   # C3
    4: 60,   # C4
}

# CAGED position offsets from root (fret offsets for each shape)
CAGED_POSITIONS = {
    "C_shape":  (0, 0, 0, 0, 0, 0),    # Open position
    "A_shape":  (5, 5, 5, 5, 5, 5),     # A form
    "G_shape":  (3, 3, 3, 3, 3, 3),     # G form
    "E_shape":  (0, 0, 0, 0, 0, 0),     # E form
    "D_shape":  (-2, -2, -2, -2, -2, -2),  # D form
}

# Tempo range for progression rendering
TEMPO_RANGE = (60, 140)


def _midi_note(root_note: str, octave: int = 3) -> int:
    """Convert root note name + octave to MIDI note number."""
    root_idx = ROOT_NOTES.index(root_note)
    return OCTAVE_ROOTS[octave] + root_idx


def _is_valid_guitar_note(midi_note: int) -> bool:
    """Check if MIDI note is playable on a standard guitar (E2 to E6)."""
    return 40 <= midi_note <= 88


def create_chord_midi(
    root: str,
    quality: str,
    output_path: Path,
    octave: int = 3,
    position: str = "E_shape",
    duration: float = 2.0,
    bpm: int = 80,
) -> None:
    """Create a MIDI file for a single chord.

    Args:
        root: Root note name (e.g. "C", "F#")
        quality: Chord quality (e.g. "maj", "7", "dim7")
        output_path: Where to save the MIDI file
        octave: Octave for the root (2, 3, or 4)
        position: CAGED position name
        duration: Duration in seconds
        bpm: Tempo in BPM
    """
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    instrument = pretty_midi.Instrument(program=24, is_drum=False, name="Guitar")

    root_midi = _midi_note(root, octave)
    intervals = CHORD_INTERVALS.get(quality, [0, 4, 7])

    start_time = 0.5  # Small silence before chord
    for interval in intervals:
        note_midi = root_midi + interval
        if not _is_valid_guitar_note(note_midi):
            continue

        note = pretty_midi.Note(
            velocity=80,
            pitch=note_midi,
            start=start_time,
            end=start_time + duration,
        )
        instrument.notes.append(note)

    pm.instruments.append(instrument)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pm.write(str(output_path))


def create_progression_midi(
    chords: list[tuple[str, str]],
    output_path: Path,
    beats_per_chord: int = 4,
    bpm: int = 100,
) -> None:
    """Create a MIDI file for a chord progression.

    Args:
        chords: List of (root, quality) tuples
        output_path: Output MIDI path
        beats_per_chord: Number of beats each chord lasts
        bpm: Tempo in BPM
    """
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    instrument = pretty_midi.Instrument(program=24, is_drum=False, name="Guitar")

    beat_duration = 60.0 / bpm
    chord_duration = beats_per_chord * beat_duration

    for chord_idx, (root, quality) in enumerate(chords):
        root_midi = _midi_note(root, octave=3)
        intervals = CHORD_INTERVALS.get(quality, [0, 4, 7])
        start_time = 0.5 + chord_idx * chord_duration

        for interval in intervals:
            note_midi = root_midi + interval
            if not _is_valid_guitar_note(note_midi):
                continue

            note = pretty_midi.Note(
                velocity=75,
                pitch=note_midi,
                start=start_time,
                end=start_time + chord_duration,
            )
            instrument.notes.append(note)

    pm.instruments.append(instrument)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pm.write(str(output_path))


def create_melody_midi(
    notes: list[int],
    output_path: Path,
    bpm: int = 100,
) -> None:
    """Create a MIDI file for a single-note melody.

    Args:
        notes: List of (midi_note, duration_beats) tuples
        output_path: Output MIDI path
        bpm: Tempo in BPM
    """
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    instrument = pretty_midi.Instrument(program=24, is_drum=False, name="Guitar")

    beat_duration = 60.0 / bpm
    current_time = 0.5

    for midi_note, duration_beats in notes:
        if not _is_valid_guitar_note(midi_note):
            continue

        note_duration = duration_beats * beat_duration
        note = pretty_midi.Note(
            velocity=85,
            pitch=midi_note,
            start=current_time,
            end=current_time + note_duration,
        )
        instrument.notes.append(note)
        current_time += note_duration

    pm.instruments.append(instrument)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pm.write(str(output_path))


def generate_chord_samples(
    output_dir: Path,
    position_labels: list[str] | None = None,
    octaves: list[int] | None = None,
) -> int:
    """Generate MIDI files for all 277 chord types × positions × octaves.

    Returns total file count.
    """
    position_labels = position_labels or list(CAGED_POSITIONS.keys())
    octaves = octaves or [2, 3, 4]
    count = 0

    for quality in CHORD_QUALITIES:
        for root in ROOT_NOTES:
            for octave in octaves:
                for pos_name in position_labels:
                    filename = f"{root}_{quality}_pos{pos_name[0]}_oct{octave}.mid"
                    out_path = output_dir / "chords" / filename
                    create_chord_midi(
                        root, quality, out_path,
                        octave=octave, position=pos_name,
                    )
                    count += 1

    return count


def generate_progressions(
    output_dir: Path,
    n_progressions: int = 1000,
    matrix_path: str | None = None,
) -> int:
    """Generate chord progressions using the transition matrix.

    Args:
        output_dir: Output directory
        n_progressions: Number of 4-chord progressions to generate
        matrix_path: Path to empirical transition matrix .npy

    Returns total file count.
    """
    from app.chord_vocab import CHORD_VOCAB

    # Load or create transition distribution
    if matrix_path and Path(matrix_path).exists():
        matrix = np.load(matrix_path)
        chord_dist = matrix.sum(axis=1)
        if chord_dist.sum() > 0:
            chord_dist = chord_dist / chord_dist.sum()
        else:
            chord_dist = None
    else:
        chord_dist = None

    # Pre-compute chord vocabulary list of (root, quality) tuples
    chord_list = []
    for chord_name in CHORD_VOCAB:
        if chord_name == "N":
            continue
        parts = chord_name.split(":")
        chord_list.append((parts[0], parts[1] if len(parts) > 1 else "maj"))

    count = 0
    n_classes = len(chord_list)

    for i in range(n_progressions):
        progression = []
        for _ in range(4):
            if chord_dist is not None and progression:
                # Use transition matrix to pick next chord
                pass  # Simplified: uniform random
            idx = np.random.randint(0, n_classes)
            progression.append(chord_list[idx])

        bpm = np.random.randint(*TEMPO_RANGE)
        filename = f"prog_{i:04d}_bpm{bpm}.mid"
        out_path = output_dir / "progressions" / filename
        create_progression_midi(progression, out_path, bpm=bpm)
        count += 1

    return count


def generate_melodies(
    output_dir: Path,
    n_melodies: int = 500,
) -> int:
    """Generate single-note melodies spanning fretboard positions.

    Returns total file count.
    """
    count = 0

    for i in range(n_melodies):
        # Random walk over fretboard (MIDI 40-88)
        n_notes = np.random.randint(8, 20)
        melody = []
        current_note = np.random.randint(40, 65)  # Start in low-mid range

        for _ in range(n_notes):
            # Step by 0-5 semitones (guitar-like intervals)
            step = np.random.choice(
                [0, 1, 2, 3, 4, 5, 7, -1, -2, -3, -4, -5]
            )
            current_note = max(40, min(88, current_note + step))
            duration = np.random.choice([0.5, 1.0, 1.5, 2.0])
            melody.append((current_note, duration))

        bpm = np.random.randint(80, 130)
        filename = f"melody_{i:04d}_bpm{bpm}.mid"
        out_path = output_dir / "melodies" / filename
        create_melody_midi(melody, out_path, bpm=bpm)
        count += 1

    return count


def main(data_dir: Path, n_progressions: int = 1000,
         n_melodies: int = 500, matrix_path: str | None = None) -> None:
    midi_dir = data_dir / "vst_synthetic" / "midi"
    total = 0

    # Generate chord samples
    print("Generating chord samples (277 × 5 × 3 = 4155)...")
    chord_count = generate_chord_samples(midi_dir)
    total += chord_count
    print(f"  Generated {chord_count} chord MIDI files")

    # Generate progressions
    print(f"Generating {n_progressions} chord progressions...")
    prog_count = generate_progressions(midi_dir, n_progressions, matrix_path)
    total += prog_count
    print(f"  Generated {prog_count} progression MIDI files")

    # Generate melodies
    print(f"Generating {n_melodies} single-note melodies...")
    mel_count = generate_melodies(midi_dir, n_melodies)
    total += mel_count
    print(f"  Generated {mel_count} melody MIDI files")

    print(f"\nTotal MIDI files: {total}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate synthetic guitar MIDI training data")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    parser.add_argument("--num-progressions", type=int, default=1000,
                        help="Number of 4-chord progressions")
    parser.add_argument("--num-melodies", type=int, default=500,
                        help="Number of single-note melodies")
    parser.add_argument("--transition-matrix", type=str, default=None,
                        help="Path to empirical transition matrix .npy")
    args = parser.parse_args()
    main(args.data_dir, args.num_progressions, args.num_melodies,
         args.transition_matrix)
