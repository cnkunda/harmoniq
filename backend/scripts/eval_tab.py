"""Commit 1 / W4: MIDI→tablature assignment evaluation.

Compares the per-note ``allCellsForMidi`` heuristic against a
playability-aware sequence DP on string/fret ground truth from GuitarSet
(primary) and EGSet12 (secondary). Inputs are the reference MIDI pitches,
so the run isolates assignment from transcription error.

Usage (from ``backend/``)::

    python scripts/eval_tab.py \
        --source guitarset,egset12 --split test \
        --augment-capo --augment-tuning \
        --report ../docs/audit/amt/w4_tab_eval.json

Metrics follow the Fretting-Transformer (arXiv:2506.14223): pitch
accuracy, tab accuracy, and mean playability difficulty.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.evaluation.manifest import (  # noqa: E402
    EvalManifest,
    ManifestError,
    TrackSpec,
    load_manifest,
    resolve_manifest_path,
)
from app.evaluation.tab_ground_truth import (  # noqa: E402
    TabGroundTruthError,
    load_tab_ground_truth,
)
from app.fretting.assign import assign_tab  # noqa: E402
from app.fretting.metrics import aggregate_metrics, evaluate_assignment  # noqa: E402
from app.fretting.techniques import label_techniques  # noqa: E402
from app.fretting.tuning import (  # noqa: E402
    MAX_FRET,
    Tuning,
    get_tuning,
    standard,
)
from app.fretting.types import TabNote  # noqa: E402

logger = logging.getLogger("harmoniq.eval.tab")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

DELTA_EPSILON = 1e-9

_TAB_GT_FORMATS = ("guitarset_jams", "egset12_jams", "guitar_techs_midi")
_TUNING_VARIANTS = ("half_step_down", "full_step_down", "drop_d")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=_REPO_ROOT / "docs" / "eval" / "amt_manifest.json",
    )
    parser.add_argument(
        "--source",
        default="guitarset,egset12",
        help="Comma-separated manifest source names",
    )
    parser.add_argument("--split", choices=("train", "val", "test"), default=None)
    parser.add_argument("--limit", type=int, default=None, help="Max tracks")
    parser.add_argument(
        "--track", action="append", default=[], help="Track id (repeatable)"
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=_REPO_ROOT / "docs" / "audit" / "amt" / "w4_tab_eval.json",
    )
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument(
        "--tuning", default="standard", help="Base tuning name"
    )
    parser.add_argument(
        "--capo", type=int, default=0, help="Base capo for the standard variant"
    )
    parser.add_argument(
        "--augment-capo",
        action="store_true",
        help="Evaluate capo 0-7 as transposed variants",
    )
    parser.add_argument(
        "--augment-tuning",
        action="store_true",
        help="Evaluate half/full-step-down and drop-D variants",
    )
    parser.add_argument("--max-fret", type=int, default=MAX_FRET)
    parser.add_argument("--alpha", type=float, default=0.25)
    parser.add_argument("--max-span", type=int, default=5)
    parser.add_argument("--group-tolerance-ms", type=float, default=30.0)
    parser.add_argument("--max-group-candidates", type=int, default=256)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Override the manifest data_root",
    )
    return parser.parse_args(argv)


def _select_tracks(
    manifest: EvalManifest, args: argparse.Namespace
) -> list[TrackSpec]:
    sources = {
        item.strip() for item in args.source.split(",") if item.strip()
    }
    requested = set(args.track)
    selected: list[TrackSpec] = []
    for track in manifest.tracks:
        if track.source not in sources:
            continue
        if track.gt_format not in _TAB_GT_FORMATS:
            continue
        if args.split is not None and track.split != args.split:
            continue
        if requested and track.id not in requested:
            continue
        selected.append(track)
    return selected


def _resolve_gt_path(
    manifest: EvalManifest,
    track: TrackSpec,
    args: argparse.Namespace,
) -> Path:
    if not track.gt_path:
        raise TabGroundTruthError(f"track {track.id!r} has no gt_path")
    return resolve_manifest_path(
        track.gt_path,
        manifest_path=args.manifest,
        data_root=(
            args.data_root if args.data_root is not None else manifest.data_root
        ),
    )


def _shift_capo(notes: list[TabNote], capo: int) -> list[TabNote]:
    """Simulate a performance at ``capo``: same positions, higher pitches."""
    return [note.with_pitch(note.pitch + capo) for note in notes]


def _retune(notes: list[TabNote], tuning: Tuning) -> list[TabNote]:
    """Simulate a different tuning: same string/fret, retuned pitch."""
    output: list[TabNote] = []
    for note in notes:
        if note.string is None or note.fret is None:
            raise TabGroundTruthError(
                "tuning augmentation requires string/fret ground truth"
            )
        output.append(
            note.with_pitch(tuning.pitch_for(note.string, note.fret))
        )
    return output


def _build_variants(
    reference: list[TabNote],
    args: argparse.Namespace,
) -> list[tuple[str, str, Tuning, list[TabNote]]]:
    """Return ``(name, description, tuning, notes)`` variants."""
    base_tuning = get_tuning(args.tuning, capo=args.capo)
    base_notes = (
        _retune(reference, base_tuning)
        if args.tuning != "standard"
        else _shift_capo(reference, args.capo)
    )
    variants: list[tuple[str, str, Tuning, list[TabNote]]] = [
        (
            "base",
            f"{args.tuning} tuning, capo {args.capo}",
            base_tuning,
            base_notes,
        )
    ]

    if args.augment_capo:
        for capo in range(8):
            if args.tuning == "standard" and capo == args.capo:
                continue
            tuning = get_tuning(args.tuning, capo=capo)
            variants.append(
                (
                    f"capo_{capo}",
                    f"{args.tuning} tuning, augmented capo {capo}",
                    tuning,
                    _retune(reference, tuning),
                )
            )

    if args.augment_tuning:
        for name in _TUNING_VARIANTS:
            tuning = get_tuning(name, capo=0)
            variants.append(
                (
                    f"tuning_{name}",
                    f"augmented {name} tuning",
                    tuning,
                    _retune(reference, tuning),
                )
            )
    return variants


def _score(
    reference: list[TabNote],
    mode: str,
    tuning: Tuning,
    args: argparse.Namespace,
) -> dict[str, object]:
    assignment = assign_tab(
        reference,
        tuning=tuning,
        mode=mode,
        max_fret=args.max_fret,
        alpha=args.alpha,
        max_span=args.max_span,
        group_tolerance_s=args.group_tolerance_ms / 1000.0,
        max_group_candidates=args.max_group_candidates,
    )
    return evaluate_assignment(reference, assignment, alpha=args.alpha)


def _gate(base_modes: dict[str, dict[str, object]]) -> dict[str, Any]:
    baseline = base_modes["baseline"]
    dp = base_modes["dp"]

    def _delta(key: str) -> float:
        left = baseline.get(key)
        right = dp.get(key)
        if left is None or right is None:
            return 0.0
        return round(float(right) - float(left), 6)

    tab_delta = _delta("tab_accuracy")
    pitch_delta = _delta("pitch_accuracy")
    baseline_difficulty = baseline.get("difficulty")
    dp_difficulty = dp.get("difficulty")
    difficulty_improvement = (
        round(float(baseline_difficulty) - float(dp_difficulty), 6)
        if baseline_difficulty is not None and dp_difficulty is not None
        else 0.0
    )
    validity_delta = _delta("group_validity")
    checks = {
        "tab_accuracy": tab_delta > DELTA_EPSILON,
        "pitch_accuracy": pitch_delta > DELTA_EPSILON,
        "playability": difficulty_improvement > DELTA_EPSILON,
        "group_validity": validity_delta > DELTA_EPSILON,
    }
    # G4 names pitch, tab, and playability only; group validity is reported
    # as a physical-soundness diagnostic, not a gate criterion.
    g4_checks = ("pitch_accuracy", "tab_accuracy", "playability")
    return {
        "baseline_tab_accuracy": baseline.get("tab_accuracy"),
        "dp_tab_accuracy": dp.get("tab_accuracy"),
        "tab_accuracy_delta": tab_delta,
        "baseline_pitch_accuracy": baseline.get("pitch_accuracy"),
        "dp_pitch_accuracy": dp.get("pitch_accuracy"),
        "pitch_accuracy_delta": pitch_delta,
        "baseline_difficulty": baseline_difficulty,
        "dp_difficulty": dp_difficulty,
        "difficulty_improvement": difficulty_improvement,
        "baseline_group_validity": baseline.get("group_validity"),
        "dp_group_validity": dp.get("group_validity"),
        "group_validity_delta": validity_delta,
        "checks": checks,
        "passed": any(checks[name] for name in g4_checks),
    }


def _technique_counts(
    notes_by_track: dict[str, list[TabNote]],
    args: argparse.Namespace,
) -> dict[str, int]:
    totals: dict[str, int] = {}
    for track_id in sorted(notes_by_track):
        reference = notes_by_track[track_id]
        assignment = assign_tab(
            reference,
            tuning=standard(),
            mode="dp",
            max_fret=args.max_fret,
            alpha=args.alpha,
            max_span=args.max_span,
            group_tolerance_s=args.group_tolerance_ms / 1000.0,
            max_group_candidates=args.max_group_candidates,
        )
        labels = label_techniques(reference, assignment=assignment.notes)
        for tag, count in labels.counts.items():
            totals[tag] = totals.get(tag, 0) + int(count)
    return dict(sorted(totals.items()))


def _render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# W4 tablature assignment — {report['manifest_id']}")
    lines.append("")
    lines.append(
        "Evaluation: symbolic MIDI→tab assignment on reference pitches. "
        "Tuning/capo variants are augmented, not recorded audio."
    )
    lines.append("")
    lines.append(f"Tracks: {report['summary']['tracks']}")
    lines.append(
        f"Notes: {report['summary']['notes']} · "
        f"Skipped: {report['summary']['skipped']}"
    )
    lines.append("")
    lines.append("## Gate (base variant)")
    lines.append("")
    gate = report["gate"]
    lines.append("| Metric | allCellsForMidi | DP | Delta |")
    lines.append("| --- | ---: | ---: | ---: |")
    lines.append(
        f"| Pitch accuracy | {gate['baseline_pitch_accuracy']} | "
        f"{gate['dp_pitch_accuracy']} | {gate['pitch_accuracy_delta']} |"
    )
    lines.append(
        f"| Tab accuracy | {gate['baseline_tab_accuracy']} | "
        f"{gate['dp_tab_accuracy']} | {gate['tab_accuracy_delta']} |"
    )
    difficulty_delta = -float(gate["difficulty_improvement"])
    lines.append(
        f"| Difficulty (lower is better) | {gate['baseline_difficulty']} | "
        f"{gate['dp_difficulty']} | {difficulty_delta:+} |"
    )
    lines.append(
        f"| Group validity | {gate['baseline_group_validity']} | "
        f"{gate['dp_group_validity']} | {gate['group_validity_delta']} |"
    )
    lines.append("")
    passed_on = [
        name for name in ("pitch_accuracy", "tab_accuracy", "playability")
        if gate["checks"].get(name)
    ]
    lines.append(
        f"**Gate: {'PASS' if gate['passed'] else 'FAIL'}"
        + (f" (passed on {', '.join(passed_on)})" if passed_on else "")
        + "**"
    )
    lines.append("")
    lines.append("## Variants")
    lines.append("")
    lines.append(
        "| Variant | Mode | Tracks | Notes | Pitch acc | Tab acc | "
        "Difficulty | Group validity |"
    )
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for name in sorted(report["variants"]):
        variant = report["variants"][name]
        for mode in ("baseline", "dp"):
            metrics = variant["modes"][mode]
            lines.append(
                f"| {name} | {mode} | {metrics.get('tracks')} | "
                f"{metrics.get('notes')} | {metrics.get('pitch_accuracy')} | "
                f"{metrics.get('tab_accuracy')} | "
                f"{metrics.get('difficulty')} | "
                f"{metrics.get('group_validity')} |"
            )
    lines.append("")
    lines.append("## Per-track (base variant)")
    lines.append("")
    lines.append(
        "| Track | Source | Split | Notes | Base tab | DP tab | "
        "Base diff | DP diff |"
    )
    lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for track in report["tracks"]:
        lines.append(
            f"| {track['id']} | {track['source']} | {track['split']} | "
            f"{track['notes']} | {track['baseline']['tab_accuracy']} | "
            f"{track['dp']['tab_accuracy']} | "
            f"{track['baseline']['difficulty']} | {track['dp']['difficulty']} |"
        )
    lines.append("")
    lines.append("## Techniques (prototype)")
    lines.append("")
    if report["techniques"]:
        lines.append(
            "Heuristic labels, not scored: "
            + ", ".join(
                f"{tag}={count}" for tag, count in report["techniques"].items()
            )
        )
    else:
        lines.append("No technique candidates found.")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    for note in report["notes"]:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        logger.error("cannot load manifest: %s", exc)
        return 2

    tracks = _select_tracks(manifest, args)
    if args.limit is not None:
        tracks = tracks[: args.limit]
    if not tracks:
        logger.error(
            "no string-annotated tracks selected for sources=%s split=%s",
            args.source,
            args.split,
        )
        return 2

    logger.info(
        "evaluating %d track(s) from %s", len(tracks), args.source
    )

    variants: dict[str, dict[str, Any]] = {}
    base_track_rows: list[dict[str, Any]] = []
    technique_notes: dict[str, list[TabNote]] = {}
    skipped: list[dict[str, str]] = []
    total_notes = 0

    for track in tracks:
        try:
            gt_path = _resolve_gt_path(manifest, track, args)
            reference = load_tab_ground_truth(
                gt_path, gt_format=track.gt_format
            )
        except (TabGroundTruthError, ManifestError) as exc:
            logger.warning("[%s] skipped: %s", track.id, exc)
            skipped.append({"id": track.id, "reason": str(exc)})
            continue

        total_notes += len(reference)
        technique_notes[track.id] = reference
        track_variants = _build_variants(reference, args)
        base_row: dict[str, Any] | None = None
        for name, description, tuning, variant_notes in track_variants:
            variant = variants.setdefault(
                name,
                {
                    "description": description,
                    "tuning": tuning.name,
                    "capo": tuning.capo,
                    "modes": {"baseline": [], "dp": []},
                },
            )
            for mode in ("baseline", "dp"):
                metrics = _score(variant_notes, mode, tuning, args)
                variant["modes"][mode].append(metrics)
                if name == "base":
                    if base_row is None:
                        base_row = {
                            "id": track.id,
                            "source": track.source,
                            "split": track.split,
                            "notes": len(reference),
                        }
                    base_row[mode] = metrics
        if base_row is not None:
            base_track_rows.append(base_row)
        logger.info(
            "[%s] %d notes, base tab baseline=%.4f dp=%.4f",
            track.id,
            len(reference),
            base_row["baseline"]["tab_accuracy"],  # type: ignore[index]
            base_row["dp"]["tab_accuracy"],  # type: ignore[index]
        )

    if not variants:
        logger.error("no tracks could be evaluated")
        return 2

    variant_report: dict[str, Any] = {}
    for name in sorted(variants):
        variant = variants[name]
        variant_report[name] = {
            "description": variant["description"],
            "tuning": variant["tuning"],
            "capo": variant["capo"],
            "modes": {
                mode: aggregate_metrics(variant["modes"][mode])
                for mode in ("baseline", "dp")
            },
        }

    base_modes = variant_report["base"]["modes"]
    report = {
        "schema_version": 1,
        "manifest_id": manifest.manifest_id,
        "evaluation": (
            "symbolic MIDI-to-tab string/fret assignment on reference pitches"
        ),
        "config": {
            "sources": sorted(
                {item.strip() for item in args.source.split(",") if item.strip()}
            ),
            "split": args.split,
            "tuning": args.tuning,
            "capo": args.capo,
            "augment_capo": args.augment_capo,
            "augment_tuning": args.augment_tuning,
            "max_fret": args.max_fret,
            "alpha": args.alpha,
            "max_span": args.max_span,
            "group_tolerance_ms": args.group_tolerance_ms,
            "max_group_candidates": args.max_group_candidates,
        },
        "summary": {
            "tracks": len(base_track_rows),
            "notes": total_notes,
            "skipped": len(skipped),
        },
        "gate": _gate(base_modes),
        "variants": variant_report,
        "techniques": _technique_counts(technique_notes, args),
        "tracks": base_track_rows,
        "skipped": skipped,
        "notes": [
            "DadaGP was not staged (research access on request); the gate uses "
            "GuitarSet (primary) and EGSet12 (secondary).",
            "Tuning/capo variants are augmented by transposing the reference "
            "performance; they are not recorded tuning/capo performances.",
            "The DP receives reference pitches, so pitch accuracy is 1.0 for "
            "every assignable note; unassignable notes are counted as misses.",
            "The DP minimises playability cost subject to distinct strings for "
            "simultaneous notes. The per-note baseline can report a lower "
            "difficulty only by placing colliding notes on the same string; "
            "group validity shows that difference directly.",
            "Tab accuracy and group validity are the primary gains here; "
            "playability may trade off against physical validity.",
            "Technique labels are a heuristic prototype and are not scored.",
            "The audio string-activity auxiliary head is deferred; target "
            "construction is implemented in app.fretting.string_activity.",
        ],
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_path = args.markdown or args.report.with_suffix(".md")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    logger.info("wrote %s and %s", args.report, markdown_path)

    gate = report["gate"]
    logger.info(
        "gate=%s tab_delta=%s difficulty_improvement=%s validity_delta=%s",
        "PASS" if gate["passed"] else "FAIL",
        gate["tab_accuracy_delta"],
        gate["difficulty_improvement"],
        gate["group_validity_delta"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
