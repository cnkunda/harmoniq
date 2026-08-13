#!/usr/bin/env python3
"""Real dataset preparation for chord model training (Commit 101).

Sources:
  - GuitarSet (official chord annotations in JAMS, real guitar audio, 180
    comp tracks across 6 players) - audio + annotation live under
    ``backend/data/guitarset/raw``.
  - Isophonics annotations (Beatles/Queen/Zweieck/Carole King ``.lab``
    files under ``backend/data/annotations``) with audio resolved at
    download time from YouTube via yt-dlp using the committed manifest
    ``backend/data/manifests/isophonics_yt.json``.

EGSET is intentionally excluded: its JAMS files carry only pitch contours
and its GP files contain no chord names, so no trustworthy chord ground
truth is available (the ``egset12/processed/timelines`` were model
pseudo-labels, not annotations).

Feature recipe matches production inference exactly
(``app/chord_inference._run_tflite_raw``): 36-bin CQT @ 44.1kHz, 0.1s hop,
per-frame L1 normalisation, 4-bin bass channel concat -> (T, 40).

Commands:
    status              Print what is present per source
    download            Resolve + download YouTube audio per manifest
    prep                Extract CQT, align labels, gate, cache npz + manifest
    split               Assign train/val/test by artist policy
    stats               Vocabulary mapping coverage over all annotations
    all                 download + prep + split

Usage:
    cd backend && python scripts/prepare_real_datasets.py all --limit 8
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from real_label_vocab import (  # noqa: E402
    NO_CHORD_IDX,
    annotation_to_class_index,
    parse_annotation_label,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("harmoniq.prepare_real_datasets")

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
REAL_DIR = DATA_DIR / "real_audio"
YT_AUDIO_DIR = REAL_DIR / "youtube"
PROCESSED_DIR = REAL_DIR / "processed"
MANIFEST_DIR = DATA_DIR / "manifests"
YT_MANIFEST = MANIFEST_DIR / "isophonics_yt.json"
SPLIT_POLICY = MANIFEST_DIR / "split_policy.json"

HOP_SEC = 0.1
SR = 44100
N_BINS = 36
BINS_PER_OCTAVE = 12
BASS_BINS = 4
FEATURE_DIM = N_BINS + BASS_BINS          # 40
MIN_EVENT_S = 0.1                          # label quality gate (Commit 102 methodology)
SILENCE_ENERGY = 1e-6
MIN_USABLE_FRAMES = 32
MIN_COVERAGE = 0.05
MIN_TRACK_S = 30.0
DURATION_MATCH = (0.7, 1.5)

DEFAULT_SPLIT_POLICY = {
    "guitarset": {
        "00": "train", "01": "train", "02": "train", "03": "test",
        "04": "train", "05": "val",
    },
    "isophonics_yt": {
        "Beatles": "train", "Queen": "train", "Zweieck": "test",
        "Carole_King": "val",
    },
}


def extract_chord_features(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Extract (T, 40) chord features matching ``chord_inference._run_tflite_raw``.

    Returns (features, frame_energy) where frame_energy is the pre-normalisation
    absolute CQT sum per frame, used to silence-gate training windows.
    """
    import librosa

    hop = int(SR * HOP_SEC)
    cqt = np.abs(librosa.cqt(y=y, sr=SR, hop_length=hop, n_bins=N_BINS, bins_per_octave=BINS_PER_OCTAVE))
    energy = cqt.sum(axis=0)
    cqt = cqt.T.astype(np.float32)
    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    cqt = cqt / norms
    bass = cqt[:, :BASS_BINS]
    features = np.concatenate([cqt, bass], axis=1)
    return features.astype(np.float32), energy.astype(np.float32)


def parse_lab_events(lab_path: Path) -> list[dict]:
    """Parse an Isophonics-style .lab file into chord events."""
    events = []
    for raw in lab_path.read_text(errors="ignore").splitlines():
        parts = raw.strip().split()
        if len(parts) < 3:
            continue
        try:
            start, end = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        label = " ".join(parts[2:])
        events.append({"start": start, "end": end, "label": label})
    events.sort(key=lambda e: e["start"])
    return events


