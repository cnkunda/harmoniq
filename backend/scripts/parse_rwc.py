"""Parse RWC-P chord annotations into 277-class chord timelines.

RWC-P ships semicolon-separated CSVs (t_start;t_end;chord) with
Harte-like labels and 'N' for no chord. Labels are normalized to
Harmoniq's 277-class vocabulary and saved per-track JSON timelines for
extract_rwc_cqt.py.

Usage:
    python scripts/parse_rwc.py [--data-dir DATA_DIR]

Output:
    <data_dir>/rwc/processed/timelines/<track_id>.json
        [{start, end, chord}, ...]
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.parse_guitarset import _parse_jams_chord_label

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Roots outside parse_guitarset's flat->sharp table (Db/Eb/Gb/Ab/Bb).
_ROOT_ALIASES = {"Cb": "B", "Fb": "E"}

_REQUIRED_COLUMNS = {"t_start", "t_end", "chord"}


def _normalize_rwc_label(raw: str) -> str | None:
    """Map an RWC chord label to the 277-class vocabulary.

    Handles Cb/Fb roots and the maj6 quality alias before delegating to
    the shared Harte parser (flats, bass notes, parenthesized alterations,
    hdim7 mapping).
    """
    raw = raw.strip()
    if not raw or raw == "N":
        return None

    if ":" in raw:
        root, quality = raw.split(":", 1)
        root = _ROOT_ALIASES.get(root, root)
        quality = quality.replace("maj6", "6")
        raw = f"{root}:{quality}"

    return _parse_jams_chord_label(raw)


def parse_rwc_csv(csv_path: Path) -> tuple[list[dict], Counter]:
    """Parse one RWC-P chord CSV into a timeline.

    Returns:
        (timeline, skipped) where timeline holds {start, end, chord}
        entries and skipped counts raw labels outside the vocabulary.
    """
    timeline: list[dict] = []
    skipped: Counter = Counter()

    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        if not _REQUIRED_COLUMNS.issubset(reader.fieldnames or []):
            print(f"  [WARN] {csv_path.name}: missing columns {_REQUIRED_COLUMNS}")
            return timeline, skipped

        for row in reader:
            raw_label = (row.get("chord") or "").strip()
            try:
                start = float(row["t_start"])
                end = float(row["t_end"])
            except (TypeError, ValueError):
                print(f"  [WARN] {csv_path.name}: bad timestamps for {raw_label!r}")
                continue
            if end <= start:
                print(f"  [WARN] {csv_path.name}: non-positive duration for {raw_label!r}")
                continue

            chord = _normalize_rwc_label(raw_label)
            if chord is None:
                if raw_label and raw_label != "N":
                    skipped[raw_label] += 1
                continue

            timeline.append({"start": start, "end": end, "chord": chord})

    return timeline, skipped


def parse_all(chords_dir: Path) -> tuple[dict[str, list[dict]], Counter]:
    """Parse all RWC-P chord CSVs in a directory."""
    songs: dict[str, list[dict]] = {}
    skipped: Counter = Counter()

    csv_files = sorted(chords_dir.glob("*.csv"))
    if not csv_files:
        return songs, skipped

    for csv_path in csv_files:
        timeline, file_skipped = parse_rwc_csv(csv_path)
        skipped.update(file_skipped)
        if timeline:
            songs[csv_path.stem] = timeline

    return songs, skipped


def save_timelines(songs: dict[str, list[dict]], output_dir: Path) -> None:
    """Save parsed chord timelines as JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for track_id, chords in songs.items():
        out_path = output_dir / f"{track_id}.json"
        with open(out_path, "w") as f:
            json.dump(chords, f, indent=2)
    print(f"  Saved {len(songs)} timelines to {output_dir}")


def main(data_dir: Path) -> None:
    raw = data_dir / "rwc" / "raw"
    proc = data_dir / "rwc" / "processed"

    chords_dir = raw / "chords" / "RWC-P"
    if not chords_dir.exists():
        print(f"Chord directory not found: {chords_dir}")
        print("Run download_rwc.py first.")
        return

    print("Parsing RWC-P chord annotations...")
    songs, skipped = parse_all(chords_dir)

    if not songs:
        print("No songs parsed. Check annotation directory structure.")
        return

    timeline_dir = proc / "timelines"
    save_timelines(songs, timeline_dir)

    total_segments = sum(len(chords) for chords in songs.values())
    print(f"\nTotal songs parsed: {len(songs)}")
    print(f"  Chord segments: {total_segments}")
    if skipped:
        print(f"  Skipped labels (not in 277 vocab): {dict(skipped.most_common(10))}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Parse RWC-P chords to 277-class timelines")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    args = parser.parse_args()
    main(args.data_dir)
