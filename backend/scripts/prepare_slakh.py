"""Prepare a Slakh2100-redux subset with chord + bass labels (Stage D).

Streams the 48.7 GB CC-BY-4.0 Slakh2100-redux 16 kHz archive from Zenodo and
extracts only ``TrackXXXXX/mix.flac`` + ``TrackXXXXX/all_src.mid`` for a
subset of tracks (the full archive is never stored). Chord labels are derived
from the aligned MIDI via the same pitch-set template matching used for
Guitar-TECHS/EGSet12; bass is the lowest active note. 144-bin CQT windows are
written in the v2 schema.

Splits: deterministic hash over track ids → 80 % train / 10 % val / 10 % test
(the redux archive already de-duplicates MIDI, per the Slakh maintainers).

Usage (Modal entrypoint in modal_chord_170.py; needs network + a volume)::

    python scripts/prepare_slakh.py --limit 400 --workers 8
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_labels import pitch_to_pitch_class  # noqa: E402
from app.chord_vocab_170 import (  # noqa: E402
    BASS_TO_IDX,
    BASS_VOCAB,
    N_IDX_170,
    QUALITIES_14,
    QUALITY_INTERVALS_170,
)

SLAKH_URL = "https://zenodo.org/records/7708270/files/slakh2100_redux_16k.tar.gz"
HOP_SEC = 0.1
WINDOW = 128
HOP_FRAMES = 64
NUM_BINS = 144
BINS_PER_OCTAVE = 24
JACCARD_THRESHOLD = 0.66
MIN_PITCHES = 3

# Precompute chord templates: pitch-class offsets per 170-class chord.
_CHORD_TEMPLATES = []
for _quality_index, _quality in enumerate(QUALITIES_14):
    _intervals = {interval % 12 for interval in QUALITY_INTERVALS_170[_quality]}
    for _root_index in range(12):
        _CHORD_TEMPLATES.append(
            (frozenset((_root_index + interval) % 12 for interval in _intervals),
             _quality_index * 12 + _root_index)
        )


def _split_for(track_id: str) -> str:
    score = int(hashlib.sha256(f"slakh:{track_id}".encode()).hexdigest(), 16) % 100
    if score < 10:
        return "test"
    if score < 20:
        return "val"
    return "train"


def _jaccard(a: frozenset[int], b: frozenset[int]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _chord_for(pitch_classes: frozenset[int]) -> int:
    if len(pitch_classes) < MIN_PITCHES:
        return N_IDX_170
    best_label = N_IDX_170
    best_score = 0.0
    for tones, label in _CHORD_TEMPLATES:
        score = _jaccard(pitch_classes, tones)
        if score > best_score:
            best_score = score
            best_label = label
    return best_label if best_score >= JACCARD_THRESHOLD else N_IDX_170


# ---------------------------------------------------------------------------
# Streaming extraction
# ---------------------------------------------------------------------------


def extract_subset(limit: int, raw_dir: Path, url: str = SLAKH_URL) -> dict:
    """Stream the archive and extract mix.flac + all_src.mid for ``limit`` tracks."""
    import requests

    raw_dir.mkdir(parents=True, exist_ok=True)
    existing = {p.name for p in raw_dir.iterdir() if p.is_dir()}
    if len(existing) >= limit:
        return {"status": "cached", "tracks": len(existing)}
    report = {"status": "ok", "extracted": 0, "skipped_existing": 0, "bytes": 0}
    splits_path = raw_dir / "slakh_splits.json"
    split_map: dict[str, str] = {}
    if splits_path.exists():
        try:
            split_map = json.loads(splits_path.read_text())
        except Exception:
            split_map = {}
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    wanted_names = ("mix.flac", "all_src.mid")
    track_pattern = re.compile(r"^Track\d+$")
    seen_tracks: set[str] = set()
    inspected = 0
    try:
        with tarfile.open(fileobj=response.raw, mode="r|gz") as archive:
            for member in archive:
                if inspected < 15:
                    print(f"  [tar] {member.name}", flush=True)
                    inspected += 1
                parts = [part for part in member.name.split("/") if part]
                if "omitted" in parts:
                    continue
                track = next((part for part in parts if track_pattern.match(part)), None)
                if track is None or parts[-1] not in wanted_names:
                    continue
                parent = parts[parts.index(track) - 1] if parts.index(track) > 0 else "train"
                if parent in ("train", "validation", "test"):
                    split_map[track] = "val" if parent == "validation" else parent
                track_dir = raw_dir / track
                target = track_dir / parts[-1]
                if track_dir.exists() and (track_dir / "mix.flac").exists() \
                        and (track_dir / "all_src.mid").exists():
                    report["skipped_existing"] += 1
                    seen_tracks.add(track)
                    continue
                track_dir.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    continue
                with open(target, "wb") as handle:
                    while True:
                        chunk = source.read(1 << 20)
                        if not chunk:
                            break
                        handle.write(chunk)
                        report["bytes"] += len(chunk)
                if (track_dir / "mix.flac").exists() and (track_dir / "all_src.mid").exists():
                    if track not in seen_tracks:
                        seen_tracks.add(track)
                        report["extracted"] += 1
                if len(seen_tracks) >= limit:
                    break
    finally:
        response.close()
    splits_path.write_text(json.dumps(split_map, indent=2))
    report["tracks"] = len(seen_tracks)
    report["split_counts"] = {
        s: sum(1 for v in split_map.values() if v == s)
        for s in ("train", "val", "test")
    }
    return report


# ---------------------------------------------------------------------------
# Audio + MIDI → CQT windows
# ---------------------------------------------------------------------------


def _note_events(midi_path: Path) -> list[tuple[float, float, float]]:
    import pretty_midi

    midi = pretty_midi.PrettyMIDI(str(midi_path))
    return [
        (float(note.start), float(note.end), float(note.pitch))
        for instrument in midi.instruments
        if not instrument.is_drum
        for note in instrument.notes
    ]


def _process_track(track_dir: Path, out_dir: Path, splits_path: Path | None = None,
                   window: int = WINDOW, hop_frames: int = HOP_FRAMES) -> dict:
    import librosa

    mix_path = track_dir / "mix.flac"
    midi_path = track_dir / "all_src.mid"
    if not mix_path.exists() or not midi_path.exists():
        return {"track": track_dir.name, "status": "missing_inputs"}
    try:
        notes = _note_events(midi_path)
        if not notes:
            return {"track": track_dir.name, "status": "no_notes"}
        y, sr = librosa.load(str(mix_path), sr=16000, mono=True)
        if y.size == 0:
            return {"track": track_dir.name, "status": "empty_audio"}
        hop = int(sr * HOP_SEC)
        cqt = np.abs(librosa.cqt(y=y, sr=sr, hop_length=hop, n_bins=NUM_BINS,
                                 bins_per_octave=BINS_PER_OCTAVE,
                                 fmin=librosa.note_to_hz("C1"))).T.astype(np.float32)
        norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
        feats = cqt / norms
        n_frames = len(feats)
        half = window // 2
        padded = np.concatenate([np.zeros((half, NUM_BINS), dtype=np.float32), feats,
                                 np.zeros((half, NUM_BINS), dtype=np.float32)], axis=0)
        n_windows = max(1, int(np.ceil(n_frames / hop_frames)))
        windows = np.zeros((n_windows, window, NUM_BINS), dtype=np.float32)
        centres = np.arange(n_windows, dtype=np.float64) * hop_frames * HOP_SEC
        labels = np.full(n_windows, N_IDX_170, dtype=np.int64)
        bass = np.full(n_windows, 12, dtype=np.int64)  # BASS_X_IDX
        for index, centre in enumerate(centres):
            start = index * hop_frames
            windows[index] = padded[start:start + window]
            active = [pitch for (s, e, pitch) in notes if s <= centre < e]
            if not active:
                continue
            pitch_classes = frozenset(pitch_to_pitch_class(p) for p in active)
            labels[index] = _chord_for(pitch_classes)
            bass[index] = BASS_TO_IDX[BASS_VOCAB[pitch_to_pitch_class(min(active)) % 12]]
        track_id = track_dir.name
        # The subset is streamed in archive order (validation-first), so the
        # official split is not representative; redux already de-duplicates
        # MIDI, making a deterministic hash split safe and balanced.
        split = _split_for(track_id)
        np.savez_compressed(
            out_dir / f"{track_id}.npz",
            features=windows,
            labels170=labels,
            bass_labels=bass,
            confidence=np.ones(n_windows, dtype=np.float32),
            center_times=centres.astype(np.float32),
            track_id=np.bytes_(track_id.encode()),
            split=np.bytes_(split.encode()),
            source=np.bytes_(b"slakh"),
            teacher=np.bytes_(b"midi"),
            loss_weight=np.float64(1.0),
            schema_version=np.int64(2),
        )
        return {
            "track": track_id, "status": "ok", "split": split,
            "windows": int(n_windows),
            "n_windows": int(np.sum(labels == N_IDX_170)),
            "bass_known": int(np.sum(bass != 12)),
        }
    except Exception as exc:
        return {"track": track_dir.name, "status": f"error:{type(exc).__name__}: {exc}"}


def parse_and_extract(raw_dir: Path, out_dir: Path, workers: int = 8,
                      limit: int = 0, window: int = WINDOW,
                      hop_frames: int = HOP_FRAMES) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    track_dirs = sorted(p for p in Path(raw_dir).iterdir() if p.is_dir())
    if limit:
        track_dirs = track_dirs[:limit]
    splits_path = Path(raw_dir) / "slakh_splits.json"
    results: list[dict] = []
    if workers <= 1:
        results = [_process_track(t, out_dir, splits_path, window, hop_frames)
                   for t in track_dirs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_process_track, t, out_dir, splits_path,
                                   window, hop_frames): t
                       for t in track_dirs}
            for future in as_completed(futures):
                results.append(future.result())
    ok = [r for r in results if r.get("status") == "ok"]
    qualities = {}
    for track_dir in track_dirs:
        path = out_dir / f"{track_dir.name}.npz"
        if not path.exists():
            continue
        labels = np.load(path)["labels170"]
        for label in labels:
            if int(label) < N_IDX_170:
                quality = QUALITIES_14[int(label) // 12]
                qualities[quality] = qualities.get(quality, 0) + 1
    return {
        "tracks_ok": len(ok),
        "tracks_failed": len(results) - len(ok),
        "windows": int(sum(r.get("windows", 0) for r in ok)),
        "n_windows": int(sum(r.get("n_windows", 0) for r in ok)),
        "bass_known": int(sum(r.get("bass_known", 0) for r in ok)),
        "splits": {s: sum(1 for r in ok if r.get("split") == s)
                   for s in ("train", "val", "test")},
        "qualities": qualities,
        "out_dir": str(out_dir),
        "errors": [r for r in results if r.get("status") != "ok"][:5],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--raw-dir", type=Path,
                        default=_BACKEND_DIR / "data" / "chord170" / "slakh_raw")
    parser.add_argument("--out-dir", type=Path,
                        default=_BACKEND_DIR / "data" / "chord170" / "slakh")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--window", type=int, default=WINDOW)
    parser.add_argument("--hop", type=int, default=HOP_FRAMES)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)

    download_report = {"status": "skipped"}
    if not args.skip_download:
        download_report = extract_subset(args.limit, args.raw_dir)
        print(json.dumps(download_report, indent=2), flush=True)
    report = {
        "download": download_report,
        "extract": parse_and_extract(args.raw_dir, args.out_dir / "processed" / "cqt",
                                     workers=args.workers, limit=args.limit,
                                     window=args.window, hop_frames=args.hop),
    }
    print(json.dumps(report, indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
