"""Build the W1 real-audio dataset manifest.

Run from ``backend/``::

    python scripts/build_w1_manifest.py

Output: ``docs/eval/w1_dataset_manifest.json`` (committed, paths relative
to ``backend/``).

The manifest includes every real-audio track available locally. Tracks
that already have human/weak labels keep them; unlabeled tracks are marked
``label_status="none"`` for the MT3/teacher pseudo-labeler.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.data_engine.splits import deterministic_split  # noqa: E402
from app.evaluation.manifest import load_manifest as load_eval_manifest  # noqa: E402

DATA_DIR = _BACKEND_DIR / "data"
_EVAL_MANIFEST = _REPO_ROOT / "docs" / "eval" / "amt_manifest.json"
_OUT = _REPO_ROOT / "docs" / "eval" / "w1_dataset_manifest.json"


def _rel(path: Path) -> str:
    # relpath/normpath avoids per-file stat calls on the WSL /mnt/c mount.
    return Path(os.path.normpath(os.path.relpath(path, _BACKEND_DIR))).as_posix()


def _eval_split_map() -> dict[str, str]:
    """Map eval audio paths (backend-relative) to their split.

    Keyed by the manifest's relative ``audio_path`` so no filesystem
    resolution is needed while building the W1 manifest.
    """
    if not _EVAL_MANIFEST.is_file():
        raise SystemExit(
            "W0 eval manifest missing; run scripts/build_eval_manifest.py first "
            f"({_EVAL_MANIFEST})"
        )
    manifest = load_eval_manifest(_EVAL_MANIFEST)
    mapping: dict[str, str] = {}
    for track in manifest.tracks:
        mapping[os.path.normpath(track.audio_path)] = track.split
    return mapping


def _guitarset_tracks(eval_splits: dict[str, str]) -> list[dict[str, Any]]:
    root = DATA_DIR / "guitarset"
    timelines = root / "processed" / "timelines"
    audio_dir = root / "raw" / "audio_mono-mix"
    annotation_dir = root / "raw" / "annotation"
    if not timelines.is_dir():
        print("[SKIP] GuitarSet timelines not found")
        return []

    tracks: list[dict[str, Any]] = []
    for timeline in sorted(timelines.glob("*.json")):
        stem = timeline.stem
        audio = audio_dir / f"{stem}_mix.wav"
        jams = annotation_dir / f"{stem}.jams"
        if not audio.is_file() or not jams.is_file():
            continue
        split = eval_splits.get(_rel(audio)) or deterministic_split(
            f"guitarset:{stem}"
        )
        tracks.append(
            {
                "id": f"guitarset:{stem}",
                "audio_path": _rel(audio),
                "source": "guitarset",
                "licence_id": "CC-BY-4.0",
                "split": split,
                "label_status": "human",
                "label_channels": ["chord", "solo"],
                "chord_label_path": _rel(timeline),
                "note_label_path": _rel(jams),
                "category": "acoustic",
                "recording_type": "studio",
                "instrument_count": 1,
                "notes": "Hexaphonic GuitarSet annotations merged per track.",
            }
        )
    print(f"[OK] GuitarSet: {len(tracks)} track(s)")
    return tracks


def _guitar_techs_tracks(eval_splits: dict[str, str]) -> list[dict[str, Any]]:
    root = DATA_DIR / "guitar_techs"
    timelines = root / "processed" / "timelines"
    if not timelines.is_dir():
        print("[SKIP] Guitar-TECHS timelines not found")
        return []

    tracks: list[dict[str, Any]] = []
    for timeline in sorted(timelines.glob("*.json")):
        track_id = timeline.stem
        parts = track_id.split("_", 2)
        if len(parts) != 3:
            continue
        source = f"{parts[0]}_{parts[1]}"
        label = parts[2]
        midi = root / "raw" / source / "midi" / f"midi_{label}.mid"
        if not midi.is_file():
            continue

        direct = root / "raw" / source / "audio" / "directinput" / f"directinput_{label}.wav"
        micamp = root / "raw" / source / "audio" / "micamp" / f"micamp_{label}.wav"
        direct_split = (
            eval_splits.get(_rel(direct)) if direct.is_file() else None
        ) or deterministic_split(f"guitar_techs:{track_id}")

        for perspective, audio in (("directinput", direct), ("micamp", micamp)):
            if not audio.is_file():
                continue
            tracks.append(
                {
                    "id": f"guitar_techs:{track_id}:{perspective}",
                    "audio_path": _rel(audio),
                    "source": "guitar_techs",
                    "licence_id": "CC-BY-4.0",
                    "split": direct_split,
                    "label_status": "human",
                    "label_channels": ["chord", "solo"],
                    "chord_label_path": _rel(timeline),
                    "note_label_path": _rel(midi),
                    "category": parts[1],
                    "recording_type": "studio",
                    "instrument_count": 1,
                    "notes": f"Electric guitar; {perspective} perspective.",
                }
            )
    print(f"[OK] Guitar-TECHS: {len(tracks)} track(s)")
    return tracks


def _egset12_tracks(eval_splits: dict[str, str]) -> list[dict[str, Any]]:
    root = DATA_DIR / "egset12"
    timelines = root / "processed" / "timelines"
    raw = root / "raw"
    if not timelines.is_dir():
        print("[SKIP] EGSet12 timelines not found")
        return []
    tracks: list[dict[str, Any]] = []
    for timeline in sorted(timelines.glob("*.json")):
        stem = timeline.stem
        audio = raw / f"{stem}.wav"
        jams = raw / f"{stem}.jams"
        if not audio.is_file() or not jams.is_file():
            continue
        split = eval_splits.get(_rel(audio)) or deterministic_split(
            f"egset12:{stem}"
        )
        tracks.append(
            {
                "id": f"egset12:{stem}",
                "audio_path": _rel(audio),
                "source": "egset12",
                "licence_id": "CC-BY-4.0",
                "split": split,
                "label_status": "human",
                "label_channels": ["chord", "solo"],
                "chord_label_path": _rel(timeline),
                "note_label_path": _rel(jams),
                "category": "electric",
                "recording_type": "studio",
                "instrument_count": 1,
                "notes": "Jazz/funk/twelve-tone electric guitar.",
            }
        )
    print(f"[OK] EGSet12: {len(tracks)} track(s)")
    return tracks


def _rwc_tracks(eval_splits: dict[str, str]) -> list[dict[str, Any]]:
    root = DATA_DIR / "rwc"
    timelines = root / "processed" / "timelines"
    if not timelines.is_dir():
        print("[SKIP] RWC-P timelines not found")
        return []
    metadata: dict[str, dict[str, str]] = {}
    metadata_path = root / "raw" / "metadata.csv"
    if metadata_path.is_file():
        import csv

        with metadata_path.open("r", encoding="utf-8", newline="") as handle:
            metadata = {
                row["RWCID"]: row
                for row in csv.DictReader(handle, delimiter=";")
                if row.get("RWCID")
            }

    rwc_audio = {
        path.stem: path for path in root.rglob("*.wav")
    } if root.is_dir() else {}
    tracks: list[dict[str, Any]] = []
    for timeline in sorted(timelines.glob("*.json")):
        stem = timeline.stem
        audio = rwc_audio.get(stem)
        if audio is None:
            continue
        split = eval_splits.get(_rel(audio)) or deterministic_split(
            f"rwc:{stem}"
        )
        meta = metadata.get(stem, {})
        live = [
            item.strip()
            for item in (meta.get("LiveInstruments") or "").split(",")
            if item.strip()
        ]
        count = len(live)
        if (meta.get("SingerInformation") or "").strip():
            count += 1
        if (meta.get("DrumInformation") or "").strip():
            count += 1
        tracks.append(
            {
                "id": f"rwc:{stem}",
                "audio_path": _rel(audio),
                "source": "rwc_p",
                "licence_id": "CC-BY-NC-4.0",
                "split": split,
                "label_status": "human",
                "label_channels": ["chord"],
                "chord_label_path": _rel(timeline),
                "category": (meta.get("GenreSub") or meta.get("GenreMain") or "popular"),
                "recording_type": "studio",
                "instrument_count": max(1, count),
                "notes": "RWC-P full mix; chord labels only. Non-commercial.",
            }
        )
    print(f"[OK] RWC-P: {len(tracks)} track(s)")
    return tracks


def _youtube_tracks() -> list[dict[str, Any]]:
    root = DATA_DIR / "youtube_crawl"
    raw = root / "raw"
    labels = root / "processed" / "cqt"
    if not raw.is_dir():
        print("[SKIP] YouTube crawl audio not found")
        return []
    tracks: list[dict[str, Any]] = []
    for audio in sorted(raw.glob("*.wav")):
        stem = audio.stem
        label = labels / f"{stem}.npz"
        if not label.is_file():
            continue
        tracks.append(
            {
                "id": f"youtube:{stem}",
                "audio_path": _rel(audio),
                "source": "youtube_crawl",
                "licence_id": "YOUTUBE-TOS",
                "split": deterministic_split(f"youtube:{stem}"),
                "label_status": "weak",
                "label_channels": ["chord"],
                "chord_label_path": _rel(label),
                "category": "web",
                "recording_type": "unknown",
                "instrument_count": 1,
                "notes": "Weak chord label from the crawl metadata.",
            }
        )
    print(f"[OK] YouTube crawl: {len(tracks)} track(s)")
    return tracks


def _idmt_raw_tracks(eval_splits: dict[str, str]) -> list[dict[str, Any]]:
    root = DATA_DIR / "idmt_smt_guitar" / "raw" / "audio"
    if not root.is_dir():
        print("[SKIP] IDMT raw audio not found")
        return []
    tracks: list[dict[str, Any]] = []
    for audio in sorted(root.rglob("*.wav")):
        rel = audio.relative_to(root)
        lower_parts = [part.lower() for part in rel.parts]
        if "dataset4" in lower_parts:
            category = "music"
        elif any("chord" in part for part in lower_parts):
            category = "chords"
        else:
            category = "exercise"
        track_id = f"idmt_raw:{rel.with_suffix('').as_posix()}"
        split = eval_splits.get(_rel(audio)) or deterministic_split(track_id)
        tracks.append(
            {
                "id": track_id,
                "audio_path": _rel(audio),
                "source": "idmt_smt_guitar",
                "licence_id": "IDMT-ACADEMIC",
                "split": split,
                "label_status": "none",
                "label_channels": ["chord", "solo"],
                "category": category,
                "recording_type": "studio",
                "instrument_count": 1,
                "notes": "Raw IDMT clip; pseudo-labeled by the W1 teacher.",
            }
        )
    print(f"[OK] IDMT raw: {len(tracks)} track(s)")
    return tracks


def _user_tracks() -> list[dict[str, Any]]:
    root = DATA_DIR / "jobs"
    if not root.is_dir():
        return []
    tracks: list[dict[str, Any]] = []
    for audio in sorted(root.glob("*/*.wav")):
        if audio.parent.name == "stems":
            continue
        if audio.name not in ("song.wav", "input.wav", "chord_mix.wav"):
            continue
        job = audio.parent.name
        track_id = f"user:{job}:{audio.stem}"
        tracks.append(
            {
                "id": track_id,
                "audio_path": _rel(audio),
                "source": "user_jobs",
                "licence_id": "USER-PROVIDED",
                "split": deterministic_split(track_id),
                "label_status": "none",
                "label_channels": ["chord", "solo"],
                "category": "user",
                "recording_type": "unknown",
                "instrument_count": 1,
                "notes": "Local analysis job audio; not redistributed.",
            }
        )
    if tracks:
        print(f"[OK] User jobs: {len(tracks)} track(s)")
    return tracks


def build_manifest(*, include_user_jobs: bool = False) -> dict[str, Any]:
    eval_splits = _eval_split_map()
    tracks: list[dict[str, Any]] = []
    tracks.extend(_guitarset_tracks(eval_splits))
    tracks.extend(_guitar_techs_tracks(eval_splits))
    tracks.extend(_egset12_tracks(eval_splits))
    tracks.extend(_rwc_tracks(eval_splits))
    tracks.extend(_youtube_tracks())
    tracks.extend(_idmt_raw_tracks(eval_splits))
    if include_user_jobs:
        tracks.extend(_user_tracks())
    tracks.sort(key=lambda track: track["id"])
    if not tracks:
        raise SystemExit("No real-audio tracks found for the W1 manifest")

    data_root = os.path.relpath(_BACKEND_DIR, _OUT.parent)
    return {
        "schema_version": 1,
        "manifest_id": "w1-dataset-v1",
        "description": (
            "W1 real-audio dataset manifest. Paths are relative to data_root. "
            "GuitarSet follows split_policy.json; other sources use the "
            "deterministic W1 hash split. Human/weak labels are preserved; "
            "unlabeled tracks are teacher pseudo-label candidates."
        ),
        "data_root": Path(data_root).as_posix(),
        "tracks": tracks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=_OUT)
    parser.add_argument(
        "--include-user-jobs",
        action="store_true",
        help="Include local backend/data/jobs audio (not reproducible on a clean checkout)",
    )
    args = parser.parse_args(argv)

    manifest = build_manifest(include_user_jobs=args.include_user_jobs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    from collections import Counter

    counts = Counter(track["source"] for track in manifest["tracks"])
    splits = Counter(track["split"] for track in manifest["tracks"])
    status = Counter(track["label_status"] for track in manifest["tracks"])
    print(f"[DONE] wrote {len(manifest['tracks'])} tracks to {args.out}")
    print(f"  sources: {dict(sorted(counts.items()))}")
    print(f"  splits: {dict(sorted(splits.items()))}")
    print(f"  label_status: {dict(sorted(status.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
