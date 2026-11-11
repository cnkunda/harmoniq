"""Build the committed W0 evaluation manifest from local dataset folders.

The manifest is written to ``docs/eval/amt_manifest.json`` and references
audio/annotations relative to ``backend/``. It is regenerated whenever the
dataset inventory changes::

    cd backend
    python scripts/build_eval_manifest.py

Datasets are included only when their files are present. Missing datasets
are reported clearly and left out; there is no silent fallback to an
empty manifest.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.data_engine.splits import deterministic_split  # noqa: E402

DATA_DIR = _BACKEND_DIR / "data"


def _rel(path: Path) -> str:
    """Return a POSIX path relative to backend/."""
    try:
        return path.resolve().relative_to(_BACKEND_DIR.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"path is outside the backend directory: {path}"
        ) from exc


def _split_policy() -> dict[str, Any]:
    path = DATA_DIR / "manifests" / "split_policy.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _guitarset_tracks(policy: dict[str, Any]) -> list[dict[str, Any]]:
    root = DATA_DIR / "guitarset"
    timelines = root / "processed" / "timelines"
    audio_dir = root / "raw" / "audio_mono-mix"
    annotation_dir = root / "raw" / "annotation"
    if not timelines.is_dir():
        print("[SKIP] GuitarSet timelines not found")
        return []

    split_map = policy.get("guitarset", {})
    tracks: list[dict[str, Any]] = []
    for timeline in sorted(timelines.glob("*.json")):
        stem = timeline.stem
        audio = audio_dir / f"{stem}_mix.wav"
        jams = annotation_dir / f"{stem}.jams"
        if not audio.is_file() or not jams.is_file():
            print(f"[WARN] GuitarSet missing audio/JAMS for {stem}; skipping")
            continue
        player = stem.split("_", 1)[0]
        split = split_map.get(player, "test")
        tracks.append(
            {
                "id": f"guitarset:{stem}",
                "audio_path": _rel(audio),
                "gt_format": "guitarset_jams",
                "gt_path": _rel(jams),
                "chord_gt_path": _rel(timeline),
                "source": "guitarset",
                "recording_type": "studio",
                "split": split,
                "instrument_count": 1,
                "instruments": [24],
                "tuning": "standard",
                "capo": 0,
                "expects_notes": True,
                "notes": "Acoustic guitar, hexaphonic annotations merged per track.",
            }
        )
    print(f"[OK] GuitarSet: {len(tracks)} track(s)")
    return tracks


def _egset12_tracks() -> list[dict[str, Any]]:
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
            print(f"[WARN] EGSet12 missing audio/JAMS for {stem}; skipping")
            continue
        tracks.append(
            {
                "id": f"egset12:{stem}",
                "audio_path": _rel(audio),
                "gt_format": "egset12_jams",
                "gt_path": _rel(jams),
                "chord_gt_path": _rel(timeline),
                "source": "egset12",
                "recording_type": "studio",
                "split": deterministic_split(f"egset12:{stem}"),
                "instrument_count": 1,
                "instruments": [24],
                "tuning": "standard",
                "capo": 0,
                "expects_notes": True,
                "notes": "Electric guitar; jazz/funk/twelve-tone styles.",
            }
        )
    print(f"[OK] EGSet12: {len(tracks)} track(s)")
    return tracks


def _idmt_tracks() -> list[dict[str, Any]]:
    root = DATA_DIR / "idmt_smt_guitar"
    timelines = root / "processed" / "timelines"
    audio_root = root / "raw" / "audio"
    if not timelines.is_dir():
        print("[SKIP] IDMT timelines not found")
        return []

    tracks: list[dict[str, Any]] = []
    for timeline in sorted(timelines.glob("*.json")):
        stem = timeline.stem
        audio: Path | None = None
        try:
            payload = json.loads(timeline.read_text(encoding="utf-8"))
            if payload and isinstance(payload[0], dict):
                raw_path = payload[0].get("path")
                if raw_path:
                    candidate = Path(raw_path)
                    if candidate.is_file():
                        audio = candidate
        except (json.JSONDecodeError, IndexError, TypeError):
            payload = []

        if audio is None and audio_root.is_dir():
            matches = sorted(audio_root.rglob(f"{stem}.wav"))
            if matches:
                audio = matches[0]

        if audio is None:
            print(f"[WARN] IDMT audio not found for {stem}; skipping")
            continue

        tracks.append(
            {
                "id": f"idmt:{stem}",
                "audio_path": _rel(audio),
                "gt_format": "chord_timeline",
                "chord_gt_path": _rel(timeline),
                "source": "idmt_smt_guitar",
                "recording_type": "studio",
                "split": deterministic_split(f"idmt:{stem}"),
                "instrument_count": 1,
                "instruments": [24],
                "tuning": "standard",
                "capo": 0,
                "expects_notes": False,
                "notes": "Chord-level ground truth only; no note MIDI bundled.",
            }
        )
    print(f"[OK] IDMT-SMT-Guitar: {len(tracks)} track(s)")
    return tracks


def _guitar_techs_tracks() -> list[dict[str, Any]]:
    root = DATA_DIR / "guitar_techs"
    timelines = root / "processed" / "timelines"
    raw = root / "raw"
    if not timelines.is_dir():
        print("[SKIP] Guitar-TECHS timelines not found")
        return []

    tracks: list[dict[str, Any]] = []
    for timeline in sorted(timelines.glob("*.json")):
        track_id = timeline.stem
        parts = track_id.split("_", 2)
        if len(parts) != 3:
            print(f"[WARN] Guitar-TECHS unexpected id {track_id}; skipping")
            continue
        source = f"{parts[0]}_{parts[1]}"
        label = parts[2]
        audio = raw / source / "audio" / "directinput" / f"directinput_{label}.wav"
        midi = raw / source / "midi" / f"midi_{label}.mid"
        if not audio.is_file() or not midi.is_file():
            print(f"[WARN] Guitar-TECHS missing audio/MIDI for {track_id}; skipping")
            continue
        tracks.append(
            {
                "id": f"guitar_techs:{track_id}",
                "audio_path": _rel(audio),
                "gt_format": "guitar_techs_midi",
                "gt_path": _rel(midi),
                "chord_gt_path": _rel(timeline),
                "source": "guitar_techs",
                "recording_type": "studio",
                "split": deterministic_split(f"guitar_techs:{track_id}"),
                "instrument_count": 1,
                "instruments": [24],
                "tuning": "standard",
                "capo": 0,
                "expects_notes": True,
                "notes": "Electric guitar; per-string MIDI merged; techniques/chords/scales.",
            }
        )
    print(f"[OK] Guitar-TECHS: {len(tracks)} track(s)")
    return tracks


def _rwc_metadata() -> dict[str, dict[str, str]]:
    path = DATA_DIR / "rwc" / "raw" / "metadata.csv"
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {
            row["RWCID"]: row
            for row in csv.DictReader(handle, delimiter=";")
            if row.get("RWCID")
        }


def _rwc_instrument_count(meta: dict[str, str]) -> int:
    instruments = [
        item.strip()
        for item in (meta.get("LiveInstruments") or "").split(",")
        if item.strip()
    ]
    count = len(instruments)
    if (meta.get("SingerInformation") or "").strip():
        count += 1
    if (meta.get("DrumInformation") or "").strip():
        count += 1
    return max(1, count)


def _rwc_tracks() -> list[dict[str, Any]]:
    root = DATA_DIR / "rwc"
    timelines = root / "processed" / "timelines"
    if not timelines.is_dir():
        print("[SKIP] RWC-P timelines not found (run scripts/download_rwc.py)")
        return []

    metadata = _rwc_metadata()
    tracks: list[dict[str, Any]] = []
    for timeline in sorted(timelines.glob("*.json")):
        stem = timeline.stem
        matches = sorted(root.rglob(f"{stem}.wav")) if root.is_dir() else []
        if not matches:
            print(f"[WARN] RWC-P audio not found for {stem}; skipping")
            continue
        meta = metadata.get(stem, {})
        title = (meta.get("Title") or "").strip()
        genre = (meta.get("GenreSub") or meta.get("GenreMain") or "").strip()
        note = "RWC-P full mix; chord timeline only. CC BY-NC 4.0."
        if title or genre:
            note = f"{note} {title} ({genre}).".replace("  ", " ")
        tracks.append(
            {
                "id": f"rwc:{stem}",
                "audio_path": _rel(matches[0]),
                "gt_format": "chord_timeline",
                "chord_gt_path": _rel(timeline),
                "source": "rwc_p",
                "recording_type": "studio",
                "split": deterministic_split(f"rwc:{stem}"),
                "instrument_count": _rwc_instrument_count(meta),
                "instruments": [24],
                "tuning": "standard",
                "capo": 0,
                "expects_notes": False,
                "notes": note,
            }
        )
    print(f"[OK] RWC-P: {len(tracks)} track(s)")
    return tracks


def build_manifest(*, max_per_source: int | None = None) -> dict[str, Any]:
    policy = _split_policy()
    tracks: list[dict[str, Any]] = []
    for builder in (
        _guitarset_tracks,
        _egset12_tracks,
        _idmt_tracks,
        _guitar_techs_tracks,
        _rwc_tracks,
    ):
        if builder is _guitarset_tracks:
            added = builder(policy)
        else:
            added = builder()
        if max_per_source is not None:
            added = added[:max_per_source]
        tracks.extend(added)

    tracks.sort(key=lambda track: track["id"])
    if not tracks:
        raise SystemExit(
            "No evaluation tracks found. Download at least one dataset first."
        )

    data_root = os.path.relpath(_BACKEND_DIR, _REPO_ROOT / "docs" / "eval")
    return {
        "schema_version": 1,
        "manifest_id": "amt-eval-v1",
        "description": (
            "W0 guitar-AMT evaluation manifest. Paths are relative to "
            "data_root. GuitarSet follows split_policy.json; datasets without a "
            "human policy use the deterministic W1 hash split."
        ),
        "data_root": Path(data_root).as_posix(),
        "tracks": tracks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=_REPO_ROOT / "docs" / "eval" / "amt_manifest.json",
    )
    parser.add_argument(
        "--max-per-source",
        type=int,
        default=None,
        help="Cap tracks per dataset (useful for a quick smoke manifest)",
    )
    args = parser.parse_args(argv)

    manifest = build_manifest(max_per_source=args.max_per_source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[DONE] wrote {len(manifest['tracks'])} tracks to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
