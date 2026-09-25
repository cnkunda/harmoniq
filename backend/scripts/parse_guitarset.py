"""Parse GuitarSet JAMS annotations and map to 277-class Harte vocabulary.

Reads annotation JAMS files from data/guitarset/raw/annotation/, maps
chord labels to the 277-class vocabulary, and saves per-song label
timelines for CQT extraction.

Usage:
    python scripts/parse_guitarset.py [--data-dir DATA_DIR]

Chord mapping (JAMS `chord` namespace → Harmoniq 277-class):
    hdim7   → dim7    (half-diminished 7th → fully diminished)
    minmaj7 → maj7    (minor-major 7th → major 7th)
    All other JAMS qualities map 1:1 to our vocabulary.
"""

import json
from pathlib import Path
import sys
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import ROOT_NOTES, CHORD_QUALITIES, CHORD_TO_IDX, CHORD_INTERVALS

# Flat → sharp root mapping for normalization
_FLAT_TO_SHARP = {
    "Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#",
}

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "guitarset" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "guitarset" / "processed"

# JAMS chord qualities outside our 277 vocabulary that need mapping
QUALITY_MAP = {
    "hdim7": "dim7",      # half-dim 7th [0,3,6,10] → fully dim [0,3,6,9] (closest functional match)
    "minmaj7": "maj7",    # minor-major 7th [0,3,7,11] → maj7 [0,4,7,11] (same maj7 interval)
}

# Qualities that exist in JAMS and already match our vocabulary
KNOWN_QUALITIES = set(CHORD_QUALITIES)


def _normalize_root(root: str) -> str | None:
    """Convert flat notation to sharp (Bb → A#) for Harmoniq vocabulary."""
    if root in ROOT_NOTES:
        return root
    if root in _FLAT_TO_SHARP:
        return _FLAT_TO_SHARP[root]
    return None


def _strip_extensions(label: str) -> str:
    """Remove parenthesized alterations and bass-note suffixes from a chord label.

    'C:maj7(#11)' → 'C:maj7'
    'D:min/G' → 'D:min'
    'G:7(b9,b13)' → 'G:7'
    'Am' → 'A:min' (shorthand)
    """
    # Remove bass note suffix: chord/bass → chord
    if "/" in label:
        label = label.split("/")[0]

    # Remove parenthesized alterations: chord(...) → chord
    if "(" in label:
        label = label[: label.index("(")]

    # Remove trailing whitespace
    label = label.strip()

    # Handle dots (Billboard repeat convention — expand to previous chord downstream)
    if label == ".":
        return label

    # Handle special Billboard markers
    if label in ("*", "&pause"):
        return "N"

    # Handle single-note/bass-only: '1', '5' (power chord)
    if label in ("1",):
        return "N"
    if label in ("5",):
        return label  # power chord, handled in normalize

    return label


def _parse_jams_chord_label(raw: str) -> str | None:
    """Convert a raw JAMS chord annotation to our 277-class format (like 'C:maj').

    Handles formats:
      'C:maj'   → C:maj  (Harte syntax)
      'C'       → C:maj  (implied major)
      'Am'      → A:min  (shorthand)
      'Bb7'     → Bb:7   (flat root + quality shorthand)
      'F#:min7' → F#:min7

    Returns None if the chord should be treated as no-chord (N).
    """
    if not raw or raw == "N":
        return None

    cleaned = _strip_extensions(raw)
    if not cleaned or cleaned == "N":
        return None

    # Determine if this uses 'root:quality' syntax (Harte) or shorthand
    if ":" in cleaned:
        # Harte syntax: 'C:maj', 'F#:min7'
        parts = cleaned.split(":", 1)
        root = parts[0]
        quality_raw = parts[1]
    else:
        # Shorthand: 'C' (implied major) or 'Am', 'Bb7', 'F#m'
        root = cleaned[0]
        idx = 1
        # Handle '#' or 'b' accidental
        if len(cleaned) > 1 and cleaned[1] in ("#", "b"):
            root = cleaned[:2]
            idx = 2

        quality_raw = cleaned[idx:]

    # Normalize root (accept both sharps and flats)
    root = _normalize_root(root)
    if root is None:
        return None

    # Normalize quality
    quality = _normalize_quality(quality_raw)
    if quality is None:
        return None

    # Map rare qualities to closest match
    quality = QUALITY_MAP.get(quality, quality)

    # Check if quality is in our vocabulary
    if quality not in KNOWN_QUALITIES:
        return None

    return f"{root}:{quality}"


