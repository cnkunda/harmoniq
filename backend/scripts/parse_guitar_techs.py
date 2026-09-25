"""Parse Guitar-TECHS MIDI annotations into 277-class chord timelines.

For chord recordings (P1_chords, P2_chords): derive chord labels from MIDI
note data — the Fishman Triple Play provides per-string pitch information,
which we aggregate and match against the 277-class Harte vocabulary.

For musical excerpts (P3_music): parse MIDI note events to extract chord
progressions over time.

For scales, techniques, singlenotes: label frames as "N" (no chord).

Usage:
    python scripts/parse_guitar_techs.py [--data-dir DATA_DIR] [--force]

Output:
    <data_dir>/guitar_techs/processed/timelines/<track_id>.json
        [{start, end, chord, source, player}, ...]
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_INTERVALS, CHORD_QUALITIES, ROOT_NOTES, CHORD_TO_IDX

import pretty_midi

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "guitar_techs" / "raw"
PROCESSED_DIR = DATA_DIR / "guitar_techs" / "processed"

HOP_SEC = 0.1

# Root notes as pitch classes
ROOT_PC = {note: i for i, note in enumerate(ROOT_NOTES)}
PC_TO_ROOT = {i: note for i, note in enumerate(ROOT_NOTES)}

# Precompute interval sets for fast matching
CHORD_PC_SETS: dict[str, frozenset[int]] = {}
for qual, intervals in CHORD_INTERVALS.items():
    CHORD_PC_SETS[qual] = frozenset(interval % 12 for interval in intervals)


def _midi_pc_to_root(pc: int) -> str:
    return PC_TO_ROOT.get(pc, "C")


def _match_chord(active_pcs: set[int]) -> str | None:
    """Find the best 277-class chord label matching a set of active pitch classes.

    For each (root, quality) pair, checks how many of the chord's expected
    pitch classes are present. Returns the best match, or None if no match
    reaches the coverage threshold.

    Scoring: coverage = |intersection| / |chord_pcs|, penalized by extra notes.
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
            # Jaccard-like score: reward high overlap, penalize extra notes
            score = intersection / union if union > 0 else 0.0
            if score > best_score:
                best_score = score
                best_chord = f"{PC_TO_ROOT[root_pc]}:{quality}"

    if best_score < 0.4:
        return None
    return best_chord


def _build_midi_timeline(midi_path: Path) -> list[dict]:
    """Build chord timeline from a MIDI file.

    Extracts all note events, builds active pitch sets at HOP_SEC resolution,
    then matches each frame to the 277-class chord vocabulary.

    Returns:
        List of {start, end, chord} dicts.
    """
    try:
        midi = pretty_midi.PrettyMIDI(str(midi_path))
    except Exception as e:
        print(f"    [WARN] Could not parse MIDI {midi_path.name}: {e}")
        return []

    # Collect all note events across all instruments
    notes: list[tuple[float, float, int]] = []  # (start, end, pitch)
    for inst in midi.instruments:
        for note in inst.notes:
            notes.append((note.start, note.end, note.pitch))

    if not notes:
        return []

    duration = max(end for _, end, _ in notes)
    num_frames = int(np.ceil(duration / HOP_SEC)) + 1

    frame_chords: list[str | None] = [None] * num_frames

    for start_t, end_t, pitch in notes:
        pc = pitch % 12
        frame_start = int(start_t / HOP_SEC)
        frame_end = int(np.ceil(end_t / HOP_SEC))
        for f in range(frame_start, min(frame_end, num_frames)):
            if frame_chords[f] is None:
                frame_chords[f] = set()
            if isinstance(frame_chords[f], set):
                frame_chords[f].add(pc)

    # Match each frame's pitch set to a chord label
    for f in range(num_frames):
        pcs = frame_chords[f]
        if isinstance(pcs, set) and pcs:
            frame_chords[f] = _match_chord(pcs)
        else:
            frame_chords[f] = None

    # Merge consecutive same-chord frames into segments
    segments: list[dict] = []
    seg_start = 0.0
    seg_chord = frame_chords[0]

    for f in range(1, num_frames):
        current_chord = frame_chords[f]
        if current_chord != seg_chord:
            seg_end = f * HOP_SEC
            if seg_chord is not None:
                segments.append({
                    "start": round(seg_start, 3),
                    "end": round(seg_end, 3),
                    "chord": seg_chord,
                })
            seg_start = seg_end
            seg_chord = current_chord

    # Last segment
    if seg_chord is not None:
        segments.append({
            "start": round(seg_start, 3),
            "end": round(num_frames * HOP_SEC, 3),
            "chord": seg_chord,
        })

    return segments


def _build_nochord_timeline(duration: float) -> list[dict]:
    """Build a timeline with a single 'N' segment spanning the full duration."""
    return [{
        "start": 0.0,
        "end": round(duration, 3),
        "chord": "N",
    }]


