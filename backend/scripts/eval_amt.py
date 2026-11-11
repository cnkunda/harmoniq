"""Commit 1 / W0: challenge-style AMT evaluation CLI.

Usage (from ``backend/``)::

    python scripts/eval_amt.py \
        --manifest ../docs/eval/amt_manifest.json \
        --tier mt3 \
        --limit 5 \
        --report ../docs/audit/amt/eval-mt3.json

The harness runs one tier on the same manifest and writes a deterministic
JSON + Markdown report. Predictions are cached by audio hash so repeated
runs and per-tier comparisons do not re-run the model.

Tiers:
    mt3    — MT3 event stream + chord/solo decoders
    crnn   — CRNN Keras/TFLite only (no chroma fallthrough)
    chroma — chroma template matcher only
    full   — the production fallback chain (MT3 → CRNN → chroma)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.beat_grid import estimate_beat_grid  # noqa: E402
from app.evaluation.ground_truth import (  # noqa: E402
    GroundTruth,
    GroundTruthError,
    load_ground_truth,
)
from app.evaluation.manifest import (  # noqa: E402
    EvalManifest,
    ManifestError,
    TrackSpec,
    load_manifest,
    resolve_track_paths,
)
from app.evaluation.report import (  # noqa: E402
    Prediction,
    build_report,
    evaluate_track,
    prediction_from_dict,
    prediction_to_dict,
    write_comparison_markdown,
    write_report_json,
    write_report_markdown,
)
from app.schemas import BeatGrid  # noqa: E402

logger = logging.getLogger("harmoniq.eval")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

_TIERS = ("mt3", "crnn", "chroma", "full")
_STUDENT_TIER = "student"
_CACHE_SCHEMA_VERSION = 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--tier",
        choices=(*_TIERS, _STUDENT_TIER, "all"),
        default="full",
        help=(
            "'all' runs every baselined tier (student is added when its "
            "artifact is present) and writes a comparison report"
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=_REPO_ROOT / "docs" / "audit" / "amt" / "eval.json",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="Optional Markdown path (defaults next to --report with .md)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max tracks")
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip the first N selected tracks (sharding)",
    )
    parser.add_argument("--split", choices=("train", "val", "test"), default=None)
    parser.add_argument("--source", default=None, help="Filter by source name")
    parser.add_argument("--track", action="append", default=[], help="Track id (repeatable)")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=_BACKEND_DIR / "data" / "evaluation" / "predictions",
    )
    parser.add_argument("--refresh", action="store_true", help="Ignore cached predictions")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Override the manifest data_root",
    )
    parser.add_argument(
        "--fail-on-track-error",
        action="store_true",
        help="Exit non-zero if any track fails",
    )
    return parser.parse_args(argv)


def _select_tracks(manifest: EvalManifest, args: argparse.Namespace) -> list[TrackSpec]:
    tracks = list(manifest.tracks)
    if args.split:
        tracks = [track for track in tracks if track.split == args.split]
    if args.source:
        tracks = [track for track in tracks if track.source == args.source]
    if args.track:
        requested = set(args.track)
        tracks = [track for track in tracks if track.id in requested]
    tracks.sort(key=lambda track: track.id)
    if args.offset < 0:
        raise SystemExit("--offset must be non-negative")
    if args.offset:
        tracks = tracks[args.offset :]
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be at least 1")
        tracks = tracks[: args.limit]
    if not tracks:
        raise SystemExit("No tracks selected; check --split/--source/--track")
    return tracks


def _audio_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_path(
    cache_dir: Path,
    tier: str,
    track: TrackSpec,
    audio_hash: str,
) -> Path:
    safe_id = "".join(
        char if char.isalnum() or char in "-_." else "_" for char in track.id
    )
    return cache_dir / tier / f"{safe_id}-{audio_hash[:16]}.json"


def _to_prediction_notes(notes, events=None) -> list:
    from app.evaluation.ground_truth import GTNote

    # SoloNote does not carry a GM program. Recover it from the nearest MT3
    # onset of the same pitch so instrument-ID metrics reflect the model, not
    # a hardcoded guitar label.
    onsets_by_pitch: dict[int, list[tuple[float, int]]] = {}
    for event in events or []:
        if not getattr(event, "is_onset", True):
            continue
        if int(event.program) == 128:
            continue
        onsets_by_pitch.setdefault(int(event.pitch), []).append(
            (float(event.time), int(event.program))
        )

    def _program_for(note) -> int:
        candidates = onsets_by_pitch.get(int(note.pitch), [])
        if not candidates:
            return 24
        onset, program = min(
            candidates, key=lambda item: abs(item[0] - float(note.start_time))
        )
        if abs(onset - float(note.start_time)) <= 0.15:
            return program
        return 24

    return [
        GTNote(
            pitch=int(note.pitch),
            onset=float(note.start_time),
            offset=float(note.start_time) + float(note.duration),
            velocity=int(note.velocity),
            program=_program_for(note),
            confidence=float(note.confidence),
        )
        for note in notes
    ]


def _chords_from_timeline(timeline) -> list:
    from app.evaluation.ground_truth import GTChord

    events = list(timeline.events)
    chords: list[GTChord] = []
    for index, event in enumerate(events):
        start = float(event.timestamp)
        if index + 1 < len(events):
            end = float(events[index + 1].timestamp)
        else:
            end = start + 1.0
        chords.append(
            GTChord(
                start=start,
                end=max(start, end),
                chord=str(event.chord),
                confidence=float(event.confidence),
            )
        )
    return chords


def _predict_mt3(audio: Path, beat_grid: BeatGrid) -> Prediction:
    from app.mt3 import (
        decode_events_to_chord_timeline,
        decode_events_to_solo_notes,
        mt3_infer,
    )

    start = time.perf_counter()
    stream = mt3_infer(str(audio))
    if not stream.events:
        raise RuntimeError("MT3 returned no events")
    chord_timeline = decode_events_to_chord_timeline(stream, beat_grid)
    solo_notes = decode_events_to_solo_notes(stream, beat_grid)
    runtime_ms = (time.perf_counter() - start) * 1000.0
    return Prediction(
        notes=_to_prediction_notes(solo_notes.notes, stream.events),
        chords=_chords_from_timeline(chord_timeline),
        runtime_ms=runtime_ms,
        tier="mt3",
        metadata={
            "model_version": stream.model_version,
            "mean_confidence": stream.mean_confidence,
            "num_instruments": stream.num_instruments,
            "inference_time_ms": stream.inference_time_ms,
        },
    )


def _predict_full(audio: Path, beat_grid: BeatGrid) -> Prediction:
    from app.mt3.fallback import transcribe_with_fallback

    start = time.perf_counter()
    result = transcribe_with_fallback(str(audio), beat_grid)
    runtime_ms = (time.perf_counter() - start) * 1000.0
    if result.source == "none":
        raise RuntimeError(result.fallback_reason or "fallback chain produced no result")
    return Prediction(
        notes=_to_prediction_notes(
            result.solo_notes.notes,
            result.mt3_events.events if result.mt3_events else [],
        ),
        chords=_chords_from_timeline(result.chord_timeline),
        runtime_ms=runtime_ms,
        tier="full",
        metadata={
            "source": result.source,
            "mean_confidence": result.mean_confidence,
            "fallback_reason": result.fallback_reason,
        },
    )


_STUDENT_MODEL = None


def _predict_student(audio: Path, beat_grid: BeatGrid) -> Prediction:
    from app.student.inference import StudentModel

    global _STUDENT_MODEL
    if _STUDENT_MODEL is None:
        candidate = StudentModel()
        if not candidate.is_available():
            raise RuntimeError(
                candidate.unavailable_reason() or "student unavailable"
            )
        candidate.warmup()
        _STUDENT_MODEL = candidate
    model = _STUDENT_MODEL

    start = time.perf_counter()
    timeline, solo_notes, metadata = model.transcribe(audio, beat_grid)
    runtime_ms = (time.perf_counter() - start) * 1000.0
    return Prediction(
        notes=_to_prediction_notes(solo_notes.notes),
        chords=_chords_from_timeline(timeline),
        runtime_ms=runtime_ms,
        tier=_STUDENT_TIER,
        metadata=metadata,
    )


def _predict_chord_tier(
    audio: Path,
    beat_grid: BeatGrid,
    tier: str,
) -> Prediction:
    from app.chord_inference import get_last_inference_tier, infer_chords

    start = time.perf_counter()
    timeline = infer_chords(audio, beat_grid, force_tier=tier)
    runtime_ms = (time.perf_counter() - start) * 1000.0
    actual_tier = get_last_inference_tier()
    if not timeline.events:
        raise RuntimeError(f"{tier} produced no chord events")
    return Prediction(
        notes=[],
        chords=_chords_from_timeline(timeline),
        runtime_ms=runtime_ms,
        tier=actual_tier,
        metadata={"requested_tier": tier, "actual_tier": actual_tier},
    )


def _predict(
    audio: Path,
    beat_grid: BeatGrid,
    tier: str,
) -> Prediction:
    if tier == "mt3":
        return _predict_mt3(audio, beat_grid)
    if tier == "full":
        return _predict_full(audio, beat_grid)
    if tier == _STUDENT_TIER:
        return _predict_student(audio, beat_grid)
    if tier in ("crnn", "chroma"):
        return _predict_chord_tier(audio, beat_grid, tier)
    raise ValueError(f"unsupported tier: {tier!r}")


def _run_track(
    manifest: EvalManifest,
    track: TrackSpec,
    args: argparse.Namespace,
    tier: str,
) -> Prediction:
    try:
        audio, gt_path, chord_gt_path = resolve_track_paths(
            manifest,
            track,
            manifest_path=args.manifest,
            data_root_override=args.data_root,
        )
    except ManifestError as exc:
        return Prediction(
            completed=False,
            error=str(exc),
            tier=tier,
        )

    cache_path = _cache_path(
        args.cache_dir, tier, track, _audio_hash(audio)
    )
    if cache_path.is_file() and not args.refresh:
        logger.info("[%s] cache hit: %s", track.id, cache_path)
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            return prediction_from_dict(payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "[%s] invalid cache %s (%s); recomputing",
                track.id,
                cache_path,
                exc,
            )

    try:
        logger.info("[%s] running %s", track.id, tier)
        beat_grid = BeatGrid.model_validate(estimate_beat_grid(audio))
        prediction = _predict(audio, beat_grid, tier)
    except Exception as exc:  # noqa: BLE001 - recorded in the report
        logger.exception("[%s] %s failed", track.id, tier)
        return Prediction(
            completed=False,
            error=f"{type(exc).__name__}: {exc}",
            tier=tier,
        )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _CACHE_SCHEMA_VERSION,
        **prediction_to_dict(prediction),
    }
    cache_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return prediction


def _run_tier(
    manifest: EvalManifest,
    tracks: list[TrackSpec],
    args: argparse.Namespace,
    tier: str,
) -> dict:
    results = []
    for track in tracks:
        prediction = _run_track(manifest, track, args, tier)
        if not prediction.completed:
            logger.error("[%s] failed: %s", track.id, prediction.error)

        try:
            _, gt_path, chord_gt_path = resolve_track_paths(
                manifest,
                track,
                manifest_path=args.manifest,
                data_root_override=args.data_root,
            )
            ground_truth = load_ground_truth(
                track, gt_path=gt_path, chord_gt_path=chord_gt_path
            )
        except (ManifestError, GroundTruthError) as exc:
            logger.error("[%s] ground truth failed: %s", track.id, exc)
            prediction = Prediction(
                completed=False,
                error=f"ground_truth: {exc}",
                tier=tier,
            )
            results.append(evaluate_track(track, prediction, GroundTruth()))
            continue

        result = evaluate_track(track, prediction, ground_truth)
        results.append(result)
        logger.info(
            "[%s] verdict=%s runtime=%.0fms",
            track.id,
            result.verdict,
            prediction.runtime_ms,
        )
    return build_report(manifest, tier, results)


def _tier_report_path(base: Path, tier: str) -> Path:
    return base.with_name(f"{base.stem}-{tier}{base.suffix}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        tracks = _select_tracks(manifest, args)
    except (ManifestError, SystemExit) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    if args.tier == "all":
        from app.student.inference import StudentModel

        tiers = list(_TIERS)
        if StudentModel().is_available():
            tiers.append(_STUDENT_TIER)
        else:
            logger.info("student tier skipped: %s", StudentModel().unavailable_reason())
    else:
        tiers = [args.tier]
    logger.info(
        "Evaluating %d track(s) with tier(s)=%s from %s",
        len(tracks),
        ",".join(tiers),
        args.manifest,
    )

    reports: dict[str, dict] = {}
    for tier in tiers:
        report = _run_tier(manifest, tracks, args, tier)
        reports[tier] = report
        if args.tier == "all":
            tier_path = _tier_report_path(args.report, tier)
            write_report_json(report, tier_path)
            write_report_markdown(report, tier_path.with_suffix(".md"))
        else:
            write_report_json(report, args.report)
            write_report_markdown(
                report, args.markdown or args.report.with_suffix(".md")
            )
        print(
            f"[DONE] tier={tier} tracks={len(tracks)} "
            f"verdicts={report['verdicts']}"
        )

    if args.tier == "all":
        comparison = {
            "schema_version": 3,
            "manifest_id": manifest.manifest_id,
            "tiers": {
                tier: {
                    "aggregates": report["aggregates"],
                    "verdicts": report["verdicts"],
                    "failures": report["failures"],
                }
                for tier, report in reports.items()
            },
        }
        write_report_json(comparison, args.report)
        write_comparison_markdown(
            comparison, (args.markdown or args.report.with_suffix(".md"))
        )
        print(f"[DONE] comparison report={args.report}")

    failed_tracks = sum(
        report["aggregates"]["failed"] for report in reports.values()
    )
    if args.fail_on_track_error and failed_tracks:
        print(
            f"[FAIL] {failed_tracks} tier-track failure(s)",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
