"""W2 teacher comparison harness.

Runs every available teacher on the fixed 50-track sample, scores note/chord
metrics and instrument leakage, and writes a go/no-go recommendation.

Usage (from ``backend/``)::

    python scripts/build_teacher_sample.py
    python scripts/compare_teachers.py --teachers mt3,mr_mt3,yourmt3,musicfm

The PyTorch teachers run in a subprocess worker; configure them with
``HARMONIQ_MT3_INFER_PATH`` and ``HARMONIQ_MT3_CHECKPOINT_DIR``. Unavailable
teachers are reported with a reason, never silently skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Iterable

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.beat_grid import estimate_beat_grid  # noqa: E402
from app.evaluation.ground_truth import (  # noqa: E402
    GroundTruth,
    GroundTruthError,
    GTChord,
    GTNote,
    load_ground_truth,
)
from app.evaluation.manifest import (  # noqa: E402
    EvalManifest,
    ManifestError,
    TrackSpec,
    load_manifest,
    resolve_track_paths,
)
from app.evaluation.metrics import (  # noqa: E402
    chord_event_prf,
    chord_frame_accuracy,
    calibration_metrics,
    note_metrics,
)
from app.evaluation.report import (  # noqa: E402
    Prediction,
    evaluate_track,
)
from app.mt3.chord_decoder import decode_events_to_chord_timeline  # noqa: E402
from app.schemas import BeatGrid  # noqa: E402
from app.teachers import (  # noqa: E402
    TEACHER_NAMES,
    TeacherError,
    TeacherTimeout,
    TeacherUnavailable,
    aggregate_leakage,
    get_teacher,
    leakage_report,
    notes_to_event_stream,
    teacher_statuses,
)
from app.teachers.leakage import GUITAR_PROGRAMS  # noqa: E402

logger = logging.getLogger("harmoniq.w2.compare")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

_DEFAULT_SAMPLE = _REPO_ROOT / "docs" / "eval" / "w2_teacher_sample.json"
_DEFAULT_REPORT = _REPO_ROOT / "docs" / "audit" / "amt" / "w2_teacher_comparison.json"
_DEFAULT_CACHE = _BACKEND_DIR / "data" / "evaluation" / "teacher_outputs"

_CACHE_SCHEMA_VERSION = 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=_DEFAULT_SAMPLE)
    parser.add_argument(
        "--teachers",
        default="mt3,mr_mt3,yourmt3,musicfm",
        help="Comma-separated teacher names",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip the first OFFSET tracks (after sorting); for sharded runs",
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--cached-only",
        action="store_true",
        help="Score only cached teacher outputs; never run inference",
    )
    parser.add_argument("--cache-dir", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--report", type=Path, default=_DEFAULT_REPORT)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument(
        "--device", default=os.getenv("HARMONIQ_TEACHER_DEVICE", "cpu")
    )
    parser.add_argument(
        "--timeout", type=float, default=float(os.getenv("HARMONIQ_TEACHER_TIMEOUT_S", "1800"))
    )
    parser.add_argument("--accuracy-tolerance", type=float, default=0.02)
    parser.add_argument("--leakage-tolerance", type=float, default=0.02)
    parser.add_argument("--max-rtf-ratio", type=float, default=3.0)
    parser.add_argument(
        "--min-guitar-retention",
        type=float,
        default=0.2,
        help="Minimum share of a teacher's notes that survive guitar-program filtering",
    )
    return parser.parse_args(argv)


def _parse_teachers(raw: str) -> list[str]:
    names = [name.strip() for name in raw.split(",") if name.strip()]
    unknown = [name for name in names if name not in TEACHER_NAMES]
    if unknown:
        raise SystemExit(
            f"unknown teacher(s): {', '.join(unknown)}; "
            f"choose from {', '.join(TEACHER_NAMES)}"
        )
    return names


def _audio_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_id(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in "-_." else "_" for char in value
    )


def _cache_path(cache_dir: Path, teacher: str, audio: Path) -> Path:
    return cache_dir / teacher / f"{_safe_id(audio.stem)}-{_audio_hash(audio)[:16]}.json"


def _prediction_chords(timeline) -> list[GTChord]:
    events = list(timeline.events)
    chords: list[GTChord] = []
    for index, event in enumerate(events):
        start = float(event.timestamp)
        end = (
            float(events[index + 1].timestamp)
            if index + 1 < len(events)
            else start + 1.0
        )
        chords.append(
            GTChord(
                start=start,
                end=max(start, end),
                chord=str(event.chord),
                confidence=float(event.confidence),
            )
        )
    return chords


def _prediction_notes_list(notes) -> list[GTNote]:
    return [
        GTNote(
            pitch=int(note.pitch),
            onset=float(note.onset),
            offset=float(note.offset),
            velocity=int(note.velocity),
            program=note.program,
            confidence=float(note.confidence),
        )
        for note in notes
    ]


def _prediction_notes(output) -> list[GTNote]:
    return _prediction_notes_list(output.notes)


def _audio_duration(output, ground_truth: GroundTruth) -> float:
    duration = output.metadata.get("audio_duration_s")
    if duration:
        return float(duration)
    candidates = [note.offset for note in output.notes]
    candidates.extend(chord.end for chord in ground_truth.chords)
    return max(candidates + [1.0])


def _load_teacher_outputs(
    teacher,
    audio_paths: list[Path],
    cache_dir: Path,
    *,
    refresh: bool,
    cached_only: bool = False,
) -> dict[Path, Any]:
    outputs: dict[Path, Any] = {}
    missing: list[Path] = []
    for path in audio_paths:
        cache = _cache_path(cache_dir, teacher.name, path)
        if cache.is_file() and not refresh:
            try:
                payload = json.loads(cache.read_text(encoding="utf-8"))
                from app.teachers.events import TeacherOutput

                outputs[path] = TeacherOutput.from_dict(payload)
                continue
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                logger.warning("invalid teacher cache %s; recomputing", cache)
        missing.append(path)

    if cached_only:
        if missing:
            logger.info(
                "%s: %d/%d track(s) not cached; skipped (cached-only)",
                teacher.name,
                len(missing),
                len(audio_paths),
            )
        return outputs

    if missing:
        logger.info(
            "%s: transcribing %d track(s) (%d cached)",
            teacher.name,
            len(missing),
            len(outputs),
        )
        fresh = teacher.transcribe_many(missing)
        outputs.update(fresh)
        for path, output in fresh.items():
            cache = _cache_path(cache_dir, teacher.name, path)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps(
                    {"schema_version": _CACHE_SCHEMA_VERSION, **output.as_dict()},
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
    return outputs


def _average(values: Iterable[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return round(sum(present) / len(present), 6) if present else None


def _f1(block: Any) -> float | None:
    return float(block["f1"]) if isinstance(block, dict) else None


def _note_f1(metrics: dict[str, Any], key: str) -> float | None:
    return _f1(metrics.get("notes", {}).get(key))


def _raw_note_f1(metrics: dict[str, Any], key: str) -> float | None:
    return _f1((metrics.get("notes_raw") or {}).get(key))


def _summarize_teacher(
    name: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    completed = [record for record in records if not record.get("error")]
    leak_reports = [record["leakage"] for record in completed if record.get("leakage")]
    leak = aggregate_leakage(leak_reports)
    runtimes = [float(record["runtime_ms"]) for record in completed]
    rtfs = [
        float(record["runtime_ms"]) / 1000.0 / float(record["audio_duration_s"])
        for record in completed
        if record.get("audio_duration_s")
    ]
    return {
        "tracks": len(records),
        "completed": len(completed),
        "failed": len(records) - len(completed),
        "chord_frame_accuracy": _average(
            record["metrics"].get("chords", {}).get("frame_accuracy")
            for record in completed
        ),
        "onset_f1": _average(
            _note_f1(record["metrics"], "onset_multi") for record in completed
        ),
        "onset_pitch_f1": _average(
            _note_f1(record["metrics"], "onset_pitch") for record in completed
        ),
        "raw_onset_pitch_f1": _average(
            _raw_note_f1(record["metrics"], "onset_pitch")
            for record in completed
        ),
        "offset_f1": _average(
            _note_f1(record["metrics"], "offset_multi") for record in completed
        ),
        "guitar_retention": _average(
            record["metrics"].get("guitar_retention") for record in completed
        ),
        "ece": _average(
            record["metrics"].get("calibration", {}).get("ece")
            for record in completed
        ),
        "leakage_rate": leak.get("leakage_rate"),
        "non_guitar_program_share": leak.get("non_guitar_program_share"),
        "out_of_range_share": leak.get("out_of_range_share"),
        "family_counts": leak.get("family_counts"),
        "notes": leak.get("notes"),
        "runtime_ms_mean": _average(runtimes),
        "runtime_ms_total": round(sum(runtimes), 3) if runtimes else None,
        "rtf": _average(rtfs),
    }


def _delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return round(float(candidate) - float(baseline), 6)


def _decide(
    summaries: dict[str, dict[str, Any]],
    statuses: dict[str, dict[str, Any]],
    *,
    accuracy_tolerance: float,
    leakage_tolerance: float,
    max_rtf_ratio: float,
    min_guitar_retention: float = 0.2,
) -> dict[str, Any]:
    baseline = summaries.get("mt3")
    if baseline is None or not baseline.get("completed"):
        return {
            "status": "blocked",
            "recommended_teacher": None,
            "rationale": "MT3 baseline did not produce results.",
            "checks": {},
        }

    # A teacher with cached results is a valid candidate even when its runtime
    # is unavailable (e.g. `--cached-only` reproduction on a machine without
    # mt3-infer), matching how cached outputs are still scored.
    available_others = [
        name
        for name, status in statuses.items()
        if name != "mt3"
        and (
            status.get("available")
            or (summaries.get(name) or {}).get("completed", 0) > 0
        )
    ]
    if not available_others:
        return {
            "status": "blocked",
            "recommended_teacher": None,
            "rationale": (
                "No non-MT3 teacher is available; configure MR-MT3/YourMT3 "
                "checkpoints and the mt3-infer worker, then rerun."
            ),
            "checks": {},
        }

    required = max(1, int(round(0.8 * baseline["tracks"])))
    checks: dict[str, dict[str, Any]] = {}
    candidates: list[tuple[float, str]] = []
    for name in available_others:
        summary = summaries.get(name)
        if summary is None or summary.get("completed", 0) < required:
            checks[name] = {
                "eligible": False,
                "reason": "insufficient completed tracks",
            }
            continue
        chord_delta = _delta(
            summary["chord_frame_accuracy"], baseline["chord_frame_accuracy"]
        )
        onset_delta = _delta(summary["onset_f1"], baseline["onset_f1"])
        onset_pitch_delta = _delta(
            summary.get("onset_pitch_f1"), baseline.get("onset_pitch_f1")
        )
        leakage_delta = _delta(
            summary["leakage_rate"], baseline["leakage_rate"]
        )
        retention = summary.get("guitar_retention")
        rtf = summary.get("rtf")
        baseline_rtf = baseline.get("rtf")
        runtime_ratio = (
            round(float(rtf) / float(baseline_rtf), 6)
            if rtf is not None and baseline_rtf
            else None
        )

        improves_accuracy = (
            (chord_delta is not None and chord_delta >= accuracy_tolerance)
            or (onset_delta is not None and onset_delta >= accuracy_tolerance)
            or (
                onset_pitch_delta is not None
                and onset_pitch_delta >= accuracy_tolerance
            )
        )
        leakage_ok = (
            leakage_delta is not None
            and leakage_delta <= leakage_tolerance
        )
        retention_ok = (
            retention is not None and float(retention) >= min_guitar_retention
        )
        runtime_ok = (
            runtime_ratio is not None
            and runtime_ratio <= max_rtf_ratio
        )
        eligible = improves_accuracy and retention_ok and runtime_ok
        checks[name] = {
            "eligible": eligible,
            "chord_delta": chord_delta,
            "onset_delta": onset_delta,
            "onset_pitch_delta": onset_pitch_delta,
            "leakage_delta": leakage_delta,
            "guitar_retention": retention,
            "requires_guitar_filter": not leakage_ok,
            "runtime_ratio": runtime_ratio,
            "improves_accuracy": improves_accuracy,
            "retention_ok": retention_ok,
            "runtime_ok": runtime_ok,
        }
        if eligible:
            score = (
                0.5 * float(summary["chord_frame_accuracy"] or 0.0)
                + 0.5 * float(summary["onset_f1"] or 0.0)
                - float(summary["leakage_rate"] or 0.0)
            )
            candidates.append((score, name))

    if candidates:
        candidates.sort(reverse=True)
        _, recommended = candidates[0]
        return {
            "status": "go",
            "recommended_teacher": recommended,
            "rationale": (
                f"{recommended} beats MT3 on chord or guitar-filtered onset "
                "accuracy within the runtime budget."
                + (
                    " Mandatory guitar-program filtering is required because "
                    "raw leakage is higher than MT3."
                    if checks[recommended].get("requires_guitar_filter")
                    else ""
                )
            ),
            "checks": checks,
        }

    return {
        "status": "no-go",
        "recommended_teacher": None,
        "rationale": (
            "No available teacher beat MT3 on chord/onset accuracy while "
            "keeping leakage and runtime within tolerance."
        ),
        "checks": checks,
    }


def _sanitize(text: str | None) -> str | None:
    if not text:
        return text
    return (
        text.replace(str(_BACKEND_DIR), "<backend>")
        .replace(str(_REPO_ROOT), "<repo>")
        .replace(os.path.expanduser("~"), "~")
    )


def _build_report(
    manifest: EvalManifest,
    teachers: list[str],
    statuses: dict[str, dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
    records: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    baseline = summaries.get("mt3")
    deltas: dict[str, dict[str, Any]] = {}
    if baseline is not None:
        for name, summary in summaries.items():
            if name == "mt3":
                continue
            deltas[name] = {
                "chord_frame_accuracy": _delta(
                    summary["chord_frame_accuracy"], baseline["chord_frame_accuracy"]
                ),
                "onset_f1": _delta(summary["onset_f1"], baseline["onset_f1"]),
                "onset_pitch_f1": _delta(
                    summary.get("onset_pitch_f1"), baseline.get("onset_pitch_f1")
                ),
                "raw_onset_pitch_f1": _delta(
                    summary.get("raw_onset_pitch_f1"),
                    baseline.get("raw_onset_pitch_f1"),
                ),
                "offset_f1": _delta(summary["offset_f1"], baseline["offset_f1"]),
                "guitar_retention": _delta(
                    summary.get("guitar_retention"),
                    baseline.get("guitar_retention"),
                ),
                "leakage_rate": _delta(
                    summary["leakage_rate"], baseline["leakage_rate"]
                ),
                "ece": _delta(summary["ece"], baseline["ece"]),
                "rtf_ratio": (
                    round(float(summary["rtf"]) / float(baseline["rtf"]), 6)
                    if summary.get("rtf") is not None
                    and baseline.get("rtf")
                    else None
                ),
            }

    decision = _decide(
        summaries,
        statuses,
        accuracy_tolerance=args.accuracy_tolerance,
        leakage_tolerance=args.leakage_tolerance,
        max_rtf_ratio=args.max_rtf_ratio,
        min_guitar_retention=args.min_guitar_retention,
    )
    return {
        "schema_version": 1,
        "sample_id": manifest.manifest_id,
        "config": {
            "teachers": teachers,
            "tracks": len({record["track_id"] for record in records}),
            "device": args.device,
            "accuracy_tolerance": args.accuracy_tolerance,
            "leakage_tolerance": args.leakage_tolerance,
            "max_rtf_ratio": args.max_rtf_ratio,
            "min_guitar_retention": args.min_guitar_retention,
        },
        "teacher_status": {
            name: {
                "available": status["available"],
                "display_name": status["display_name"],
                "reason": _sanitize(status["reason"]),
            }
            for name, status in statuses.items()
        },
        "summaries": summaries,
        "deltas_vs_mt3": deltas,
        "decision": decision,
        "records": records,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# W2 teacher comparison — {report['sample_id']}",
        "",
        "| Teacher | Status | Tracks | Chord acc | Onset F1 | OnsetPitch F1 | Offset F1 | Guitar ret | Leakage | ECE | RTF |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    def fmt(value):
        if value is None:
            return "—"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)

    for name, summary in report["summaries"].items():
        status = report["teacher_status"].get(name, {})
        state = "available" if status.get("available") else "unavailable"
        lines.append(
            f"| {name} | {state} | {summary.get('completed', 0)}/"
            f"{summary.get('tracks', 0)} | "
            f"{fmt(summary.get('chord_frame_accuracy'))} | "
            f"{fmt(summary.get('onset_f1'))} | "
            f"{fmt(summary.get('onset_pitch_f1'))} | "
            f"{fmt(summary.get('offset_f1'))} | "
            f"{fmt(summary.get('guitar_retention'))} | "
            f"{fmt(summary.get('leakage_rate'))} | "
            f"{fmt(summary.get('ece'))} | "
            f"{fmt(summary.get('rtf'))} |"
        )
    lines.append("")
    lines.append("## Deltas vs MT3")
    lines.append("")
    lines.append(
        "| Teacher | Chord Δ | Onset Δ | OnsetPitch Δ | Offset Δ | Retention Δ | Leakage Δ | RTF ratio |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for name, delta in report["deltas_vs_mt3"].items():
        lines.append(
            f"| {name} | {fmt(delta.get('chord_frame_accuracy'))} | "
            f"{fmt(delta.get('onset_f1'))} | {fmt(delta.get('onset_pitch_f1'))} | "
            f"{fmt(delta.get('offset_f1'))} | {fmt(delta.get('guitar_retention'))} | "
            f"{fmt(delta.get('leakage_rate'))} | {fmt(delta.get('rtf_ratio'))} |"
        )
    lines.append("")
    decision = report["decision"]
    lines.append("## Decision")
    lines.append("")
    lines.append(f"**{decision['status']}**")
    lines.append("")
    lines.append(decision["rationale"])
    if decision.get("recommended_teacher"):
        lines.append("")
        lines.append(f"Recommended teacher: **{decision['recommended_teacher']}**")
    if decision.get("checks"):
        lines.append("")
        lines.append("| Teacher | Eligible | Chord Δ | Onset Δ | OnsetPitch Δ | Leakage Δ | Retention | Filter | RTF ratio |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |")
        for name, check in sorted(decision["checks"].items()):
            lines.append(
                f"| {name} | {check.get('eligible')} | "
                f"{fmt(check.get('chord_delta'))} | {fmt(check.get('onset_delta'))} | "
                f"{fmt(check.get('onset_pitch_delta'))} | "
                f"{fmt(check.get('leakage_delta'))} | "
                f"{fmt(check.get('guitar_retention'))} | "
                f"{check.get('requires_guitar_filter')} | "
                f"{fmt(check.get('runtime_ratio'))} |"
            )
    lines.append("")
    unavailable = [
        f"- **{name}**: {status['reason']}"
        for name, status in report["teacher_status"].items()
        if not status["available"]
    ]
    if unavailable:
        lines.append("## Unavailable teachers")
        lines.append("")
        lines.extend(unavailable)
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    teachers = _parse_teachers(args.teachers)
    os.environ.setdefault("HARMONIQ_TEACHER_DEVICE", args.device)
    os.environ.setdefault("HARMONIQ_TEACHER_TIMEOUT_S", str(args.timeout))

    try:
        manifest = load_manifest(args.sample)
    except (ManifestError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    tracks = sorted(manifest.tracks, key=lambda track: track.id)
    if args.offset < 0:
        raise SystemExit("--offset must be at least 0")
    if args.offset:
        tracks = tracks[args.offset :]
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be at least 1")
        tracks = tracks[: args.limit]
    if not tracks:
        raise SystemExit("no tracks selected")

    statuses = teacher_statuses()
    records: list[dict[str, Any]] = []
    summaries: dict[str, dict[str, Any]] = {}

    for teacher_name in teachers:
        status = statuses.get(teacher_name)
        if status is None:
            continue

        teacher = get_teacher(teacher_name)
        resolved: dict[str, tuple[Path, Path | None, Path | None] | None] = {}
        for track in tracks:
            try:
                resolved[track.id] = resolve_track_paths(
                    manifest, track, manifest_path=args.sample
                )
            except ManifestError as exc:
                logger.error("[%s] path error: %s", track.id, exc)
                resolved[track.id] = None

        audio_paths = [
            resolved[track.id][0]
            for track in tracks
            if resolved[track.id] is not None
        ]
        try:
            outputs = _load_teacher_outputs(
                teacher,
                audio_paths,
                args.cache_dir,
                refresh=args.refresh,
                # Unavailable teachers can still be scored from cache (e.g.
                # MT3 baseline on a PyTorch-only cloud box).
                cached_only=args.cached_only or not status["available"],
            )
        except (TeacherError, TeacherUnavailable, TeacherTimeout) as exc:
            logger.error("%s failed: %s", teacher_name, exc)
            summaries[teacher_name] = {
                "tracks": len(tracks),
                "completed": 0,
                "failed": len(tracks),
                "chord_frame_accuracy": None,
                "onset_f1": None,
                "offset_f1": None,
                "ece": None,
                "leakage_rate": None,
                "non_guitar_program_share": None,
                "out_of_range_share": None,
                "runtime_ms_mean": None,
                "runtime_ms_total": None,
                "rtf": None,
            }
            continue

        teacher_records: list[dict[str, Any]] = []
        for track in tracks:
            paths = resolved[track.id]
            if paths is None:
                teacher_records.append(
                    {
                        "track_id": track.id,
                        "source": track.source,
                        "split": track.split,
                        "teacher": teacher_name,
                        "error": "path resolution failed",
                    }
                )
                continue
            audio, gt_path, chord_gt_path = paths
            output = outputs.get(audio)
            try:
                ground_truth = load_ground_truth(
                    track, gt_path=gt_path, chord_gt_path=chord_gt_path
                )
            except (GroundTruthError, ManifestError) as exc:
                teacher_records.append(
                    {
                        "track_id": track.id,
                        "source": track.source,
                        "split": track.split,
                        "teacher": teacher_name,
                        "error": f"ground_truth: {exc}",
                    }
                )
                continue
            if output is None:
                teacher_records.append(
                    {
                        "track_id": track.id,
                        "source": track.source,
                        "split": track.split,
                        "teacher": teacher_name,
                        "error": (
                            "not cached (cached-only run)"
                            if args.cached_only or not status["available"]
                            else "teacher produced no output"
                        ),
                    }
                )
                continue
            if output.metadata.get("error"):
                teacher_records.append(
                    {
                        "track_id": track.id,
                        "source": track.source,
                        "split": track.split,
                        "teacher": teacher_name,
                        "error": str(output.metadata["error"]),
                    }
                )
                continue

            duration = _audio_duration(output, ground_truth)
            try:
                beat_grid = BeatGrid.model_validate(estimate_beat_grid(audio))
                event_stream = notes_to_event_stream(
                    output.notes,
                    audio_duration=duration,
                    model_version=output.model_version,
                )
                chord_timeline = decode_events_to_chord_timeline(
                    event_stream, beat_grid
                )
                prediction = Prediction(
                    notes=_prediction_notes(output),
                    chords=_prediction_chords(chord_timeline),
                    runtime_ms=output.latency_ms,
                    completed=True,
                    tier=teacher_name,
                    metadata=output.metadata,
                )
                result = evaluate_track(track, prediction, ground_truth)
                leakage = leakage_report(
                    output.notes, expected_programs=track.instruments
                )
                guitar_notes = [
                    note
                    for note in output.notes
                    if note.program is not None
                    and int(note.program) in GUITAR_PROGRAMS
                ]
                metrics = dict(result.metrics)
                metrics["leakage"] = leakage
                metrics["guitar_retention"] = (
                    round(len(guitar_notes) / len(output.notes), 6)
                    if output.notes
                    else 0.0
                )
                if ground_truth.has_notes:
                    metrics["notes_raw"] = note_metrics(
                        ground_truth.notes,
                        _prediction_notes_list(output.notes),
                    )
                    metrics["notes"] = note_metrics(
                        ground_truth.notes,
                        _prediction_notes_list(guitar_notes),
                    )
                teacher_records.append(
                    {
                        "track_id": track.id,
                        "source": track.source,
                        "split": track.split,
                        "teacher": teacher_name,
                        "audio_duration_s": round(duration, 6),
                        "runtime_ms": round(output.latency_ms, 3),
                        "metrics": metrics,
                        "leakage": leakage,
                        "model_version": output.model_version,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - recorded in the report
                logger.exception("[%s/%s] evaluation failed", teacher_name, track.id)
                teacher_records.append(
                    {
                        "track_id": track.id,
                        "source": track.source,
                        "split": track.split,
                        "teacher": teacher_name,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        records.extend(teacher_records)
        summaries[teacher_name] = _summarize_teacher(
            teacher_name, teacher_records
        )

    report = _build_report(
        manifest, teachers, statuses, summaries, records, args
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path = args.markdown or args.report.with_suffix(".md")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")

    print(
        f"[DONE] teachers={teachers} tracks={len(tracks)} "
        f"decision={report['decision']['status']} report={args.report}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