def jams_chord_events(jams_path: Path) -> list[dict]:
    """Extract chord events from a GuitarSet JAMS file."""
    import json

    data = json.loads(jams_path.read_text())
    for annotation in data.get("annotations", []):
        if annotation.get("namespace") == "chord":
            events = []
            for d in annotation.get("data", []):
                events.append({
                    "start": d["time"],
                    "end": d["time"] + d["duration"],
                    "label": d["value"],
                })
            events.sort(key=lambda e: e["start"])
            return events
    return []


def events_to_frame_labels(
    n_frames: int,
    events: list[dict],
    hop_sec: float = HOP_SEC,
    min_event_s: float = MIN_EVENT_S,
) -> tuple[np.ndarray, np.ndarray]:
    """Align chord events to feature frames.

    Returns (labels, center_mask): labels is the per-frame class index
    (``NO_CHORD_IDX`` outside events); center_mask marks frames whose covering
    event is at least ``min_event_s`` long (candidate window centers).
    """
    labels = np.full(n_frames, NO_CHORD_IDX, dtype=np.int32)
    mask = np.zeros(n_frames, dtype=bool)
    for ev in events:
        cls = annotation_to_class_index(ev["label"])
        i0 = max(0, int(np.floor(ev["start"] / hop_sec)))
        i1 = min(n_frames, int(np.ceil(ev["end"] / hop_sec)))
        if i1 <= i0:
            continue
        labels[i0:i1] = cls
        if ev["end"] - ev["start"] >= min_event_s:
            mask[i0:i1] = True
    return labels, mask


def iter_guitarset_tracks() -> list[dict]:
    """Yield GuitarSet comp tracks with audio + JAMS annotation paths."""
    audio_dir = DATA_DIR / "guitarset" / "raw" / "audio_mono-mix"
    ann_dir = DATA_DIR / "guitarset" / "raw" / "annotation"
    tracks = []
    for wav in sorted(audio_dir.glob("*_comp_mix.wav")):
        jams = ann_dir / (wav.name.replace("_comp_mix.wav", "_comp.jams"))
        if not jams.exists():
            logger.warning("Missing JAMS for %s, skipping", wav.name)
            continue
        tracks.append({
            "track_id": wav.name.replace("_comp_mix.wav", ""),
            "source": "guitarset",
            "artist": wav.name[:2],
            "audio": wav,
            "lab": jams,
        })
    return tracks


def iter_isophonics_tracks() -> list[dict]:
    """Yield manifest tracks that already have downloaded audio."""
    tracks = []
    if not YT_MANIFEST.exists():
        return tracks
    manifest = json.loads(YT_MANIFEST.read_text())
    for entry in manifest["tracks"]:
        artist_dir = YT_AUDIO_DIR / entry["artist"]
        audio = artist_dir / f"{entry['id']}.wav"
        if not audio.exists():
            logger.debug("No audio yet for %s, skipping", entry["id"])
            continue
        lab = DATA_DIR / "annotations" / "isophonics" / entry["artist"] / entry["lab"]
        if not lab.exists():
            logger.warning("Missing lab %s for %s, skipping", entry["lab"], entry["id"])
            continue
        tracks.append({
            "track_id": entry["id"],
            "source": "isophonics_yt",
            "artist": entry["artist"],
            "audio": audio,
            "lab": lab,
        })
    return tracks


def load_audio(path: Path) -> np.ndarray:
    import librosa

    y, _ = librosa.load(str(path), sr=SR, mono=True)
    return y


def sanitize_track_id(track_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in track_id)