def _get_duration(wav_path: Path) -> float:
    """Get duration of a WAV file using soundfile."""
    import soundfile as sf
    try:
        info = sf.info(str(wav_path))
        return info.duration
    except Exception:
        return 0.0


def process_player_category(player: str, category: str, raw_dir: Path,
                            processed_dir: Path, force: bool = False) -> dict:
    """Process all tracks for a single (player, category) pair.

    For chords: parse MIDI to derive chord labels.
    For scales/techniques/singlenotes: label as N (no chord).
    For music: parse MIDI for chord progressions.

    Returns stats dict.
    """
    cat_dir = raw_dir / f"{player}_{category}"
    timelines_dir = processed_dir / "timelines"
    timelines_dir.mkdir(parents=True, exist_ok=True)

    if not cat_dir.exists():
        return {"player": player, "category": category, "status": "not_found"}

    midi_dir = cat_dir / "midi"
    audio_dir = cat_dir / "audio" / "directinput"

    midi_files = sorted(midi_dir.glob("*.mid")) if midi_dir.exists() else []
    wav_files = sorted(audio_dir.glob("*.wav")) if audio_dir.exists() else []

    if not midi_files and not wav_files:
        return {"player": player, "category": category, "status": "no_data"}

    track_count = 0
    chord_count = 0
    total_segments = 0

    # Build track_id from MIDI filename, or use player_category if none
    if category in ("scales", "techniques", "singlenotes"):
        # Label everything as N
        for wav in wav_files:
            label = wav.stem.replace("directinput_", "")
            track_id = f"{player}_{category}_{label}"
            out_path = timelines_dir / f"{track_id}.json"
            if out_path.exists() and not force:
                continue

            duration = _get_duration(wav)
            timeline = _build_nochord_timeline(duration)
            if timeline:
                for seg in timeline:
                    seg["source"] = f"{player}_{category}"
                    seg["player"] = player
                    seg["track_id"] = track_id
                with open(out_path, "w") as f:
                    json.dump(timeline, f, indent=2)
                track_count += 1
                total_segments += len(timeline)
    else:
        # Chords or music: parse MIDI
        for mid in midi_files:
            label = mid.stem.replace("midi_", "")
            track_id = f"{player}_{category}_{label}"
            out_path = timelines_dir / f"{track_id}.json"
            if out_path.exists() and not force:
                track_count += 1
                with open(out_path) as f:
                    timeline = json.load(f)
                    total_segments += len(timeline)
                    chord_count += sum(1 for s in timeline if s.get("chord") != "N")
                continue

            timeline = _build_midi_timeline(mid)
            if not timeline:
                continue

            for seg in timeline:
                seg["source"] = f"{player}_{category}"
                seg["player"] = player
                seg["track_id"] = track_id
                if seg.get("chord") and seg["chord"] != "N":
                    chord_count += 1

            with open(out_path, "w") as f:
                json.dump(timeline, f, indent=2)
            track_count += 1
            total_segments += len(timeline)

    return {
        "player": player,
        "category": category,
        "status": "ok",
        "tracks": track_count,
        "chord_segments": chord_count,
        "total_segments": total_segments,
    }


def main(data_dir: Path, force: bool = False) -> None:
    raw_dir = data_dir / "guitar_techs" / "raw"
    processed_dir = data_dir / "guitar_techs" / "processed"

    if not raw_dir.exists():
        print(f"Raw data directory not found: {raw_dir}")
        print("Run download_guitar_techs.py first.")
        return

    players = ["P1", "P2", "P3"]
    categories = ["chords", "scales", "techniques", "singlenotes", "music"]

    all_stats = []
    for player in players:
        for category in categories:
            print(f"Processing {player}_{category}...")
            stats = process_player_category(
                player, category, raw_dir, processed_dir, force=force
            )
            all_stats.append(stats)
            if stats["status"] == "ok":
                print(f"  {stats['tracks']} tracks, "
                      f"{stats['chord_segments']} chord segments, "
                      f"{stats['total_segments']} total segments")
            elif stats["status"] == "not_found":
                print(f"  [SKIP] Directory not found")

    # Summary
    total_tracks = sum(s.get("tracks", 0) for s in all_stats)
    total_chord_segs = sum(s.get("chord_segments", 0) for s in all_stats)
    total_segs = sum(s.get("total_segments", 0) for s in all_stats)

    print(f"\nGuitar-TECHS parsing complete:")
    print(f"  Total tracks: {total_tracks}")
    print(f"  Total segments: {total_segs}")
    print(f"  Chord-labeled segments: {total_chord_segs}")
    print(f"  Timelines: {processed_dir / 'timelines'}/")
    print(f"\nNext: python scripts/extract_guitar_techs_cqt.py")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Parse Guitar-TECHS MIDI to 277-class chord timelines")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    parser.add_argument("--force", action="store_true",
                        help="Re-parse existing timelines")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
