"""W5: aggregate chord-confidence calibration and evaluate the quality gate.

Reads one or more per-source ``eval_amt.py`` reports (same tier), pools the
duration-weighted calibration bins, and joins each track's chord frame
accuracy with the reference-free audio-quality snapshot used by the ingest
gate. The output is deterministic JSON + Markdown so W5/W6 can diff it.

Usage (from ``backend/``)::

    python scripts/eval_calibration_quality.py \
        --manifest ../docs/eval/amt_manifest.json \
        --eval-report ../docs/audit/amt/w5_eval_mt3-guitarset.json \
        --eval-report ../docs/audit/amt/w5_eval_mt3-rwc_p.json \
        --out-json ../docs/audit/amt/w5_calibration.json \
        --out-md ../docs/audit/amt/w5_calibration.md

Only chord-template confidence is calibrated. MT3 note confidence is a
placeholder (``0.9``) and is deliberately excluded -- see docs/eval/README.md.

Use ``--skip-quality`` to skip audio decoding (calibration only).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.evaluation.manifest import (  # noqa: E402
    EvalManifest,
    ManifestError,
    load_manifest,
    resolve_track_paths,
)

logger = logging.getLogger("harmoniq.w5")

SCHEMA_VERSION = 1
DEFAULT_ACCURACY_THRESHOLD = 0.5
_NUM_BINS = 10


@dataclass(frozen=True)
class TrackCalibration:
    """One track's calibration bins + accuracy, flattened for aggregation."""

    id: str
    source: str
    split: str
    instrument_count: int
    tier: str
    frame_accuracy: float | None
    bins: list[dict[str, Any]]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=_REPO_ROOT / "docs" / "eval" / "amt_manifest.json",
    )
    parser.add_argument(
        "--eval-report",
        type=Path,
        action="append",
        default=[],
        help="Per-source eval_amt report (repeatable).",
    )
    parser.add_argument(
        "--eval-report-dir",
        type=Path,
        default=None,
        help="Directory of eval_amt reports (all *.json; tier must match).",
    )
    parser.add_argument("--tier", default=None, help="Filter reports by tier.")
    parser.add_argument(
        "--out-json",
        type=Path,
        default=_REPO_ROOT / "docs" / "audit" / "amt" / "w5_calibration.json",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=_REPO_ROOT / "docs" / "audit" / "amt" / "w5_calibration.md",
    )
    parser.add_argument(
        "--accuracy-threshold",
        type=float,
        default=DEFAULT_ACCURACY_THRESHOLD,
        help="Chord frame accuracy treated as a 'good' transcription for the gate matrix.",
    )
    parser.add_argument(
        "--skip-quality",
        action="store_true",
        help="Skip audio decoding and the recording-quality evaluation.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Override the manifest data_root.",
    )
    return parser.parse_args(argv)


def _report_paths(args: argparse.Namespace) -> list[Path]:
    paths = list(args.eval_report)
    if args.eval_report_dir is not None:
        if not args.eval_report_dir.is_dir():
            raise SystemExit(f"Report directory not found: {args.eval_report_dir}")
        paths.extend(sorted(args.eval_report_dir.glob("*.json")))
    if not paths:
        raise SystemExit("Provide --eval-report or --eval-report-dir")
    return paths


