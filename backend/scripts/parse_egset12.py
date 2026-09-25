"""Parse EGSet12 JAMS annotations into 277-class chord timelines.

EGSet12 JAMS files contain per-string MIDI note annotations (note_midi
namespace) but no explicit chord namespace. This script extracts MIDI
note events, builds active pitch sets per time frame, and matches them
against the 277-class vocabulary using template-based chord matching.

Usage:
    python scripts/parse_egset12.py [--data-dir DATA_DIR] [--force]

Output:
    <data_dir>/egset12/processed/timelines/<track_id>.json
        [{start, end, chord}, ...]
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_INTERVALS, CHORD_QUALITIES, ROOT_NOTES

PC_TO_ROOT = {i: note for i, note in enumerate(ROOT_NOTES)}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "egset12" / "raw"
PROCESSED_DIR = DATA_DIR / "egset12" / "processed"

HOP_SEC = 0.1

# Precompute interval sets for fast matching
CHORD_PC_SETS: dict[str, frozenset[int]] = {}
for qual, intervals in CHORD_INTERVALS.items():
    CHORD_PC_SETS[qual] = frozenset(interval % 12 for interval in intervals)


def _match_chord(active_pcs: set[int]) -> str | None:
    """Find the best 277-class chord label matching a set of active pitch classes.

    Scoring: Jaccard-like coverage with >66% threshold and penalty for extra notes.
    """
    if len(active_pcs) < 2:
        return None

    best_score = -1.0
    best_chord = None

    for root_pc in range(12):
        for quality in CHORD_QUALITIES:
            expected = CHORD_PC_SETS[quality]
            shifted = frozenset((pc + root_pc) % 12 for pc in expected)
            intersection = len(shifted & active_pcs)
            union = len(shifted | active_pcs)
            coverage = intersection / len(shifted) if shifted else 0.0
            if coverage < 0.66:
                continue
            score = intersection / union if union > 0 else 0.0
            if score > best_score:
                best_score = score
                best_chord = f"{PC_TO_ROOT[root_pc]}:{quality}"

    if best_score < 0.4:
        return None
    return best_chord


def _extract_midi_notes(jams_data: dict) -> list[tuple[float, float, int]]:
    """Extract all MIDI note events from JAMS note_midi annotations.

    Returns list of (start_time, end_time, midi_pitch) tuples.
    """
    notes: list[tuple[float, float, int]] = []
    for ann in jams_data.get("annotations", []):
        if ann.get("namespace") != "note_midi":
            continue
        ann_data = ann.get("data", [])
        if not ann_data:
            continue
        for item in ann_data:
            start = float(item.get("time", 0))
            duration = float(item.get("duration", 0))
            pitch = int(item.get("value", 0))
            if pitch > 0:
                notes.append((start, start + duration, pitch))
    return notes


def _build_chord_timeline(notes: list[tuple[float, float, int]]) -> list[dict]:
    """Build a chord timeline from MIDI note events.

    At each HOP_SEC frame, collects active pitch classes and matches
    against the 277-class vocabulary. Merges consecutive same-chord
    frames into segments.
    """
    if not notes:
        return []

    duration = max(end for _, end, _ in notes)
    num_frames = int(np.ceil(duration / HOP_SEC)) + 1

    # Per-frame active pitch class sets
    frame_pcs: list[set[int] | None] = [None] * num_frames

    for start_t, end_t, pitch in notes:
        pc = pitch % 12
        f_start = int(start_t / HOP_SEC)
        f_end = int(np.ceil(end_t / HOP_SEC))
        for f in range(f_start, min(f_end, num_frames)):
            if frame_pcs[f] is None:
                frame_pcs[f] = set()
            frame_pcs[f].add(pc)

    # Match each frame to a chord
    frame_chords: list[str | None] = []
    for f_pcs in frame_pcs:
        if f_pcs and len(f_pcs) >= 2:
            frame_chords.append(_match_chord(f_pcs))
        else:
            frame_chords.append(None)

    # Merge consecutive same-chord frames
    segments: list[dict] = []
    seg_start = 0.0
    seg_chord = frame_chords[0]

    for f in range(1, num_frames):
        current = frame_chords[f]
        if current != seg_chord:
            seg_end = f * HOP_SEC
            if seg_chord is not None:
                segments.append({
                    "start": round(seg_start, 3),
                    "end": round(seg_end, 3),
                    "chord": seg_chord,
                })
            seg_start = seg_end
            seg_chord = current

    if seg_chord is not None:
        segments.append({
            "start": round(seg_start, 3),
            "end": round(num_frames * HOP_SEC, 3),
            "chord": seg_chord,
        })

    return segments


def parse_jams_file(jams_path: Path) -> list[dict] | None:
    """Parse a single EGSet12 JAMS file into a chord timeline.

    Returns list of {start, end, chord} dicts, or None on failure.
    """
    try:
        with open(jams_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [WARN] Could not parse {jams_path.name}: {e}")
        return None

    notes = _extract_midi_notes(data)
    if not notes:
        print(f"  [WARN] {jams_path.name}: no note_midi data found")
        return None

    chords = _build_chord_timeline(notes)
    return chords if chords else None


def main(data_dir: Path, force: bool = False) -> None:
    raw = data_dir / "egset12" / "raw"
    proc = data_dir / "egset12" / "processed"

    if not raw.exists():
        print(f"Raw data directory not found: {raw}")
        print("Run download_egset12.py first.")
        return

    jams_files = sorted(raw.glob("*.jams"))
    if not jams_files:
        print(f"No JAMS files found in {raw}")
        return

    timelines_dir = proc / "timelines"
    timelines_dir.mkdir(parents=True, exist_ok=True)

    existing = list(timelines_dir.glob("*.json"))
    if not force and existing:
        print(f"[SKIP] Timelines already exist ({len(existing)} files) in {timelines_dir}")
        return

    print(f"Found {len(jams_files)} JAMS files, parsing MIDI notes to chords...")

    total_segments = 0
    parsed_count = 0

    for jf in jams_files:
        track_id = jf.stem
        chords = parse_jams_file(jf)
        if chords is None:
            print(f"  [SKIP] {track_id}: no chord annotations derived")
            continue

        out_path = timelines_dir / f"{track_id}.json"
        with open(out_path, "w") as f:
            json.dump(chords, f, indent=2)

        total_segments += len(chords)
        parsed_count += 1
        chord_count = sum(1 for c in chords if c.get("chord") != "N")
        print(f"  {track_id}: {len(chords)} segments ({chord_count} chord)")

    print(f"\nParsing complete:")
    print(f"  Files parsed: {parsed_count} / {len(jams_files)}")
    print(f"  Total chord segments: {total_segments}")
    print(f"  Output: {timelines_dir}/")
    print(f"\nNext: python scripts/extract_egset12_cqt.py")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Parse EGSet12 JAMS (note_midi) to 277-class chord timelines")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    parser.add_argument("--force", action="store_true",
                        help="Re-parse existing timelines")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
