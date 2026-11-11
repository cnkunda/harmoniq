"""Deterministic report assembly for the W0 evaluation harness.

A report is diffable across commits: keys are sorted, floats are rounded,
and no wall-clock timestamps or absolute paths are written. The manifest
id + tier identify a run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.evaluation.ground_truth import GroundTruth, GTChord, GTNote
from app.evaluation.manifest import EvalManifest, TrackSpec
from app.evaluation.metrics import (
    chord_event_prf,
    chord_frame_accuracy,
    chord_root_accuracy,
    calibration_metrics,
    note_metrics,
)
from app.evaluation.verdict import (
    Verdict,
    VerdictInput,
    compute_verdict,
    verdict_matches,
)

REPORT_SCHEMA_VERSION = 3


@dataclass
class Prediction:
    """A tier's output for one track."""

    notes: list[GTNote] = field(default_factory=list)
    chords: list[GTChord] = field(default_factory=list)
    runtime_ms: float = 0.0
    completed: bool = True
    error: str | None = None
    tier: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrackResult:
    """Prediction + ground truth + computed metrics for one track."""

    spec: TrackSpec
    prediction: Prediction
    ground_truth: GroundTruth
    metrics: dict[str, Any]
    verdict: Verdict | None
    expected_verdict_matches: bool | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.spec.id,
            "source": self.spec.source,
            "split": self.spec.split,
            "recording_type": self.spec.recording_type,
            "instrument_count": self.spec.instrument_count,
            "tuning": self.spec.tuning,
            "capo": self.spec.capo,
            "tier": self.prediction.tier,
            "completed": self.prediction.completed,
            "error": self.prediction.error,
            "runtime_ms": round(float(self.prediction.runtime_ms), 3),
            "qualitative": self.spec.qualitative,
            "verdict": self.verdict,
            "expected_verdict": self.spec.expected_verdict,
            "expected_verdict_matches": self.expected_verdict_matches,
            "metrics": self.metrics,
        }


def prediction_to_dict(prediction: Prediction) -> dict[str, Any]:
    """Serialize a prediction for the on-disk cache."""
    return {
        "tier": prediction.tier,
        "completed": prediction.completed,
        "error": prediction.error,
        "runtime_ms": prediction.runtime_ms,
        "metadata": prediction.metadata,
        "notes": [
            {
                "pitch": note.pitch,
                "onset": note.onset,
                "offset": note.offset,
                "velocity": note.velocity,
                "program": note.program,
                "confidence": note.confidence,
            }
            for note in prediction.notes
        ],
        "chords": [
            {
                "start": chord.start,
                "end": chord.end,
                "chord": chord.chord,
                "confidence": chord.confidence,
            }
            for chord in prediction.chords
        ],
    }


def prediction_from_dict(payload: dict[str, Any]) -> Prediction:
    """Deserialize a cached prediction."""
    notes = [
        GTNote(
            pitch=int(item["pitch"]),
            onset=float(item["onset"]),
            offset=float(item["offset"]),
            velocity=(
                int(item["velocity"]) if item.get("velocity") is not None else None
            ),
            program=(
                int(item["program"]) if item.get("program") is not None else None
            ),
            confidence=(
                float(item["confidence"])
                if item.get("confidence") is not None
                else None
            ),
        )
        for item in payload.get("notes", [])
    ]
    chords = [
        GTChord(
            start=float(item["start"]),
            end=float(item["end"]),
            chord=str(item["chord"]),
            confidence=(
                float(item["confidence"])
                if item.get("confidence") is not None
                else None
            ),
        )
        for item in payload.get("chords", [])
    ]
    return Prediction(
        notes=notes,
        chords=chords,
        runtime_ms=float(payload.get("runtime_ms", 0.0)),
        completed=bool(payload.get("completed", True)),
        error=payload.get("error"),
        tier=str(payload.get("tier", "unknown")),
        metadata=dict(payload.get("metadata") or {}),
    )