def _load_reports(paths: Iterable[Path]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file():
            raise SystemExit(f"Report not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "tracks" not in payload:
            raise SystemExit(
                f"{path} is not a per-tier eval report (missing 'tracks')"
            )
        reports.append(payload)
    return reports


def _select_reports(
    reports: list[dict[str, Any]], tier: str | None
) -> tuple[list[dict[str, Any]], str]:
    tiers = {str(report.get("tier", "unknown")) for report in reports}
    if tier is not None:
        reports = [report for report in reports if report.get("tier") == tier]
        tiers = {str(report.get("tier", "unknown")) for report in reports}
        if not reports:
            raise SystemExit(f"No reports for tier {tier!r}")
    if len(tiers) != 1:
        raise SystemExit(
            "All reports must be the same tier; got " + ", ".join(sorted(tiers))
        )
    return reports, next(iter(tiers))


def _track_rows(reports: list[dict[str, Any]]) -> list[TrackCalibration]:
    rows: list[TrackCalibration] = []
    seen: set[str] = set()
    for report in reports:
        for track in report.get("tracks", []):
            track_id = str(track.get("id"))
            if track_id in seen:
                continue
            seen.add(track_id)
            metrics = track.get("metrics") or {}
            chords = metrics.get("chords") or {}
            calibration = metrics.get("calibration") or {}
            bins = calibration.get("bins") or []
            rows.append(
                TrackCalibration(
                    id=track_id,
                    source=str(track.get("source", "unknown")),
                    split=str(track.get("split", "unknown")),
                    instrument_count=int(track.get("instrument_count") or 0),
                    tier=str(track.get("tier", "unknown")),
                    frame_accuracy=(
                        float(chords["frame_accuracy"])
                        if chords.get("frame_accuracy") is not None
                        else None
                    ),
                    bins=list(bins),
                )
            )
    rows.sort(key=lambda row: row.id)
    return rows


def _pool_bins(rows: Iterable[TrackCalibration]) -> list[dict[str, Any]]:
    """Pool equal-width bins by duration weight.

    ``eval_amt`` emits ``bins`` with identical edges per track, so pooling by
    edge index is exact for the duration-weighted ECE definition.
    """
    pooled: list[dict[str, float | int]] = [
        {
            "lower": round(index / _NUM_BINS, 6),
            "upper": round((index + 1) / _NUM_BINS, 6),
            "count": 0,
            "weight": 0.0,
            "confidence_weighted": 0.0,
            "correct_weighted": 0.0,
        }
        for index in range(_NUM_BINS)
    ]
    for row in rows:
        for index, item in enumerate(row.bins[:_NUM_BINS]):
            weight = float(item.get("weight") or 0.0)
            if weight <= 0.0:
                continue
            pooled[index]["count"] = int(pooled[index]["count"]) + int(
                item.get("count") or 0
            )
            pooled[index]["weight"] = float(pooled[index]["weight"]) + weight
            pooled[index]["confidence_weighted"] = float(
                pooled[index]["confidence_weighted"]
            ) + float(item.get("avg_confidence") or 0.0) * weight
            pooled[index]["correct_weighted"] = float(
                pooled[index]["correct_weighted"]
            ) + float(item.get("accuracy") or 0.0) * weight

    output: list[dict[str, Any]] = []
    for item in pooled:
        weight = float(item["weight"])
        avg_confidence = (
            float(item["confidence_weighted"]) / weight if weight > 0 else 0.0
        )
        accuracy = float(item["correct_weighted"]) / weight if weight > 0 else 0.0
        output.append(
            {
                "lower": round(float(item["lower"]), 6),
                "upper": round(float(item["upper"]), 6),
                "count": int(item["count"]),
                "weight": round(weight, 6),
                "avg_confidence": round(avg_confidence, 6),
                "accuracy": round(accuracy, 6),
                "gap": round(abs(accuracy - avg_confidence), 6),
            }
        )
    return output


def _calibration_summary(rows: list[TrackCalibration]) -> dict[str, Any]:
    bins = _pool_bins(rows)
    total_weight = sum(float(item["weight"]) for item in bins)
    if total_weight <= 0.0:
        return {
            "samples": 0,
            "total_weight_s": 0.0,
            "ece": None,
            "overall_accuracy": None,
            "mean_confidence": None,
            "bins": bins,
        }
    ece = sum(
        (float(item["weight"]) / total_weight) * float(item["gap"])
        for item in bins
    )
    accuracy = sum(
        float(item["accuracy"]) * float(item["weight"]) for item in bins
    ) / total_weight
    confidence = sum(
        float(item["avg_confidence"]) * float(item["weight"]) for item in bins
    ) / total_weight
    return {
        "samples": sum(int(item["count"]) for item in bins),
        "total_weight_s": round(total_weight, 6),
        "ece": round(ece, 6),
        "overall_accuracy": round(accuracy, 6),
        "mean_confidence": round(confidence, 6),
        "bins": bins,
    }


def _group_summaries(
    rows: list[TrackCalibration], key: Any
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[TrackCalibration]] = {}
    for row in rows:
        groups.setdefault(str(key(row)), []).append(row)
    return {
        name: _calibration_summary(groups[name])
        for name in sorted(groups)
    }


def _accuracy_bucket(value: float | None, threshold: float) -> str | None:
    if value is None:
        return None
    return "high" if value >= threshold else "low"


def _quality_distribution(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    median = (
        ordered[middle]
        if count % 2
        else (ordered[middle - 1] + ordered[middle]) / 2.0
    )
    return {
        "n": count,
        "min": round(ordered[0], 6),
        "max": round(ordered[-1], 6),
        "mean": round(sum(ordered) / count, 6),
        "median": round(median, 6),
    }


def _gate_sweep(
    samples: list[dict[str, Any]],
    metric: str,
    *,
    higher_is_better: bool,
    threshold: float,
    accuracy_threshold: float,
) -> dict[str, Any] | None:
    accepted: list[float] = []
    rejected: list[float] = []
    for sample in samples:
        quality = sample["quality"]
        value = float(quality.get(metric))
        accepted_here = value >= threshold if higher_is_better else value <= threshold
        accuracy = float(sample["accuracy"])
        if accepted_here:
            accepted.append(accuracy)
        else:
            rejected.append(accuracy)
    if not accepted or not rejected:
        return None
    accepted_mean = sum(accepted) / len(accepted)
    rejected_mean = sum(rejected) / len(rejected)
    return {
        "metric": metric,
        "higher_is_better": higher_is_better,
        "threshold": round(threshold, 6),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "accepted_mean_accuracy": round(accepted_mean, 6),
        "rejected_mean_accuracy": round(rejected_mean, 6),
        "separation": round(accepted_mean - rejected_mean, 6),
        "accepted_high_accuracy_share": round(
            sum(1 for value in accepted if value >= accuracy_threshold)
            / len(accepted),
            6,
        ),
        "rejected_high_accuracy_share": round(
            sum(1 for value in rejected if value >= accuracy_threshold)
            / len(rejected),
            6,
        ),
    }


def _quality_evaluation(
    rows: list[TrackCalibration],
    manifest: EvalManifest,
    manifest_path: Path,
    data_root: Path | None,
    accuracy_threshold: float,
) -> dict[str, Any]:
    from app.audio_quality import (
        AudioQualityAnalysisError,
        analyze_audio_quality,
    )

    specs = {spec.id: spec for spec in manifest.tracks}
    samples: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for row in rows:
        if row.frame_accuracy is None:
            continue
        spec = specs.get(row.id)
        if spec is None:
            errors.append({"id": row.id, "error": "track missing from manifest"})
            continue
        try:
            audio, _gt_path, _chord_gt_path = resolve_track_paths(
                manifest,
                spec,
                manifest_path=manifest_path,
                data_root_override=data_root,
            )
            quality = analyze_audio_quality(audio)
        except (ManifestError, AudioQualityAnalysisError, OSError) as exc:
            logger.warning("[%s] quality evaluation failed: %s", row.id, exc)
            errors.append({"id": row.id, "error": str(exc)})
            continue
        samples.append(
            {
                "id": row.id,
                "source": row.source,
                "accuracy": row.frame_accuracy,
                "quality": quality.model_dump(),
            }
        )

    threshold = accuracy_threshold
    gate = {
        "acceptable": 0,
        "rejected": 0,
        "true_accept": 0,
        "false_accept": 0,
        "true_reject": 0,
        "false_reject": 0,
        "accepted_mean_accuracy": None,
        "rejected_mean_accuracy": None,
    }
    accepted_acc: list[float] = []
    rejected_acc: list[float] = []
    for sample in samples:
        accurate = float(sample["accuracy"]) >= threshold
        acceptable = bool(sample["quality"].get("acceptable"))
        if acceptable:
            gate["acceptable"] += 1
            accepted_acc.append(float(sample["accuracy"]))
            gate["true_accept" if accurate else "false_accept"] += 1
        else:
            gate["rejected"] += 1
            rejected_acc.append(float(sample["accuracy"]))
            gate["true_reject" if not accurate else "false_reject"] += 1
    if accepted_acc:
        gate["accepted_mean_accuracy"] = round(
            sum(accepted_acc) / len(accepted_acc), 6
        )
    if rejected_acc:
        gate["rejected_mean_accuracy"] = round(
            sum(rejected_acc) / len(rejected_acc), 6
        )

    sweep: list[dict[str, Any]] = []
    for value in [index / 20.0 for index in range(21)]:
        item = _gate_sweep(
            samples,
            "score",
            higher_is_better=True,
            threshold=value,
            accuracy_threshold=threshold,
        )
        if item is not None:
            sweep.append(item)
    for value in [0.0, 3.0, 6.0, 10.0, 15.0, 20.0]:
        item = _gate_sweep(
            samples,
            "snr_db",
            higher_is_better=True,
            threshold=value,
            accuracy_threshold=threshold,
        )
        if item is not None:
            sweep.append(item)
    for value in [0.0, 0.005, 0.01, 0.02, 0.05]:
        item = _gate_sweep(
            samples,
            "clipping_ratio",
            higher_is_better=False,
            threshold=value,
            accuracy_threshold=threshold,
        )
        if item is not None:
            sweep.append(item)
    for value in [0.5, 0.7, 0.9, 0.95]:
        item = _gate_sweep(
            samples,
            "silence_ratio",
            higher_is_better=False,
            threshold=value,
            accuracy_threshold=threshold,
        )
        if item is not None:
            sweep.append(item)

    accepted_mean = gate["accepted_mean_accuracy"]
    rejected_mean = gate["rejected_mean_accuracy"]
    if accepted_mean is None or rejected_mean is None:
        recommendation = "insufficient rejected or accepted tracks to evaluate the gate"
    elif accepted_mean >= rejected_mean and accepted_mean >= threshold:
        recommendation = "keep: accepted tracks are at least as accurate as rejected tracks"
    else:
        recommendation = "review: accepted tracks are not more accurate than rejected tracks"

    distributions = {
        "score": _quality_distribution(
            [float(sample["quality"]["score"]) for sample in samples]
        ),
        "snr_db": _quality_distribution(
            [float(sample["quality"]["snr_db"]) for sample in samples]
        ),
        "clipping_ratio": _quality_distribution(
            [float(sample["quality"]["clipping_ratio"]) for sample in samples]
        ),
        "silence_ratio": _quality_distribution(
            [float(sample["quality"]["silence_ratio"]) for sample in samples]
        ),
    }

    return {
        "tracks": len(samples),
        "accuracy_threshold": round(threshold, 6),
        "gate": gate,
        "distributions": distributions,
        "sweep": sweep,
        "recommendation": recommendation,
        "errors": errors,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# W5 calibration & recording-quality evaluation — {report['manifest_id']}")
    lines.append("")
    lines.append(f"Tier: `{report['tier']}` · tracks: {report['tracks']}")
    lines.append("")
    calibration = report["calibration"]
    lines.append("## Chord-confidence calibration")
    lines.append("")
    lines.append(
        f"Samples: {calibration['samples']} · duration: "
        f"{_fmt(calibration['total_weight_s'])} s · ECE: {_fmt(calibration['ece'])} "
        f"· accuracy: {_fmt(calibration['overall_accuracy'])} · "
        f"mean confidence: {_fmt(calibration['mean_confidence'])}"
    )
    lines.append("")
    lines.append("| Bin | Events | Duration (s) | Avg confidence | Accuracy | Gap |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for item in calibration["bins"]:
        lines.append(
            f"| {item['lower']:.1f}–{item['upper']:.1f} | {item['count']} | "
            f"{_fmt(item['weight'])} | {_fmt(item['avg_confidence'])} | "
            f"{_fmt(item['accuracy'])} | {_fmt(item['gap'])} |"
        )
    lines.append("")
    lines.append("### By source")
    lines.append("")
    lines.append("| Source | Events | ECE | Accuracy | Mean confidence |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for name, summary in report["by_source"].items():
        lines.append(
            f"| {name} | {summary['samples']} | {_fmt(summary['ece'])} | "
            f"{_fmt(summary['overall_accuracy'])} | {_fmt(summary['mean_confidence'])} |"
        )
    lines.append("")
    quality = report.get("recording_quality")
    if quality is None:
        lines.append("## Recording-quality gate")
        lines.append("")
        lines.append("Skipped (`--skip-quality`).")
        lines.append("")
        return "\n".join(lines)
    lines.append("## Recording-quality gate")
    lines.append("")
    gate = quality["gate"]
    lines.append(
        f"Tracks evaluated: {quality['tracks']} · accuracy threshold: "
        f"{_fmt(quality['accuracy_threshold'])}"
    )
    lines.append("")
    lines.append("| | High accuracy | Low accuracy | Total |")
    lines.append("| --- | ---: | ---: | ---: |")
    lines.append(
        f"| Accepted | {gate['true_accept']} | {gate['false_accept']} | {gate['acceptable']} |"
    )
    lines.append(
        f"| Rejected | {gate['false_reject']} | {gate['true_reject']} | {gate['rejected']} |"
    )
    lines.append("")
    lines.append(
        f"Accepted mean accuracy: {_fmt(gate['accepted_mean_accuracy'])} · "
        f"rejected mean accuracy: {_fmt(gate['rejected_mean_accuracy'])}"
    )
    lines.append("")
    lines.append(f"Recommendation: **{quality['recommendation']}**")
    lines.append("")
    lines.append("| Metric | Threshold | Accepted | Rejected | Accepted acc | Rejected acc | Separation |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for item in quality["sweep"]:
        lines.append(
            f"| {item['metric']} | {_fmt(item['threshold'])} | {item['accepted']} | "
            f"{item['rejected']} | {_fmt(item['accepted_mean_accuracy'])} | "
            f"{_fmt(item['rejected_mean_accuracy'])} | {_fmt(item['separation'])} |"
        )
    if quality["errors"]:
        lines.append("")
        lines.append("## Quality evaluation errors")
        lines.append("")
        for item in quality["errors"]:
            lines.append(f"- `{item['id']}`: {item['error']}")
    lines.append("")
    return "\n".join(lines)


def _write_outputs(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_render_markdown(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        reports = _load_reports(_report_paths(args))
        reports, tier = _select_reports(reports, args.tier)
    except (ManifestError, SystemExit) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    rows = _track_rows(reports)
    logger.info("Aggregating %d tracks from %d report(s)", len(rows), len(reports))
    calibration = _calibration_summary(rows)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": manifest.manifest_id,
        "tier": tier,
        "tracks": len(rows),
        "calibration": calibration,
        "by_source": _group_summaries(rows, lambda row: row.source),
        "by_split": _group_summaries(rows, lambda row: row.split),
        "by_instrument_count": _group_summaries(
            rows, lambda row: row.instrument_count
        ),
        "recording_quality": None,
    }

    if not args.skip_quality:
        report["recording_quality"] = _quality_evaluation(
            rows,
            manifest,
            args.manifest,
            args.data_root,
            args.accuracy_threshold,
        )

    _write_outputs(report, args.out_json, args.out_md)
    print(f"[DONE] wrote {args.out_json} and {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