def download_youtube(limit: int | None = None, force: bool = False) -> dict:
    """Resolve + download YouTube audio for the curated Isophonics manifest."""
    import yt_dlp

    if not YT_MANIFEST.exists():
        logger.error("Manifest %s not found", YT_MANIFEST)
        return {"downloaded": 0, "skipped": [], "failed": []}

    manifest = json.loads(YT_MANIFEST.read_text())
    metadata_path = REAL_DIR / "yt_metadata.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}

    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": str(REAL_DIR / "yt_tmp" / "%(id)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
        }],
        "postprocessor_args": ["-ar", str(SR), "-ac", "1"],
    }

    targets = [t for t in manifest["tracks"] if force or not (YT_AUDIO_DIR / t["artist"] / f"{t['id']}.wav").exists()]
    if limit:
        targets = targets[:limit]

    result = {"downloaded": 0, "skipped": [], "failed": []}
    for entry in targets:
        lab = DATA_DIR / "annotations" / "isophonics" / entry["artist"] / entry["lab"]
        events = parse_lab_events(lab)
        lab_span = events[-1]["end"] - events[0]["start"] if events else 0.0
        if lab_span < MIN_TRACK_S:
            result["skipped"].append({"id": entry["id"], "reason": f"lab span {lab_span:.1f}s < {MIN_TRACK_S}s"})
            continue

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch5:{entry['search']}", download=False)
            candidates = info.get("entries") or []
            scored = []
            for cand in candidates:
                title = (cand.get("title") or "").lower()
                query = entry["search"].lower()
                title_ok = query.split(" ", 2)[2] in title if len(query.split(" ", 2)) > 2 else True
                duration = cand.get("duration") or 0.0
                ratio = duration / lab_span if lab_span else 0.0
                ratio_ok = DURATION_MATCH[0] <= ratio <= DURATION_MATCH[1]
                scored.append((0 if not title_ok else 1, abs(ratio - 1.0), ratio_ok, cand))
            scored.sort(key=lambda s: (-s[0], s[1]))
            selected = next((s[3] for s in scored if s[2]), None)
            if selected is None:
                result["failed"].append({"id": entry["id"], "reason": "no duration-matched candidate"})
                continue
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(selected["webpage_url"], download=True)

            tmp_wav = next((REAL_DIR / "yt_tmp").glob(f"{selected['id']}*.wav"), None)
            if tmp_wav is None:
                result["failed"].append({"id": entry["id"], "reason": "download produced no wav"})
                continue
            out_dir = YT_AUDIO_DIR / entry["artist"]
            out_dir.mkdir(parents=True, exist_ok=True)
            y = load_audio(tmp_wav)
            import soundfile as sf

            sf.write(str(out_dir / f"{entry['id']}.wav"), y, SR)
            tmp_wav.unlink(missing_ok=True)

            metadata[entry["id"]] = {
                "artist": entry["artist"],
                "title": selected.get("title"),
                "webpage_url": selected.get("webpage_url"),
                "resolved_duration_s": round(float(selected.get("duration") or 0.0), 2),
                "lab_span_s": round(lab_span, 2),
                "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            result["downloaded"] += 1
            logger.info("Downloaded %s (%.0fs, span %.0fs)", entry["id"], selected.get("duration") or 0, lab_span)
        except Exception as exc:  # noqa: BLE001
            result["failed"].append({"id": entry["id"], "reason": str(exc)[:200]})
            logger.warning("Download failed for %s: %s", entry["id"], exc)

    REAL_DIR.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2))
    return result


