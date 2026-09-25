"""Parse IDMT-SMT-Guitar dataset into 277-class chord timelines.

Reads the CSV chord annotations from dataset4's chord annotation files,
maps chord symbols to the 277-class Harte vocabulary.

Usage:
    python scripts/parse_idmt_smt_guitar.py [--data-dir DATA_DIR] [--force]

Output:
    <data_dir>/idmt_smt_guitar/processed/timelines/<clip_id>.json
        [{start, end, chord, instrument, style, path}, ...]
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

IDMT_ROOT = Path(__file__).resolve().parent.parent / "data" / "idmt_smt_guitar"
RAW_DIR = IDMT_ROOT / "raw" / "audio"
PROCESSED_DIR = IDMT_ROOT / "processed"

# Only dataset4 has chord annotations (CSV files)
# Datasets 1-3 are technique recordings with XML annotations (not chord-labeled)
IDMT_CHORD_DATASET = "dataset4"

ROOT_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_REGEX = re.compile(r"^([A-G][#b]?)(.*)", re.IGNORECASE)
FULL_CHORD_REGEX = re.compile(
    r"^([A-G][#b]?)"       # Root (e.g., C, F#, Bb)
    r"((?:\#|b)?[^\s/]*)"  # Quality (m, maj7, dim, 7, etc.)
    r"(?:/([A-G][#b]?))?"  # Optional bass note (/C, /F#, /Bb)
    r"$",
    re.IGNORECASE,
)

_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}

# IDMT chord quality strings -> 277-class Harte quality
CHORD_QUALITY_MAP: dict[str, str] = {
    "": "maj",
    "maj": "maj",
    "M": "maj",
    "major": "maj",
    "m": "min",
    "min": "min",
    "mi": "min",
    "minor": "min",
    "-": "min",
    "7": "7",
    "dom7": "7",
    "M7": "maj7",
    "maj7": "maj7",
    "Δ7": "maj7",
    "m7": "min7",
    "min7": "min7",
    "mi7": "min7",
    "-7": "min7",
    "dim": "dim",
    "°": "dim",
    "aug": "aug",
    "+": "aug",
    "dim7": "dim7",
    "°7": "dim7",
    "m7b5": "m7b5",
    "ø": "m7b5",
    "aug7": "aug7",
    "+7": "aug7",
    "sus4": "sus4",
    "sus2": "sus2",
    "7sus4": "7sus4",
    "9": "9",
    "maj9": "maj9",
    "M9": "maj9",
    "min9": "min9",
    "m9": "min9",
    "-9": "min9",
    "6": "6",
    "m6": "min6",
    "add9": "add9",
    "madd9": "madd9",
    "7#9": "7#9",
    "7b9": "7b9",
    "7#11": "7#11",
    "7b5": "7b5",
    "7#5": "7#5",
    "alt7": "alt7",
}

# Extract instrument from path segments
INSTRUMENT_PATH_MAP: dict[str, str] = {
    "acoustic_mic": "acoustic",
    "acoustic_pickup": "acoustic",
    "Career SG": "electric_clean",
    "Ibanez 2820": "electric_clean",
}

# Tempo context from path (fast/slow)
STYLE_PATH_MAP: dict[str, str] = {
    "fast": "strum",
    "slow": "arpeggio",
}


def _normalize_root(root: str) -> str | None:
    root = root.capitalize()
    if root in _FLAT_TO_SHARP:
        return _FLAT_TO_SHARP[root]
    if root.endswith("b"):
        alt = root[:-1] + "b"
        if alt in _FLAT_TO_SHARP:
            return _FLAT_TO_SHARP[alt]
    if root not in ROOT_NOTES:
        # Try uppercase
        root = root.upper()
        if root not in ROOT_NOTES:
            return None
    return root


def _parse_chord_symbol(symbol: str) -> str | None:
    """Parse IDMT chord symbol to Harte format (Root:quality).

    Handles formats like: G, D7, Bmin, D7/C, Bmin/Gb, F#maj7, NC.
    Returns None for NC (no chord) or unparseable symbols.
    """
    symbol = symbol.strip()
    if not symbol or symbol == "NC" or symbol == "N":
        return None

    m = FULL_CHORD_REGEX.match(symbol)
    if not m:
        return None

    root_raw = m.group(1)
    quality_raw = m.group(2)
    # bass_raw = m.group(3)  # Not needed for chord label

    root = _normalize_root(root_raw)
    if root is None:
        return None

    quality = CHORD_QUALITY_MAP.get(quality_raw.lower())
    if quality is None:
        quality = "maj"

    return f"{root}:{quality}"


def _extract_chord_info(filename: str) -> dict | None:
    """Parse a chord filename like 'C_major_arpeggio_acoustic.wav'.

    Filename patterns:
        {root}[#|b]_{quality}_{style}_{instrument}.wav
        single_{root}{octave}_{style}_{instrument}.wav

    Returns dict with root, quality, style, instrument, and is_single_note
    (only present when True). Returns None if the root cannot be parsed.
    """
    stem = Path(filename).stem
    parts = stem.split("_")
    if not parts:
        return None

    info: dict = {
        "root": None,
        "quality": "maj",
        "style": "strum",
        "instrument": "acoustic",
    }

    if parts[0] == "single":
        info["is_single_note"] = True
        parts = parts[1:]

    if not parts:
        return None

    # First token holds the root with optional sharp/flat and a possible
    # quality/octave suffix (e.g., "G7", "C4", "Bb", "F#").
    root_token = parts[0]
    m = re.match(r"^([A-G][#b]?)(.*)$", root_token)
    if m is None:
        return None
    root = _normalize_root(m.group(1))
    if root is None:
        return None
    info["root"] = root
    qual_suffix = m.group(2)

    # In single-note clips the trailing digits are an octave number, not a
    # quality; the quantization step assigns a one-tick duration.
    if qual_suffix and not info.get("is_single_note"):
        mapped = CHORD_QUALITY_MAP.get(qual_suffix.lower())
        if mapped:
            info["quality"] = mapped

    _STYLE_TOKENS = {"arpeggio", "strum", "picked"}
    _INSTRUMENT_TOKENS = {
        "acoustic": "acoustic",
        "electric": "electric_clean",
        "distortion": "electric_distortion",
    }

    for part in parts[1:]:
        if part in _STYLE_TOKENS:
            info["style"] = part
            continue
        if part in _INSTRUMENT_TOKENS:
            info["instrument"] = _INSTRUMENT_TOKENS[part]
            continue
        # Quality tokens like "major", "minor", "maj7", "dim", "aug".
        mapped = CHORD_QUALITY_MAP.get(part.lower())
        if mapped and mapped != info["quality"]:
            info["quality"] = mapped
        # Unknown tokens (e.g., "bowing") fall through to the defaults.

    return info


def _build_chord_label(root: str, quality: str) -> str:
    """Format a chord label in the canonical Harte 'root:quality' form."""
    return f"{root}:{quality}"


def _extract_instrument(path_parts: list[str]) -> str:
    for part in path_parts:
        if part in INSTRUMENT_PATH_MAP:
            return INSTRUMENT_PATH_MAP[part]
    return "acoustic"


def _extract_style(path_parts: list[str]) -> str:
    for part in path_parts:
        if part in STYLE_PATH_MAP:
            return STYLE_PATH_MAP[part]
    return "strum"


def _find_audio_for_csv(csv_path: Path, dataset_dir: Path) -> Path | None:
    """Find the matching audio file for a chord CSV annotation file.

    CSV path: .../annotation/chords/<name>.csv
    Audio path: .../audio/<name>.wav
    """
    stem = csv_path.stem
    audio_dir = csv_path.parent.parent.parent / "audio"
    if not audio_dir.exists():
        return None
    wav_path = audio_dir / f"{stem}.wav"
    return wav_path if wav_path.exists() else None


def parse_chord_csv(csv_path: Path) -> list[dict] | None:
    """Parse a chord CSV annotation file into timeline entries.

    CSV format: timestamp,measure.beat[:chord_symbol]
    Only entries with ':' contain chord info.
    Continuation entries (without ':') use the previous chord.
    """
    entries: list[dict] = []
    timestamps: list[float] = []
    chords: list[str | None] = []

    with open(csv_path, "r") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not row[0].strip():
                continue
            try:
                ts = float(row[0].strip())
            except (ValueError, IndexError):
                continue

            timestamps.append(ts)

            if len(row) > 1 and ":" in row[1]:
                chord_str = row[1].split(":", 1)[1].strip()
                chord_harte = _parse_chord_symbol(chord_str)
                chords.append(chord_harte)
            else:
                chords.append(None)  # continuation marker

    if not timestamps:
        return None

    # Fill forward: replace None with last known chord
    last_chord: str | None = None
    resolved: list[str | None] = []
    for c in chords:
        if c is not None:
            last_chord = c
        resolved.append(last_chord)

    # Build timeline segments: group consecutive same-chord regions
    segments: list[dict] = []
    seg_start = timestamps[0]
    seg_chord = resolved[0]

    for i in range(1, len(timestamps)):
        if resolved[i] != seg_chord or i == len(timestamps) - 1:
            seg_end = timestamps[i] if i < len(timestamps) else timestamps[-1]
            if seg_chord is not None:
                segments.append({
                    "start": seg_start,
                    "end": seg_end,
                    "chord": seg_chord,
                })
            seg_start = timestamps[i]
            seg_chord = resolved[i]

    # Handle last segment
    if seg_chord is not None:
        last_end = timestamps[-1] + 2.0  # pad 2s after last annotation
        segments.append({
            "start": seg_start,
            "end": last_end,
            "chord": seg_chord,
        })

    return segments


def scan_idmt_clips(dataset_dir: Path) -> dict[str, list[dict]]:
    """Scan IDMT dataset4 for CSV chord annotations and matching audio.

    Returns dict mapping clip_id -> list of segment dicts.
    """
    clips: dict[str, list[dict]] = {}

    if not dataset_dir.exists():
        print(f"  [WARN] Dataset directory not found: {dataset_dir}")
        return clips

    chord_csv_files = sorted(dataset_dir.rglob("annotation/chords/*.csv"))

    import soundfile as sf

    for csv_path in chord_csv_files:
        # Build clip_id from relative path
        rel = csv_path.relative_to(dataset_dir)
        clip_id = str(rel.parent.parent.parent.name) + "_" + rel.stem.replace(" ", "_")

        # Find matching audio
        wav_path = _find_audio_for_csv(csv_path, dataset_dir)
        if wav_path is None:
            print(f"  [SKIP] {rel.name}: no matching audio file")
            continue

        # Parse CSV chord annotations
        segments = parse_chord_csv(csv_path)
        if not segments:
            print(f"  [SKIP] {rel.name}: no parseable chord annotations")
            continue

        # Get duration
        try:
            sfinfo = sf.info(str(wav_path))
            duration = sfinfo.duration
        except Exception as e:
            print(f"  [WARN] {rel.name}: {e}")
            continue

        # Clamp last segment end to actual duration
        if segments:
            segments[-1]["end"] = min(segments[-1]["end"], duration)

        # Extract metadata from path
        path_parts = str(rel).replace("\\", "/").split("/")
        instrument = _extract_instrument(path_parts)
        style = _extract_style(path_parts)

        # Enrich segments with metadata
        for seg in segments:
            seg["instrument"] = instrument
            seg["style"] = style
            seg["path"] = str(wav_path)

        clips[clip_id] = segments

    if clips:
        return clips

    # Fallback: when no CSV annotations are present, derive single-segment
    # timelines from audio filenames (e.g. "C_major_arpeggio_acoustic.wav").
    wav_files = sorted(dataset_dir.rglob("*.wav"))
    for wav_path in wav_files:
        info = _extract_chord_info(wav_path.name)
        if info is None or info["root"] is None:
            print(f"  [SKIP] {wav_path.name}: filename does not encode chord info")
            continue
        if info.get("is_single_note"):
            print(f"  [SKIP] {wav_path.name}: single-note clip, no chord label")
            continue
        try:
            sfinfo = sf.info(str(wav_path))
            duration = sfinfo.duration
        except Exception as e:
            print(f"  [WARN] {wav_path.name}: {e}")
            continue
        label = _build_chord_label(info["root"], info["quality"])
        clip_id = wav_path.stem
        clips[clip_id] = [{
            "start": 0.0,
            "end": duration,
            "chord": label,
            "instrument": info["instrument"],
            "style": info["style"],
            "path": str(wav_path),
        }]

    if not clips:
        print(f"  [WARN] No chord CSV files or audio clips found in {dataset_dir}")

    return clips


def save_timelines(
    clips: dict[str, list[dict]],
    output_dir: Path,
) -> None:
    """Save per-clip timelines to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for clip_id, timeline in sorted(clips.items()):
        out_path = output_dir / f"{clip_id}.json"
        with open(out_path, "w") as f:
            json.dump(timeline, f, indent=2)
        count += 1
    print(f"  Saved {count} timeline files to {output_dir}")


def print_summary(clips: dict[str, list[dict]]) -> None:
    """Print dataset summary statistics."""
    all_chords: dict[str, int] = {}
    instruments: dict[str, int] = {}
    styles: dict[str, int] = {}
    total_segments = 0

    for clip_id, segments in clips.items():
        for seg in segments:
            total_segments += 1
            if seg["chord"] is not None:
                all_chords[seg["chord"]] = all_chords.get(seg["chord"], 0) + 1
            inst = seg.get("instrument", "unknown")
            instruments[inst] = instruments.get(inst, 0) + 1
            sty = seg.get("style", "unknown")
            styles[sty] = styles.get(sty, 0) + 1

    noly_chords = len(set(
        seg["chord"] for segs in clips.values() for seg in segs
        if seg["chord"] is not None
    ))

    print(f"\nIDMT Dataset Summary:")
    print(f"  Total clips: {len(clips)}")
    print(f"  Total chord segments: {total_segments}")
    print(f"  Unique chord labels: {len(all_chords)}")
    print(f"  Instruments: {json.dumps(instruments, indent=4)}")
    print(f"  Styles: {json.dumps(styles, indent=4)}")
    if all_chords:
        top_chords = sorted(all_chords.items(), key=lambda x: -x[1])[:10]
        print(f"  Top 10 chords: {json.dumps(dict(top_chords), indent=4)}")


def main(data_dir: Path, force: bool = False) -> None:
    dataset_dir = data_dir / "idmt_smt_guitar" / "raw" / "audio" / IDMT_CHORD_DATASET
    timelines_dir = data_dir / "idmt_smt_guitar" / "processed" / "timelines"

    if not dataset_dir.exists():
        print(f"IDMT dataset4 directory not found: {dataset_dir}")
        print("Run download_idmt_smt_guitar.py first")
        sys.exit(1)

    # Check if already parsed
    existing = list(timelines_dir.glob("*.json")) if timelines_dir.exists() else []
    if not force and existing:
        print(f"[SKIP] Timelines already exist ({len(existing)} files) in {timelines_dir}")
        print("  Use --force to re-parse")
        return

    print(f"Scanning IDMT chord annotations in {dataset_dir}...")
    clips = scan_idmt_clips(dataset_dir)

    if not clips:
        print("No clips found. Check dataset directory structure.")
        return

    print(f"Found {len(clips)} chord-annotated clips")
    save_timelines(clips, timelines_dir)
    print_summary(clips)
    print(f"\nNext: python scripts/extract_idmt_cqt.py")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Parse IDMT-SMT-Guitar dataset into 277-class chord timelines")
    parser.add_argument("--data-dir", type=Path, default=IDMT_ROOT.parent.parent / "data",
                        help="Data directory root")
    parser.add_argument("--force", action="store_true",
                        help="Re-parse existing timelines")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
