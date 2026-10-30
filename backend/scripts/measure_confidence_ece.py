"""Commit 184: measure calibration of the heuristic chord confidence on GuitarSet.

The analysis pipeline surfaces ``ChordEvent.confidence`` (template coverage on
the MT3 path) as a coarse confidence band. This script checks whether that
value is calibrated: it runs MT3 on a small GuitarSet test split, decodes the
chord timeline, and compares each predicted event against the full annotation
timeline.

Usage (from backend/, with .venv-wsl active):
    python scripts/measure_confidence_ece.py --limit 3

The default output is backend/data/evaluation/ece_mt3.json (gitignored).
MT3 inference is slow (~5-10 minutes per short track); use --cache-dir to
avoid rerunning tracks.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.confidence_calibration import (  # noqa: E402
    bin_calibration,
    chord_to_mirex_index,
    expected_calibration_error,
    majority_gt_index,
)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_DATA_DIR = _BACKEND_DIR / "data" / "guitarset"
_DEFAULT_CACHE_DIR = _BACKEND_DIR / "data" / "evaluation" / "mt3_cache"
_DEFAULT_OUT = _BACKEND_DIR / "data" / "evaluation" / "ece_mt3.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=_DEFAULT_DATA_DIR)
    parser.add_argument("--limit", type=int, default=3, help="Number of test tracks (default: 3)")
    parser.add_argument(
        "--track",
        action="append",
        default=[],
        help="Explicit GuitarSet track stem (repeatable); overrides --limit",
    )
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--cache-dir", type=Path, default=_DEFAULT_CACHE_DIR)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    parser.add_argument("--refresh", action="store_true", help="Ignore cached MT3 timelines")
    return parser.parse_args()


def _select_tracks(timelines_dir: Path, limit: int, requested: list[str]) -> list[str]:
    if requested:
        return requested
    if limit < 1:
        raise SystemExit("--limit must be at least 1")

    candidates = sorted(timelines_dir.glob("05_*_comp.json"))
    if not candidates:
        candidates = sorted(timelines_dir.glob("05_*.json"))
    if not candidates:
        raise SystemExit(f"No player-05 GuitarSet timelines found under {timelines_dir}")

    return [path.stem for path in candidates[:limit]]


def _load_ground_truth(timeline_path: Path) -> list[tuple[float, float, int]]:
    raw = json.loads(timeline_path.read_text(encoding="utf-8"))
    intervals: list[tuple[float, float, int]] = []
    for entry in raw:
        start = float(entry["start"])
        end = float(entry["end"])
        chord = str(entry["chord"])
        if end <= start:
            continue
        intervals.append((start, end, chord_to_mirex_index(chord)))
    if not intervals:
        raise SystemExit(f"Ground-truth timeline is empty: {timeline_path}")
    return intervals


def _load_or_run_mt3(
    track: str,
    data_dir: Path,
    cache_dir: Path,
    *,
    refresh: bool,
) -> dict[str, Any]:
    cache_path = cache_dir / f"{track}.json"
    if cache_path.is_file() and not refresh:
        print(f"[ece] {track}: using cached MT3 timeline", flush=True)
        return json.loads(cache_path.read_text(encoding="utf-8"))

    audio_path = data_dir / "raw" / "audio_mono-mix" / f"{track}_mix.wav"
    if not audio_path.is_file():
        raise SystemExit(f"Audio not found for {track}: {audio_path}")

    from app.beat_grid import estimate_beat_grid
    from app.mt3.chord_decoder import decode_events_to_chord_timeline
    from app.mt3.model_server import mt3_infer
    from app.schemas import BeatGrid

    print(f"[ece] {track}: running MT3 (this can take several minutes)...", flush=True)
    stream = mt3_infer(str(audio_path))
    if not stream.events:
        raise SystemExit(f"MT3 returned no events for {track}")

    beat_grid = BeatGrid.model_validate(estimate_beat_grid(audio_path))
    timeline = decode_events_to_chord_timeline(stream, beat_grid)
    if not timeline.events:
        raise SystemExit(f"MT3 decoded no chord events for {track}")

    payload = {
        "track": track,
        "audio_duration_s": float(stream.audio_duration_s),
        "events": [
            {
                "timestamp": float(event.timestamp),
                "chord": str(event.chord),
                "confidence": float(event.confidence),
            }
            for event in timeline.events
        ],
    }
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[ece] {track}: cached {len(payload['events'])} decoded events", flush=True)
    return payload


def _build_samples(
    events: list[dict[str, Any]],
    gt_intervals: list[tuple[float, float, int]],
    audio_duration: float,
) -> list[tuple[float, float, float]]:
    samples: list[tuple[float, float, float]] = []
    for index, event in enumerate(events):
        start = float(event["timestamp"])
        if index + 1 < len(events):
            end = float(events[index + 1]["timestamp"])
        else:
            end = min(audio_duration, start + 1.0) if audio_duration > start else start + 1.0
        if end <= start:
            continue

        gt_index, overlap = majority_gt_index(gt_intervals, start, end)
        if overlap <= 0.0:
            continue

        predicted_index = chord_to_mirex_index(str(event["chord"]))
        confidence = max(0.0, min(1.0, float(event["confidence"])))
        samples.append((confidence, 1.0 if predicted_index == gt_index else 0.0, end - start))
    return samples


def main() -> None:
    args = _parse_args()
    timelines_dir = args.data_dir / "processed" / "timelines"
    tracks = _select_tracks(timelines_dir, args.limit, args.track)
    print(f"[ece] tracks: {', '.join(tracks)}", flush=True)

    confidences: list[float] = []
    correct: list[float] = []
    weights: list[float] = []
    track_summaries: list[dict[str, Any]] = []

    for track in tracks:
        timeline_path = timelines_dir / f"{track}.json"
        if not timeline_path.is_file():
            raise SystemExit(f"Ground-truth timeline not found for {track}: {timeline_path}")

        gt_intervals = _load_ground_truth(timeline_path)
        payload = _load_or_run_mt3(
            track,
            args.data_dir,
            args.cache_dir,
            refresh=args.refresh,
        )
        samples = _build_samples(
            payload["events"],
            gt_intervals,
            float(payload.get("audio_duration_s") or 0.0),
        )
        if not samples:
            raise SystemExit(f"No calibration samples for {track} (events outside GT timeline?)")

        track_conf = [sample[0] for sample in samples]
        track_correct = [sample[1] for sample in samples]
        track_weight = [sample[2] for sample in samples]
        track_duration = sum(track_weight)
        track_accuracy = sum(c * w for c, w in zip(track_correct, track_weight, strict=True)) / track_duration
        track_confidence = sum(c * w for c, w in zip(track_conf, track_weight, strict=True)) / track_duration

        confidences.extend(track_conf)
        correct.extend(track_correct)
        weights.extend(track_weight)
        track_summaries.append(
            {
                "track": track,
                "events": len(samples),
                "duration_s": round(track_duration, 3),
                "accuracy": round(track_accuracy, 4),
                "mean_confidence": round(track_confidence, 4),
            }
        )
        print(
            f"[ece] {track}: {len(samples)} samples, {track_duration:.1f}s, "
            f"accuracy={track_accuracy:.3f}, mean_confidence={track_confidence:.3f}",
            flush=True,
        )

    total_weight = float(sum(weights))
    if total_weight <= 0.0:
        raise SystemExit("Total calibration weight is zero")

    bins = bin_calibration(confidences, correct, weights, num_bins=args.bins)
    ece = expected_calibration_error(bins, total_weight=total_weight)
    overall_accuracy = sum(c * w for c, w in zip(correct, weights, strict=True)) / total_weight
    overall_confidence = sum(c * w for c, w in zip(confidences, weights, strict=True)) / total_weight

    print("\n## Commit 184 — heuristic chord confidence calibration\n")
    print(f"Tracks: {', '.join(tracks)}")
    print(f"Samples: {len(confidences)} predicted events across {total_weight:.1f}s")
    print(f"Overall accuracy: {overall_accuracy:.3f}")
    print(f"Mean confidence: {overall_confidence:.3f}")
    print(f"ECE ({args.bins} bins): {ece:.4f}\n")
    print("| Bin | Events | Duration (s) | Avg confidence | Accuracy | Gap |")
    print("|-----|--------|--------------|----------------|----------|-----|")
    for item in bins:
        print(
            f"| {item.lower:.1f}–{item.upper:.1f} | {item.count} | {item.weight:.2f} | "
            f"{item.avg_confidence:.3f} | {item.accuracy:.3f} | {item.gap:.3f} |"
        )

    payload = {
        "commit": 184,
        "tracks": track_summaries,
        "num_bins": args.bins,
        "samples": len(confidences),
        "total_weight_s": round(total_weight, 3),
        "overall_accuracy": round(overall_accuracy, 4),
        "mean_confidence": round(overall_confidence, 4),
        "ece": round(ece, 4),
        "bins": [
            {**asdict(item), "gap": round(item.gap, 4)}
            for item in bins
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n[ece] wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