def _normalize_quality(raw: str) -> str:
    """Normalize a JAMS chord quality string to match our vocabulary.

    Handles: '', 'maj', 'min', 'm', 'dim', 'aug', '7', 'maj7', 'min7',
             'm7', 'dim7', '7sus4', 'sus4', 'sus2', '6', 'm6', 'min6',
             '9', 'm9', 'min9', 'maj9', '11', '13', '7#9', '7b9', etc.
    """
    if not raw:
        return "maj"

    raw = raw.strip()

    # Shorthand normalization
    norm_map = {
        "maj": "maj",
        "major": "maj",
        "min": "min",
        "m": "min",
        "minor": "min",
        "dim": "dim",
        "aug": "aug",
        "augmented": "aug",
        "sus4": "sus4",
        "sus2": "sus2",
        "hdim7": "hdim7",
        "half-dim7": "hdim7",
        "half-diminished": "hdim7",
        "minmaj7": "minmaj7",
        "m/maj7": "minmaj7",
        "m(maj7)": "minmaj7",
    }

    # Direct lookup
    if raw in norm_map:
        return norm_map[raw]

    # Try known qualities directly
    if raw in KNOWN_QUALITIES:
        return raw

    # Handle 'm7' → 'min7', 'maj7' → 'maj7', 'm9' → 'min9', etc.
    # m<something> → min<something>
    if raw.startswith("m"):
        candidate = "min" + raw[1:]
        if candidate in KNOWN_QUALITIES:
            return candidate

    return raw


def parse_guitarset_jams(jams_dir: Path) -> dict[str, list[dict]]:
    """Parse all JAMS files in a directory and return per-song chord timelines.

    Returns:
        Dict mapping track_id (e.g., '00_BN1-129-Eb_comp') to list of:
            {start: float, end: float, chord_label: str}  (277-class format)
    """
    jams_files = sorted(jams_dir.rglob("*.jams"))
    if not jams_files:
        jams_files = sorted(jams_dir.rglob("*.json"))

    print(f"Found {len(jams_files)} JAMS files")

    songs: dict[str, list[dict]] = {}
    skipped_qualities: Counter = Counter()
    total_annotations = 0
    mapped_count = 0

    for jf in jams_files:
        try:
            with open(jf, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [WARN] Could not parse {jf.name}: {e}")
            continue

        # Track ID from filename (without extension)
        track_id = jf.stem

        # Extract annotations
        annotations = data.get("annotations", [])
        if not annotations:
            continue

        # Use the first chord annotation (prefer performed over instructed)
        chord_ann = None
        for ann in annotations:
            if ann.get("namespace") == "chord":
                chord_ann = ann
                break
        if chord_ann is None:
            continue

        # Get chord annotation data
        ann_data = chord_ann.get("data", [])
        if not ann_data:
            continue

        chords = []
        for item in ann_data:
            total_annotations += 1
            raw_label = item.get("value", "")
            raw_label = _strip_extensions(raw_label)

            chord = _parse_jams_chord_label(raw_label)
            if chord is None:
                continue

            # Parse time from JAMS 'time' field or separate start/end
            start = float(item.get("time", 0))
            duration = float(item.get("duration", 0))
            end = start + duration

            chords.append({
                "start": start,
                "end": end,
                "chord": chord,
            })
            mapped_count += 1

        # Track skipped qualities
        for item in ann_data:
            raw_label = item.get("value", "")
            cleaned = _strip_extensions(raw_label)
            root_part = cleaned[0] if cleaned else ""
            if len(cleaned) > 1 and cleaned[1] in ("#", "b"):
                qual = cleaned[2:]
            else:
                qual = cleaned[1:]
            qual = _normalize_quality(qual)
            if qual not in KNOWN_QUALITIES and qual not in QUALITY_MAP:
                skipped_qualities[qual] += 1

        if chords:
            songs[track_id] = chords

    print(f"  Total annotations: {total_annotations}")
    print(f"  Mapped to vocabulary: {mapped_count}")
    if skipped_qualities:
        print(f"  Skipped qualities (not in 277 vocab): {dict(skipped_qualities.most_common(10))}")

    return songs


def save_timelines(songs: dict[str, list[dict]], output_dir: Path) -> None:
    """Save parsed chord timelines as JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for track_id, chords in songs.items():
        out_path = output_dir / f"{track_id}.json"
        with open(out_path, "w") as f:
            json.dump(chords, f, indent=2)
    print(f"  Saved {len(songs)} timelines to {output_dir}")


def main(data_dir: Path) -> None:
    raw = data_dir / "guitarset" / "raw"
    proc = data_dir / "guitarset" / "processed"

    annot_dir = raw / "annotation"
    if not annot_dir.exists():
        print(f"Annotation directory not found: {annot_dir}")
        print("Run download_guitarset.py first.")
        return

    print("Parsing GuitarSet JAMS annotations...")
    songs = parse_guitarset_jams(annot_dir)

    if not songs:
        print("No songs parsed. Check annotation directory structure.")
        return

    # Save per-song timelines
    timeline_dir = proc / "timelines"
    save_timelines(songs, timeline_dir)

    # Print player distribution
    players = set(tid.split("_")[0] for tid in songs)
    print(f"\nTotal songs parsed: {len(songs)}")
    print(f"Players: {sorted(players)}")
    for pid in sorted(players):
        count = sum(1 for tid in songs if tid.startswith(pid))
        print(f"  Player {pid}: {count} tracks")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Parse GuitarSet JAMS to 277-class vocabulary")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent.parent / "data",
                        help="Data directory root")
    args = parser.parse_args()
    main(args.data_dir)
