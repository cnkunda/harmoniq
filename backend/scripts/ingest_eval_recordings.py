"""Ingest external evaluation recordings (live / home / OOD) into a W0 manifest.

The committed W0 manifest contains datasets only. This script handles
user-supplied recordings that are not redistributed with the repo:

    backend/data/eval_external/
        live/...
        home/...
        ood/...

Supported per-track annotations (optional):
    <stem>.notes.json   — generic note list
    <stem>.chords.json  — [{start, end, chord}, ...]
    <stem>.jams         — JAMS note/chord annotations
    <stem>.mid          — MIDI

A recording without any annotation is added as a **qualitative** track:
the harness records completion, runtime, and produced output, but does not
score it or assign a Pass/Warn/Fail verdict.

Usage (from ``backend/``)::

    python scripts/ingest_eval_recordings.py
    python scripts/eval_amt.py --manifest data/eval_external/manifest.json \
        --tier all --report ../docs/audit/amt/eval-external.json

Merge external tracks into a local copy of the main manifest::

    python scripts/ingest_eval_recordings.py \
        --merge-into ../docs/eval/amt_manifest.json \
        --out data/eval_external/amt_manifest_with_external.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.evaluation.manifest import (  # noqa: E402
    EvalManifest,
    TrackSpec,
    load_manifest,
)

_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".ogg"}
_RECORDING_TYPES = ("live", "home", "ood")
_DEFAULT_INPUT = _BACKEND_DIR / "data" / "eval_external"
_DEFAULT_OUT = _DEFAULT_INPUT / "manifest.json"


def _rel(path: Path) -> str:
    return Path(os.path.normpath(os.path.relpath(path, _BACKEND_DIR))).as_posix()


def _is_audio(path: Path) -> bool:
    return path.suffix.lower() in _AUDIO_EXTENSIONS


def _load_metadata(input_dir: Path) -> dict[str, dict[str, Any]]:
    path = input_dir / "metadata.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("tracks", [])
    if not isinstance(payload, list):
        raise ValueError(f"metadata.json must be a list or {{'tracks': [...]}}: {path}")
    entries: dict[str, dict[str, Any]] = {}
    for entry in payload:
        if not isinstance(entry, dict) or "audio" not in entry:
            raise ValueError(f"metadata entry needs an 'audio' key: {entry!r}")
        audio = Path(str(entry["audio"]))
        key = audio.as_posix()
        entries[key] = entry
    return entries


def _safe_id(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in "-_." else "_" for char in value
    )


def _ground_truth_for(audio: Path) -> tuple[str, str | None, str | None, bool]:
    """Return ``(gt_format, gt_path, chord_gt_path, qualitative)``."""
    notes_json = audio.with_suffix(".notes.json")
    chords_json = audio.with_suffix(".chords.json")
    jams = audio.with_suffix(".jams")
    midi = audio.with_suffix(".mid")

    if notes_json.is_file() and chords_json.is_file():
        return "notes_json", _rel(notes_json), _rel(chords_json), False
    if notes_json.is_file():
        return "notes_json", _rel(notes_json), None, False
    if chords_json.is_file():
        return "chord_timeline", None, _rel(chords_json), False
    if jams.is_file():
        chord_path = _rel(chords_json) if chords_json.is_file() else None
        return "guitarset_jams", _rel(jams), chord_path, False
    if midi.is_file():
        return "midi", _rel(midi), None, False
    return "none", None, None, True


def _resolve_meta_path(input_dir: Path, value: str | None) -> str | None:
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = input_dir / path
    if not path.is_file():
        raise FileNotFoundError(f"metadata path not found: {path}")
    return _rel(path)


def _recording_type_for(audio: Path, input_dir: Path, metadata: dict[str, Any]) -> str:
    if metadata.get("recording_type"):
        return str(metadata["recording_type"])
    try:
        relative = audio.relative_to(input_dir)
    except ValueError:
        return "unknown"
    if relative.parts and relative.parts[0] in _RECORDING_TYPES:
        return relative.parts[0]
    return "unknown"


def _track_from_audio(
    audio: Path,
    input_dir: Path,
    metadata: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    relative = audio.relative_to(input_dir).as_posix()
    meta = metadata.get(relative, {})
    recording_type = _recording_type_for(audio, input_dir, meta)

    gt_format, gt_path, chord_gt_path, qualitative = _ground_truth_for(audio)
    if "qualitative" in meta:
        qualitative = bool(meta["qualitative"])
        if qualitative:
            gt_format, gt_path, chord_gt_path = "none", None, None
    if meta.get("gt_format"):
        gt_format = str(meta["gt_format"])
        gt_path = _resolve_meta_path(input_dir, meta.get("gt_path"))
        chord_gt_path = _resolve_meta_path(input_dir, meta.get("chord_gt_path"))
        qualitative = gt_format == "none" and not gt_path and not chord_gt_path

    stem = audio.stem
    track_id = str(meta.get("id") or f"external:{recording_type}:{stem}")
    track = {
        "id": track_id,
        "audio_path": _rel(audio),
        "gt_format": gt_format,
        "gt_path": gt_path,
        "chord_gt_path": chord_gt_path,
        "source": str(meta.get("source") or "external"),
        "recording_type": recording_type,
        "split": str(meta.get("split") or "test"),
        "instrument_count": int(meta.get("instrument_count", 1)),
        "instruments": list(meta.get("instruments", [])),
        "tuning": str(meta.get("tuning") or "standard"),
        "capo": int(meta.get("capo", 0)),
        "stratum": meta.get("stratum"),
        "expected_verdict": meta.get("expected_verdict"),
        "expects_notes": bool(meta.get("expects_notes", True)),
        "qualitative": qualitative,
        "notes": str(
            meta.get("notes")
            or (
                f"External {recording_type} recording; "
                + ("no annotations (qualitative)" if qualitative else "annotated")
            )
        ),
    }
    # Validate immediately so a bad metadata entry fails before writing.
    TrackSpec.model_validate(track)
    return track


def _discover(input_dir: Path) -> list[Path]:
    audio_files: list[Path] = []
    for path in sorted(input_dir.rglob("*")):
        if "stems" in path.parts:
            continue
        if path.is_file() and _is_audio(path):
            audio_files.append(path)
    return audio_files


def build_external_manifest(
    input_dir: Path,
    *,
    merge_into: Path | None = None,
    manifest_id: str = "amt-external-v1",
    out_dir: Path | None = None,
) -> EvalManifest:
    if not input_dir.is_dir():
        raise FileNotFoundError(f"external input directory not found: {input_dir}")

    metadata = _load_metadata(input_dir)
    tracks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for audio in _discover(input_dir):
        track = _track_from_audio(audio, input_dir, metadata)
        track_id = track["id"]
        if track_id in seen:
            digest = hashlib.sha256(
                track["audio_path"].encode("utf-8")
            ).hexdigest()[:8]
            track["id"] = f"{track_id}:{digest}"
        seen.add(track["id"])
        tracks.append(track)

    base_tracks: list[dict[str, Any]] = []
    base_id = None
    if merge_into is not None:
        base = load_manifest(merge_into)
        base_id = base.manifest_id
        base_tracks = [track.model_dump() for track in base.tracks]

    merged: dict[str, dict[str, Any]] = {}
    for track in base_tracks + tracks:
        merged[track["id"]] = track
    merged_tracks = [merged[key] for key in sorted(merged)]

    base_dir = out_dir if out_dir is not None else _DEFAULT_OUT.parent
    data_root = Path(os.path.relpath(_BACKEND_DIR, base_dir)).as_posix()
    return EvalManifest(
        schema_version=1,
        manifest_id=manifest_id if merge_into is None else f"{base_id}+external",
        description=(
            "External live/home/OOD evaluation recordings. Tracks without "
            "annotations are qualitative and are not scored."
        ),
        data_root=data_root,
        tracks=[TrackSpec.model_validate(track) for track in merged_tracks],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=_DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    parser.add_argument(
        "--merge-into",
        type=Path,
        default=None,
        help="Optional base manifest to merge external tracks into",
    )
    parser.add_argument("--manifest-id", default="amt-external-v1")
    args = parser.parse_args(argv)

    if not args.input_dir.is_dir():
        for name in _RECORDING_TYPES:
            (args.input_dir / name).mkdir(parents=True, exist_ok=True)
        print(
            f"[INFO] Created {args.input_dir}/live, home, ood. "
            "Add audio (and optional .notes.json/.chords.json/.jams/.mid) "
            "then rerun this command."
        )
        return 0

    try:
        manifest = build_external_manifest(
            args.input_dir,
            merge_into=args.merge_into,
            manifest_id=args.manifest_id,
            out_dir=args.out.parent,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    if not manifest.tracks:
        print(
            f"[INFO] No audio found under {args.input_dir}. "
            "Add recordings to live/, home/, or ood/ and rerun."
        )
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(manifest.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    from collections import Counter

    types = Counter(track.recording_type for track in manifest.tracks)
    qualitative = sum(1 for track in manifest.tracks if track.qualitative)
    print(
        f"[DONE] wrote {len(manifest.tracks)} track(s) to {args.out} "
        f"(qualitative={qualitative}, types={dict(sorted(types.items()))})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
