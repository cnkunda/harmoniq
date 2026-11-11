"""W1 teacher pseudo-labeling with confidence filtering.

Usage (from ``backend/``)::

    python scripts/pseudo_label_w1.py --limit 5
    python scripts/pseudo_label_w1.py --source idmt_smt_guitar --limit 50

The teacher is MT3. Each unlabeled track is decoded into a chord timeline
and solo notes, converted to the training CQT windows, and filtered by the
chord decoder's confidence at the window centre. Output is the same
``.npz`` layout that ``build_chord_tflite.py::load_dataset_dir`` reads,
plus a per-track JSON label payload for the future solo head.

The full ≥1,000-track run is GPU-bound; ``--limit`` makes CPU smoke runs
cheap. The report records retention so a low-yield source is visible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.beat_grid import estimate_beat_grid  # noqa: E402
from app.data_engine.confidence import (  # noqa: E402
    PseudoLabelConfig,
    chord_intervals,
    has_confident_chord,
    label_distribution,
    label_windows,
)
from app.data_engine.features import extract_cqt_windows  # noqa: E402
from app.data_engine.manifest import (  # noqa: E402
    W1Manifest,
    W1Track,
    load_w1_manifest,
    resolve_w1_audio,
)
from app.schemas import BeatGrid, ChordEvent  # noqa: E402

logger = logging.getLogger("harmoniq.w1.pseudo")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

_CACHE_SCHEMA_VERSION = 1
_DEFAULT_MANIFEST = _REPO_ROOT / "docs" / "eval" / "w1_dataset_manifest.json"
_DEFAULT_OUTPUT = _BACKEND_DIR / "data" / "pseudo_label" / "w1"
_DEFAULT_REPORT = _REPO_ROOT / "docs" / "audit" / "amt" / "w1_pseudo_label_report.json"
_DEFAULT_CACHE = _BACKEND_DIR / "data" / "evaluation" / "teacher_cache" / "w1"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    parser.add_argument("--teacher", choices=("mt3",), default="mt3")
    parser.add_argument("--split", choices=("train", "val", "test"), default="train")
    parser.add_argument("--all-splits", action="store_true")
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--track", action="append", default=[])
    parser.add_argument(
        "--label-status",
        action="append",
        choices=("human", "weak", "teacher", "none"),
        default=[],
        help="Label statuses to pseudo-label (default: none)",
    )
    parser.add_argument(
        "--include-weak",
        action="store_true",
        help="Also pseudo-label tracks that already have weak labels",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip the first N selected tracks (for chunked CPU runs)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip tracks whose .npz and label JSON already exist",
    )
    parser.add_argument(
        "--report-every",
        type=int,
        default=25,
        help="Write a partial report every N tracks (0 disables)",
    )
    parser.add_argument("--min-chord-confidence", type=float, default=0.60)
    parser.add_argument("--min-note-confidence", type=float, default=0.50)
    parser.add_argument("--min-kept-windows", type=int, default=1)
    parser.add_argument("--require-chords", action="store_true")
    parser.add_argument("--loss-weight", type=float, default=0.5)
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=_DEFAULT_REPORT)
    parser.add_argument("--cache-dir", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args(argv)


def _audio_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_id(track_id: str) -> str:
    return "".join(
        char if char.isalnum() or char in "-_." else "_" for char in track_id
    )


def _select_tracks(manifest: W1Manifest, args: argparse.Namespace) -> list[W1Track]:
    statuses = set(args.label_status) or {"none"}
    if args.include_weak:
        statuses.add("weak")
    tracks = [
        track
        for track in manifest.tracks
        if track.label_status in statuses
    ]
    if not args.all_splits:
        tracks = [track for track in tracks if track.split == args.split]
    if args.source:
        requested = set(args.source)
        tracks = [track for track in tracks if track.source in requested]
    if args.category:
        requested = set(args.category)
        tracks = [track for track in tracks if track.category in requested]
    if args.track:
        requested = set(args.track)
        tracks = [track for track in tracks if track.id in requested]
    tracks.sort(key=lambda track: track.id)
    if args.offset < 0:
        raise SystemExit("--offset must be at least 0")
    if args.offset:
        tracks = tracks[args.offset :]
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be at least 1")
        tracks = tracks[: args.limit]
    if not tracks:
        raise SystemExit("No tracks selected; check --split/--source/--track/--offset")
    return tracks


def _teacher_payload(audio: Path, beat_grid: BeatGrid, teacher: str) -> dict[str, Any]:
    if teacher != "mt3":
        raise ValueError(f"unsupported teacher: {teacher!r}")
    from app.mt3 import (
        decode_events_to_chord_timeline,
        decode_events_to_solo_notes,
        mt3_infer,
    )

    stream = mt3_infer(str(audio))
    if not stream.events:
        return {
            "teacher": teacher,
            "audio_duration_s": float(stream.audio_duration_s),
            "chords": [],
            "notes": [],
        }

    chord_timeline = decode_events_to_chord_timeline(stream, beat_grid)
    solo_notes = decode_events_to_solo_notes(stream, beat_grid)

    program_by_pitch: dict[int, list[tuple[float, int]]] = {}
    for event in stream.events:
        if not event.is_onset or int(event.program) == 128:
            continue
        program_by_pitch.setdefault(int(event.pitch), []).append(
            (float(event.time), int(event.program))
        )

    def _program_for(note) -> int:
        candidates = program_by_pitch.get(int(note.pitch), [])
        if not candidates:
            return 24
        onset, program = min(
            candidates, key=lambda item: abs(item[0] - float(note.start_time))
        )
        return program if abs(onset - float(note.start_time)) <= 0.15 else 24

    return {
        "teacher": teacher,
        "audio_duration_s": float(stream.audio_duration_s),
        "chords": [
            {
                "timestamp": float(event.timestamp),
                "chord": str(event.chord),
                "confidence": float(event.confidence),
            }
            for event in chord_timeline.events
        ],
        "notes": [
            {
                "start_time": float(note.start_time),
                "duration": float(note.duration),
                "pitch": int(note.pitch),
                "velocity": int(note.velocity),
                "confidence": float(note.confidence),
                "program": _program_for(note),
            }
            for note in solo_notes.notes
        ],
    }


def _load_or_run_teacher(
    track: W1Track,
    audio: Path,
    cache_dir: Path,
    *,
    teacher: str,
    refresh: bool,
) -> dict[str, Any]:
    cache_path = cache_dir / teacher / f"{_safe_id(track.id)}-{_audio_hash(audio)[:16]}.json"
    if cache_path.is_file() and not refresh:
        logger.info("[%s] teacher cache hit", track.id)
        return json.loads(cache_path.read_text(encoding="utf-8"))

    beat_grid = BeatGrid.model_validate(estimate_beat_grid(audio))
    payload = _teacher_payload(audio, beat_grid, teacher)
    payload["schema_version"] = _CACHE_SCHEMA_VERSION
    payload["track_id"] = track.id
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return payload


def _payload_to_events(payload: dict[str, Any]) -> tuple[list[ChordEvent], list[dict]]:
    chords = [
        ChordEvent(
            timestamp=float(item["timestamp"]),
            chord=str(item["chord"]),
            confidence=float(item["confidence"]),
        )
        for item in payload.get("chords", [])
    ]
    notes = sorted(
        payload.get("notes", []),
        key=lambda item: (float(item["start_time"]), int(item["pitch"])),
    )
    return chords, notes


def _write_track_labels(
    output_dir: Path,
    track: W1Track,
    teacher: str,
    chords: list[ChordEvent],
    notes: list[dict],
    windows_total: int,
    windows_kept: int,
) -> Path:
    labels_dir = output_dir / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    path = labels_dir / f"{_safe_id(track.id)}.json"
    payload = {
        "schema_version": 1,
        "track_id": track.id,
        "source": track.source,
        "split": track.split,
        "teacher": teacher,
        "windows_total": windows_total,
        "windows_kept": windows_kept,
        "chords": [
            {
                "start": float(event.timestamp),
                "end": (
                    float(chords[index + 1].timestamp)
                    if index + 1 < len(chords)
                    else float(event.timestamp) + 1.0
                ),
                "chord": str(event.chord),
                "confidence": float(event.confidence),
            }
            for index, event in enumerate(chords)
        ],
        "notes": notes,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_npz(
    output_dir: Path,
    track: W1Track,
    features,
    labels,
    confidences,
    *,
    teacher: str,
    loss_weight: float,
    split_label: str,
    windows_total: int | None = None,
) -> Path:
    import numpy as np

    cqt_dir = output_dir / "processed" / "cqt"
    cqt_dir.mkdir(parents=True, exist_ok=True)
    path = cqt_dir / f"{_safe_id(track.id)}.npz"
    total = int(windows_total) if windows_total is not None else len(labels)
    np.savez_compressed(
        path,
        features=features.astype(np.float32),
        labels=np.asarray(labels, dtype=np.int32),
        confidence=np.asarray(confidences, dtype=np.float32),
        split=np.bytes_(split_label),
        source=np.bytes_("pseudo"),
        teacher=np.bytes_(teacher),
        track_id=np.bytes_(track.id),
        loss_weight=np.float64(loss_weight),
        windows_total=np.int64(total),
    )
    return path


def _existing_record(
    output_dir: Path,
    track: W1Track,
) -> dict[str, Any] | None:
    """Return a labeled record when both output files already exist."""
    import numpy as np

    safe = _safe_id(track.id)
    npz_path = output_dir / "processed" / "cqt" / f"{safe}.npz"
    label_path = output_dir / "labels" / f"{safe}.json"
    if not (npz_path.is_file() and label_path.is_file()):
        return None

    try:
        data = np.load(npz_path)
        labels = [int(value) for value in data["labels"]] if "labels" in data else []
    except Exception:
        return None

    windows_kept = len(labels)
    windows_total = windows_kept
    try:
        label_payload = json.loads(label_path.read_text(encoding="utf-8"))
        windows_total = int(label_payload.get("windows_total", windows_kept))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        pass

    return {
        "id": track.id,
        "source": track.source,
        "status": "labeled",
        "reason": "existing",
        "windows_total": windows_total,
        "windows_kept": windows_kept,
        "retention": round(windows_kept / max(windows_total, 1), 6),
        "chord_labels": dict(
            sorted(Counter(int(label) for label in labels).items())
        ),
        "npz": npz_path.name,
        "labels": label_path.name,
    }


def _process_track(
    manifest: W1Manifest,
    manifest_path: Path,
    track: W1Track,
    args: argparse.Namespace,
    config: PseudoLabelConfig,
) -> dict[str, Any]:
    if args.skip_existing:
        existing = _existing_record(args.output_dir, track)
        if existing is not None:
            return existing

    audio = resolve_w1_audio(manifest, track, manifest_path=manifest_path)
    payload = _load_or_run_teacher(
        track,
        audio,
        args.cache_dir,
        teacher=args.teacher,
        refresh=args.refresh,
    )
    chords, notes = _payload_to_events(payload)
    if not chords:
        return {
            "id": track.id,
            "source": track.source,
            "status": "skipped",
            "reason": "teacher_no_chords",
            "windows_total": 0,
            "windows_kept": 0,
        }

    audio_duration = float(payload.get("audio_duration_s") or 0.0)
    intervals = chord_intervals(chords, audio_duration)
    windows, center_times = extract_cqt_windows(audio)
    labels, confidences, keep = label_windows(intervals, center_times, config)

    kept_indices = [index for index, flag in enumerate(keep) if flag]
    windows_kept = len(kept_indices)
    if windows_kept < config.min_kept_windows:
        return {
            "id": track.id,
            "source": track.source,
            "status": "skipped",
            "reason": "no_confident_windows",
            "windows_total": len(windows),
            "windows_kept": windows_kept,
        }
    if config.require_chords and not has_confident_chord(labels, keep):
        return {
            "id": track.id,
            "source": track.source,
            "status": "skipped",
            "reason": "no_confident_chords",
            "windows_total": len(windows),
            "windows_kept": windows_kept,
        }

    kept_labels = [labels[index] for index in kept_indices]
    kept_confidences = [confidences[index] for index in kept_indices]
    kept_features = windows[kept_indices]

    filtered_notes = [
        note
        for note in notes
        if float(note.get("confidence", 0.0)) >= args.min_note_confidence
    ]

    # Val/test are written as "test" so the existing training loader
    # (which filters split == "test") excludes them from training.
    split_label = "train" if track.split == "train" else "test"
    npz_path = _write_npz(
        args.output_dir,
        track,
        kept_features,
        kept_labels,
        kept_confidences,
        teacher=args.teacher,
        loss_weight=args.loss_weight,
        split_label=split_label,
        windows_total=len(windows),
    )
    label_path = _write_track_labels(
        args.output_dir,
        track,
        args.teacher,
        chords,
        filtered_notes,
        len(windows),
        windows_kept,
    )
    return {
        "id": track.id,
        "source": track.source,
        "status": "labeled",
        "windows_total": len(windows),
        "windows_kept": windows_kept,
        "retention": round(windows_kept / max(len(windows), 1), 6),
        "chord_labels": dict(
            sorted(Counter(int(label) for label in kept_labels).items())
        ),
        "npz": npz_path.name,
        "labels": label_path.name,
    }


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "selected": len(records),
        "labeled": sum(1 for record in records if record["status"] == "labeled"),
        "skipped": sum(1 for record in records if record["status"] == "skipped"),
        "windows_total": sum(int(record.get("windows_total", 0)) for record in records),
        "windows_kept": sum(int(record.get("windows_kept", 0)) for record in records),
    }
    totals["retention"] = round(
        totals["windows_kept"] / max(totals["windows_total"], 1), 6
    )
    sources: dict[str, dict[str, Any]] = {}
    for record in records:
        source = record["source"]
        bucket = sources.setdefault(
            source,
            {"selected": 0, "labeled": 0, "skipped": 0, "windows_kept": 0},
        )
        bucket["selected"] += 1
        bucket[record["status"]] += 1
        bucket["windows_kept"] += int(record.get("windows_kept", 0))
    return {"totals": totals, "sources": dict(sorted(sources.items()))}


def _build_report(
    manifest: W1Manifest,
    args: argparse.Namespace,
    records: list[dict[str, Any]],
    configured_statuses: set[str],
    selected_count: int,
    *,
    partial: bool,
) -> dict[str, Any]:
    summary = _summarize(records)
    return {
        "schema_version": 1,
        "manifest_id": manifest.manifest_id,
        "teacher": args.teacher,
        "config": {
            "split": "all" if args.all_splits else args.split,
            "label_statuses": sorted(configured_statuses),
            "min_chord_confidence": args.min_chord_confidence,
            "min_note_confidence": args.min_note_confidence,
            "min_kept_windows": args.min_kept_windows,
            "require_chords": args.require_chords,
            "loss_weight": args.loss_weight,
            "offset": args.offset,
            "skip_existing": args.skip_existing,
        },
        "progress": {
            "processed": len(records),
            "selected": selected_count,
            "partial": partial,
        },
        **summary,
        "tracks": records,
    }


def _write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        manifest = load_w1_manifest(args.manifest)
        tracks = _select_tracks(manifest, args)
    except ValueError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    if args.teacher == "mt3":
        from app.mt3.model_server import Mt3ModelServer

        if not Mt3ModelServer().is_available():
            print(
                "[FAIL] MT3 is unavailable. Install the mt3 extra and download "
                "the checkpoint: pip install -e '.[mt3]' && "
                "python scripts/download_mt3_checkpoint.py",
                file=sys.stderr,
            )
            return 2

    config = PseudoLabelConfig(
        min_chord_confidence=args.min_chord_confidence,
        min_note_confidence=args.min_note_confidence,
        require_chords=args.require_chords,
        min_kept_windows=args.min_kept_windows,
    )
    logger.info(
        "Pseudo-labeling %d track(s) with %s (split=%s)",
        len(tracks),
        args.teacher,
        "all" if args.all_splits else args.split,
    )

    configured_statuses = set(args.label_status) or {"none"}
    if args.include_weak:
        configured_statuses.add("weak")

    records: list[dict[str, Any]] = []
    for index, track in enumerate(tracks, start=1):
        try:
            record = _process_track(
                manifest, args.manifest, track, args, config
            )
        except Exception as exc:  # noqa: BLE001 - recorded in the report
            logger.exception("[%s] pseudo-label failed", track.id)
            record = {
                "id": track.id,
                "source": track.source,
                "status": "skipped",
                "reason": f"{type(exc).__name__}: {exc}",
                "windows_total": 0,
                "windows_kept": 0,
            }
        records.append(record)
        logger.info(
            "(%d/%d) [%s] %s %s",
            index,
            len(tracks),
            track.id,
            record["status"],
            record.get("reason", ""),
        )
        if (
            args.report_every > 0
            and index % args.report_every == 0
            and index < len(tracks)
        ):
            _write_report(
                _build_report(
                    manifest,
                    args,
                    records,
                    configured_statuses,
                    len(tracks),
                    partial=True,
                ),
                args.report,
            )
            print(
                f"[PROGRESS] {index}/{len(tracks)} tracks; report={args.report}",
                flush=True,
            )

    report = _build_report(
        manifest,
        args,
        records,
        configured_statuses,
        len(tracks),
        partial=False,
    )
    _write_report(report, args.report)
    summary = report["totals"]
    print(
        f"[DONE] selected={summary['selected']} "
        f"labeled={summary['labeled']} "
        f"windows_kept={summary['windows_kept']} "
        f"report={args.report}"
    )
    if summary["labeled"] == 0:
        print("[FAIL] no tracks were labeled", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