def prepare_tracks(tracks: list[dict], force: bool = False) -> list[dict]:
    """Extract features, align labels, gate, and cache each track."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for track in tracks:
        track_id = sanitize_track_id(track["track_id"])
        out_path = PROCESSED_DIR / f"{track_id}.npz"
        meta_path = PROCESSED_DIR / f"{track_id}.meta.json"
        if out_path.exists() and not force:
            if not meta_path.exists():
                manifest.append(_backfill_meta(track, out_path, meta_path))
            continue

        events = (
            parse_lab_events(track["lab"])
            if track["source"] == "isophonics_yt"
            else jams_chord_events(track["lab"])
        )
        plain_events = [e for e in events if e["label"].strip().upper() not in ("N", "NC")]
        if not plain_events:
            logger.warning("No chord events for %s, skipping", track["track_id"])
            continue

        y = load_audio(track["audio"])
        features, energy = extract_chord_features(y)
        n_frames = features.shape[0]
        labels, center_mask = events_to_frame_labels(n_frames, events)
        center_mask &= energy >= SILENCE_ENERGY
        n_usable = int(center_mask.sum())
        coverage = n_usable / max(n_frames, 1)
        duration_s = round(n_frames * HOP_SEC, 2)

        gate_ok = n_usable >= MIN_USABLE_FRAMES and coverage >= MIN_COVERAGE
        entry = {
            "track_id": track_id,
            "source": track["source"],
            "artist": track["artist"],
            "audio": str(track["audio"].relative_to(DATA_DIR)),
            "lab": str(track["lab"].relative_to(DATA_DIR)),
            "n_frames": n_frames,
            "n_usable": n_usable,
            "coverage": round(coverage, 4),
            "duration_s": duration_s,
            "gate_ok": bool(gate_ok),
            "reason": "" if gate_ok else "insufficient usable frames/coverage",
        }
        if not gate_ok:
            logger.warning("Track %s gated out: %s", track["track_id"], entry["reason"])

        np.savez_compressed(
            out_path,
            features=features,
            labels=labels,
            center_mask=center_mask,
            frame_times=np.arange(n_frames, dtype=np.float32) * HOP_SEC,
            artist=track["artist"],
            source=track["source"],
        )
        (PROCESSED_DIR / f"{sanitize_track_id(track['track_id'])}.meta.json").write_text(
            json.dumps(entry, indent=2)
        )
        manifest.append(entry)
        logger.info(
            "Prepared %s: %d frames, %d usable (%.1f%%), %.1fs",
            track["track_id"], n_frames, n_usable, 100 * coverage, duration_s,
        )
    return manifest


def _backfill_meta(track: dict, out_path: Path, meta_path: Path) -> dict:
    """Write a meta sidecar for an npz cache created before the sidecar existed."""
    data = np.load(out_path)
    n_usable = int(data["center_mask"].sum())
    n_frames = int(data["features"].shape[0])
    entry = {
        "track_id": sanitize_track_id(track["track_id"]),
        "source": track["source"],
        "artist": track["artist"],
        "audio": str(track["audio"].relative_to(DATA_DIR)),
        "lab": str(track["lab"].relative_to(DATA_DIR)),
        "n_frames": n_frames,
        "n_usable": n_usable,
        "coverage": round(n_usable / max(n_frames, 1), 4),
        "duration_s": round(n_frames * HOP_SEC, 2),
        "gate_ok": bool(n_usable >= MIN_USABLE_FRAMES and n_usable / max(n_frames, 1) >= MIN_COVERAGE),
        "reason": "",
        "backfilled": True,
    }
    meta_path.write_text(json.dumps(entry, indent=2))
    return entry


def rebuild_manifest() -> list[dict]:
    """Rebuild the manifest from all cached per-track metadata (crash-safe).

    The filename is canonical for the track id (sanitized at cache time),
    so it wins over the id stored inside stale sidecars.
    """
    entries = []
    for meta in sorted(PROCESSED_DIR.glob("*.meta.json")):
        try:
            entry = json.loads(meta.read_text())
            entry["track_id"] = meta.name.removesuffix(".meta.json")
            entries.append(entry)
        except json.JSONDecodeError:
            logger.warning("Corrupt meta %s, skipping", meta.name)
    return entries


def load_policy() -> dict:
    if SPLIT_POLICY.exists():
        return json.loads(SPLIT_POLICY.read_text())
    return DEFAULT_SPLIT_POLICY


def assign_splits(tracks: list[dict]) -> dict[str, dict]:
    """Assign split roles per artist; never overlaps artists across splits."""
    policy = load_policy()
    assigned: dict[str, dict] = {}
    for track in tracks:
        if not track["gate_ok"]:
            continue
        roles = policy.get(track["source"], {})
        split = roles.get(track["artist"], "train")
        assigned[track["track_id"]] = {"artist": track["artist"], "split": split, "source": track["source"]}
    return assigned


def vocab_stats() -> dict:
    """Vocabulary mapping coverage over every annotation file on disk."""
    import glob

    quality_counts: dict[str, int] = {}
    unmapped: dict[str, int] = {}
    total = mapped = 0
    for lab in glob.glob(str(DATA_DIR / "annotations" / "**" / "*.lab"), recursive=True):
        for ev in parse_lab_events(Path(lab)):
            total += 1
            parsed = parse_annotation_label(ev["label"])
            if parsed is None:
                unmapped[ev["label"]] = unmapped.get(ev["label"], 0) + 1
            else:
                quality_counts[parsed[1]] = quality_counts.get(parsed[1], 0) + 1
                mapped += 1
    return {
        "total_chords": total,
        "mapped": mapped,
        "mapped_pct": round(100 * mapped / max(total, 1), 2),
        "quality_counts": dict(sorted(quality_counts.items(), key=lambda kv: -kv[1])),
        "unmapped_top": dict(sorted(unmapped.items(), key=lambda kv: -kv[1])[:25]),
    }


def cmd_status() -> None:
    guitarset = iter_guitarset_tracks()
    yt = iter_isophonics_tracks()
    print(f"GuitarSet comp tracks: {len(guitarset)}")
    print(f"Isophonics tracks with audio: {len(yt)}")
    print(f"Processed caches: {len(list(PROCESSED_DIR.glob('*.npz')))}")
    if YT_MANIFEST.exists():
        print(f"Manifest tracks: {len(json.loads(YT_MANIFEST.read_text())['tracks'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare real datasets for chord model training (Commit 101)")
    parser.add_argument("command", choices=["status", "download", "prep", "split", "stats", "all"])
    parser.add_argument("--limit", type=int, default=None, help="Max YouTube tracks to download")
    parser.add_argument("--force", action="store_true", help="Re-download / re-process existing artifacts")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REAL_DIR.mkdir(parents=True, exist_ok=True)

    if args.command in ("status",):
        cmd_status()
        return

    if args.command in ("download", "all"):
        result = download_youtube(limit=args.limit, force=args.force)
        print(f"download: {result['downloaded']} ok, {len(result['failed'])} failed, {len(result['skipped'])} skipped")

    if args.command in ("prep", "all"):
        tracks = iter_guitarset_tracks() + iter_isophonics_tracks()
        prepare_tracks(tracks, force=args.force)
        manifest_path = REAL_DIR / "manifest.json"
        manifest_path.write_text(json.dumps(rebuild_manifest(), indent=2))
        print(f"prep: manifest rebuilt ({len(rebuild_manifest())} tracks) -> {manifest_path}")

    if args.command in ("split", "all"):
        manifest_path = REAL_DIR / "manifest.json"
        if not manifest_path.exists():
            logger.error("Run prep first (no manifest at %s)", manifest_path)
            sys.exit(1)
        tracks = json.loads(manifest_path.read_text())
        assigned = assign_splits(tracks)
        split_path = REAL_DIR / "split.json"
        split_path.write_text(json.dumps(assigned, indent=2))
        from collections import Counter

        print("split:", dict(Counter(a["split"] for a in assigned.values())))
        print(f"  -> {split_path}")

    if args.command in ("stats",):
        stats = vocab_stats()
        print(f"mapped {stats['mapped']}/{stats['total_chords']} ({stats['mapped_pct']}%)")
        for quality, count in stats["quality_counts"].items():
            print(f"  {quality:8s} {count}")
        (REAL_DIR / "vocab_stats.json").write_text(json.dumps(stats, indent=2))
        print(f"  -> {REAL_DIR / 'vocab_stats.json'}")


if __name__ == "__main__":
    main()