def _mean(values: Iterable[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _mean_confidence(notes: Iterable[GTNote]) -> float | None:
    return _mean(note.confidence for note in notes)


def _mean_chord_confidence(chords: Iterable[GTChord]) -> float | None:
    return _mean(
        chord.confidence for chord in chords if chord.chord != "N"
    )


def evaluate_track(
    spec: TrackSpec,
    prediction: Prediction,
    ground_truth: GroundTruth,
) -> TrackResult:
    """Score one prediction against its ground truth and apply the rubric."""
    metrics: dict[str, Any] = {}

    if prediction.completed:
        if ground_truth.has_notes:
            metrics["notes"] = note_metrics(
                ground_truth.notes, prediction.notes
            )
        if ground_truth.has_chords:
            frame = chord_frame_accuracy(
                ground_truth.chords, prediction.chords
            )
            event_prf = chord_event_prf(
                ground_truth.chords, prediction.chords
            )
            root = chord_root_accuracy(
                ground_truth.chords, prediction.chords
            )
            metrics["chords"] = {
                **frame,
                "root_accuracy": root["root_accuracy"],
                "root_frames": root["frames"],
                "event_prf": event_prf.as_dict(),
            }
            duration = max(
                [chord.end for chord in ground_truth.chords]
                + [chord.end for chord in prediction.chords]
                + [0.0]
            )
            metrics["calibration"] = calibration_metrics(
                ground_truth.chords,
                prediction.chords,
                audio_duration=duration,
            )

    mean_chord_confidence = _mean_chord_confidence(prediction.chords)
    mean_note_confidence = _mean_confidence(prediction.notes)
    # CRNN/chroma are chord-only baselines. Do not fail them for the solo
    # component they are not designed to produce.
    expects_notes = spec.expects_notes and prediction.tier not in ("crnn", "chroma")
    verdict = compute_verdict(
        VerdictInput(
            completed=prediction.completed,
            error=prediction.error,
            has_chords=any(chord.chord != "N" for chord in prediction.chords),
            mean_chord_confidence=mean_chord_confidence,
            expects_notes=expects_notes,
            has_notes=bool(prediction.notes),
            mean_note_confidence=mean_note_confidence,
            qualitative=spec.qualitative,
        )
    )

    return TrackResult(
        spec=spec,
        prediction=prediction,
        ground_truth=ground_truth,
        metrics=metrics,
        verdict=verdict,
        expected_verdict_matches=verdict_matches(
            spec.expected_verdict, verdict
        ),
    )


def _aggregate_prf(results: list[TrackResult], key: str) -> dict[str, Any] | None:
    tp = fp = fn = 0
    seen = False
    for result in results:
        block = result.metrics.get("notes", {}).get(key)
        if not isinstance(block, dict):
            continue
        seen = True
        tp += int(block.get("tp", 0))
        fp += int(block.get("fp", 0))
        fn += int(block.get("fn", 0))
    if not seen:
        return None
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def _aggregate(results: list[TrackResult]) -> dict[str, Any]:
    completed = [result for result in results if result.prediction.completed]
    chord_frames = [
        float(result.metrics["chords"]["frame_accuracy"])
        for result in completed
        if result.metrics.get("chords", {}).get("frame_accuracy") is not None
    ]
    chord_roots = [
        float(result.metrics["chords"]["root_accuracy"])
        for result in completed
        if result.metrics.get("chords", {}).get("root_accuracy") is not None
    ]
    eces = [
        float(result.metrics["calibration"]["ece"])
        for result in completed
        if result.metrics.get("calibration", {}).get("ece") is not None
    ]
    runtimes = [result.prediction.runtime_ms for result in completed]
    return {
        "tracks": len(results),
        "completed": len(completed),
        "failed": len(results) - len(completed),
        "notes": {
            key: _aggregate_prf(results, key)
            for key in ("onset_pitch", "onset_multi", "offset_multi")
        },
        "chord_frame_accuracy": (
            round(sum(chord_frames) / len(chord_frames), 6)
            if chord_frames
            else None
        ),
        "chord_root_accuracy": (
            round(sum(chord_roots) / len(chord_roots), 6)
            if chord_roots
            else None
        ),
        "ece": (
            round(sum(eces) / len(eces), 6) if eces else None
        ),
        "runtime_ms_mean": (
            round(sum(runtimes) / len(runtimes), 3) if runtimes else None
        ),
        "runtime_ms_total": round(sum(runtimes), 3),
    }


def _strata(
    results: list[TrackResult],
    getter,
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[TrackResult]] = {}
    for result in results:
        groups.setdefault(str(getter(result)), []).append(result)
    output: dict[str, dict[str, Any]] = {}
    for name in sorted(groups):
        group = groups[name]
        output[name] = _aggregate(group)
    return output


def build_report(
    manifest: EvalManifest,
    tier: str,
    results: list[TrackResult],
) -> dict[str, Any]:
    """Assemble the deterministic report payload."""
    verdict_counts = {"pass": 0, "warn": 0, "fail": 0, "unscored": 0}
    for result in results:
        verdict_counts[result.verdict or "unscored"] += 1

    failures = [
        {
            "id": result.spec.id,
            "error": result.prediction.error,
            "completed": result.prediction.completed,
        }
        for result in results
        if not result.prediction.completed
    ]

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "manifest_id": manifest.manifest_id,
        "tier": tier,
        "tracks": [result.as_dict() for result in results],
        "aggregates": _aggregate(results),
        "strata": {
            "instrument_count": _strata(
                results, lambda r: r.spec.instrument_count
            ),
            "recording_type": _strata(
                results, lambda r: r.spec.recording_type
            ),
            "source": _strata(results, lambda r: r.spec.source),
            "split": _strata(results, lambda r: r.spec.split),
        },
        "verdicts": verdict_counts,
        "verdict_expectation_mismatches": [
            {
                "id": result.spec.id,
                "expected": result.spec.expected_verdict,
                "actual": result.verdict,
            }
            for result in results
            if result.expected_verdict_matches is False
        ],
        "failures": failures,
    }


def write_report_json(report: dict[str, Any], path: Path) -> None:
    """Write the report with sorted keys and a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    """Render a compact human-readable summary."""
    lines: list[str] = []
    lines.append(f"# AMT evaluation — {report['manifest_id']} / {report['tier']}")
    lines.append("")
    aggregates = report["aggregates"]
    lines.append(
        f"Tracks: {aggregates['tracks']} · completed: {aggregates['completed']} "
        f"· failed: {aggregates['failed']}"
    )
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | ---: |")
    lines.append(
        f"| Onset (pitch) F1 | {_fmt(aggregates['notes']['onset_pitch']['f1'] if aggregates['notes']['onset_pitch'] else None)} |"
    )
    lines.append(
        f"| Onset (pitch+program) F1 | {_fmt(aggregates['notes']['onset_multi']['f1'] if aggregates['notes']['onset_multi'] else None)} |"
    )
    lines.append(
        f"| Offset (pitch+program) F1 | {_fmt(aggregates['notes']['offset_multi']['f1'] if aggregates['notes']['offset_multi'] else None)} |"
    )
    lines.append(f"| Chord frame accuracy | {_fmt(aggregates['chord_frame_accuracy'])} |")
    lines.append(f"| ECE | {_fmt(aggregates['ece'])} |")
    lines.append(f"| Runtime mean (ms) | {_fmt(aggregates['runtime_ms_mean'])} |")
    lines.append("")
    lines.append(
        "Verdicts: "
        + ", ".join(
            f"{name}={count}" for name, count in sorted(report["verdicts"].items())
        )
    )
    lines.append("")
    lines.append("| Track | Source | Split | Verdict | Onset F1 | Offset F1 | Chord acc | ECE |")
    lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | ---: |")
    for track in report["tracks"]:
        notes = track["metrics"].get("notes", {})
        chords = track["metrics"].get("chords", {})
        calibration = track["metrics"].get("calibration", {})
        onset = notes.get("onset_multi", {}).get("f1") if notes else None
        offset = notes.get("offset_multi", {}).get("f1") if notes else None
        lines.append(
            f"| {track['id']} | {track['source']} | {track['split']} | "
            f"{track['verdict']} | {_fmt(onset)} | {_fmt(offset)} | "
            f"{_fmt(chords.get('frame_accuracy'))} | {_fmt(calibration.get('ece'))} |"
        )
    if report["failures"]:
        lines.append("")
        lines.append("## Failures")
        lines.append("")
        for failure in report["failures"]:
            lines.append(f"- `{failure['id']}`: {failure['error']}")
    if report["verdict_expectation_mismatches"]:
        lines.append("")
        lines.append("## Verdict mismatches")
        lines.append("")
        for mismatch in report["verdict_expectation_mismatches"]:
            lines.append(
                f"- `{mismatch['id']}`: expected {mismatch['expected']}, got {mismatch['actual']}"
            )
    lines.append("")
    return "\n".join(lines)


def write_report_markdown(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")


def render_comparison_markdown(comparison: dict[str, Any]) -> str:
    """Render a tier comparison produced by ``eval_amt.py --tier all``."""
    lines: list[str] = []
    lines.append(f"# AMT tier comparison — {comparison['manifest_id']}")
    lines.append("")
    lines.append(
        "| Tier | Tracks | Onset F1 | Offset F1 | Chord acc | ECE | Runtime mean (ms) | Verdicts |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for tier in sorted(comparison["tiers"]):
        report = comparison["tiers"][tier]
        aggregates = report["aggregates"]
        notes = aggregates.get("notes", {})
        onset = notes.get("onset_multi")
        offset = notes.get("offset_multi")
        verdicts = report.get("verdicts", {})
        lines.append(
            f"| {tier} | {aggregates.get('tracks', 0)} | "
            f"{_fmt(onset.get('f1') if onset else None)} | "
            f"{_fmt(offset.get('f1') if offset else None)} | "
            f"{_fmt(aggregates.get('chord_frame_accuracy'))} | "
            f"{_fmt(aggregates.get('ece'))} | "
            f"{_fmt(aggregates.get('runtime_ms_mean'))} | "
            + ", ".join(f"{name}={count}" for name, count in sorted(verdicts.items()))
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_comparison_markdown(comparison: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_comparison_markdown(comparison), encoding="utf-8")
