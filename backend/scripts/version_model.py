#!/usr/bin/env python3
"""Version and package trained H-GAIN model artifacts with extracted metadata.

Usage:
    python scripts/version_model.py \
        --version 1.0.1 \
        --weights app/chord_model.weights.h5 \
        --log scripts/training_log.csv

    python scripts/version_model.py \
        --version 1.0.1 \
        --weights app/chord_model.weights.h5 \
        --log scripts/training_log.csv \
        --scripts chord_inference.py chord_vocab.py
"""

import argparse
import csv
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


LOG_HEADER_LEGACY = "epoch,accuracy,learning_rate,loss,val_accuracy,val_loss"

# Multi-task training log columns (Commit 103+)
LOG_HEADER_MULTITASK = [
    "chord_probs_accuracy", "chord_probs_loss", "cqt_emd", "domain_gap",
    "loss", "presence_loss", "presence_presence_acc", "root_probs_loss",
    "root_probs_root_accuracy", "val_accuracy_real", "val_accuracy_synthetic",
    "val_chord_probs_accuracy", "val_chord_probs_loss", "val_loss",
    "val_presence_loss", "val_presence_presence_acc", "val_root_probs_loss",
    "val_root_probs_root_accuracy",
]

DEFAULT_PIPELINE_SCRIPTS = [
    "chord_inference.py",
    "chord_vocab.py",
    "viterbi_decoder.py",
    "chord_transitions.py",
    "chord_metrics.py",
    "solo_harmony_analyzer.py",
]

COMPANION_ARTIFACTS = [
    "chord_model.keras",
    "chord_model_best.keras",
    "chord_model.tflite",
    "chord_model_qat.keras",
]

BACKEND_DIR = Path(__file__).resolve().parent.parent
RESEARCH_DIR = BACKEND_DIR / "research"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Version and package a trained H-GAIN model."
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Version string, e.g. 1.0.1",
    )
    parser.add_argument(
        "--weights",
        required=True,
        type=Path,
        help="Path to the trained .weights.h5 file",
    )
    parser.add_argument(
        "--log",
        required=True,
        type=Path,
        help="Path to the CSV training log",
    )
    parser.add_argument(
        "--scripts",
        nargs="*",
        default=None,
        help="Pipeline .py files to copy (default: auto-discover known scripts)",
    )
    args = parser.parse_args(argv)

    args.weights = args.weights.resolve()
    args.log = args.log.resolve()

    if not args.weights.is_file():
        parser.error(f"weights file not found: {args.weights}")
    if not args.log.is_file():
        parser.error(f"log file not found: {args.log}")

    return args


def parse_training_log(log_path: Path) -> dict:
    with log_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if not rows:
        raise ValueError(f"CSV file is empty (header only): {log_path}")

    first = rows[0]
    last = rows[-1]

    # Legacy 6-column format (v1.0.1–v1.0.4)
    if fieldnames == [
        "epoch", "accuracy", "learning_rate", "loss", "val_accuracy", "val_loss",
    ]:
        return {
            "total_epochs": len(rows),
            "initial_lr": float(first["learning_rate"]),
            "final_val_acc": float(last["val_accuracy"]),
            "final_val_loss": float(last["val_loss"]),
            "format": "legacy",
        }

    # Multi-task 18-column format (v1.0.5+)
    if "val_accuracy_real" in fieldnames and "chord_probs_accuracy" in fieldnames:
        return {
            "total_epochs": len(rows),
            "initial_lr": None,  # Not in multi-task CSV
            "final_val_acc": float(last.get("val_chord_probs_accuracy", 0)),
            "final_val_loss": float(last.get("val_loss", 0)),
            "final_val_accuracy_real": float(last.get("val_accuracy_real", 0)),
            "final_val_accuracy_synthetic": float(last.get("val_accuracy_synthetic", 0)),
            "final_domain_gap": float(last.get("domain_gap", 0)),
            "final_chord_probs_accuracy": float(last.get("chord_probs_accuracy", 0)),
            "format": "multitask",
        }

    raise ValueError(
        f"Unrecognized CSV header in {log_path}\n"
        f"  columns: {fieldnames}"
    )


def discover_artifacts(weights_path: Path) -> list[Path]:
    artifacts = [weights_path]
    parent = weights_path.parent

    for name in COMPANION_ARTIFACTS:
        candidate = parent / name
        if candidate.is_file():
            artifacts.append(candidate)
            print(f"  [DISCOVERED] {candidate}")
        else:
            print(f"  [SKIPPED]    {name} (not found)")

    return artifacts


def ensure_output_dir(version: str) -> Path:
    dest = RESEARCH_DIR / f"h-gain-v{version}"

    if dest.exists():
        answer = input(
            f"Directory {dest} already exists. Overwrite? [y/N] "
        ).strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(1)
        shutil.rmtree(dest)
        print(f"  [REMOVED]  {dest}")

    dest.mkdir(parents=True, exist_ok=True)
    print(f"  [CREATED]  {dest}")
    return dest


def copy_files(files: list[Path], dest: Path) -> None:
    for src in files:
        shutil.copy2(src, dest / src.name)
        print(f"  [COPIED]   {src.name}")


def copy_pipeline_scripts(
    weights_dir: Path,
    dest: Path,
    explicit_scripts: list[str] | None,
) -> None:
    script_names = explicit_scripts if explicit_scripts is not None else DEFAULT_PIPELINE_SCRIPTS

    for name in script_names:
        src = weights_dir / name
        if src.is_file():
            shutil.copy2(src, dest / name)
            print(f"  [COPIED]   {name}")
        else:
            print(f"  [SKIPPED]  {name} (not found)")


def generate_metadata(version: str, log_data: dict, dest: Path) -> None:
    metrics = {
        "val_accuracy": log_data["final_val_acc"],
        "val_loss": log_data["final_val_loss"],
    }
    if log_data.get("format") == "multitask":
        metrics.update({
            "val_accuracy_real": log_data.get("final_val_accuracy_real"),
            "val_accuracy_synthetic": log_data.get("final_val_accuracy_synthetic"),
            "domain_gap": log_data.get("final_domain_gap"),
            "chord_probs_accuracy": log_data.get("final_chord_probs_accuracy"),
        })

    metadata = {
        "model_name": "H-GAIN",
        "version": version,
        "architecture": "CRNN",
        "pipeline": {
            "demucs_version": "4.0",
            "librosa_version": "0.10.0",
        },
        "hyperparameters": {
            "epochs": log_data["total_epochs"],
            "initial_lr": log_data.get("initial_lr"),
        },
        "metrics": metrics,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    meta_path = dest / "metadata.json"
    with meta_path.open("w") as f:
        json.dump(metadata, f, indent=2)
    print(f"  [GENERATED] metadata.json")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    print(f"\nH-GAIN Model Versioning")
    print(f"{'=' * 50}")

    # Parse training log
    print(f"\n[1/5] Parsing training log ...")
    try:
        log_data = parse_training_log(args.log)
    except (ValueError, csv.Error) as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return 1
    print(f"  [OK]       {args.log.name} — {log_data['total_epochs']} epochs, "
          f"val_acc={log_data['final_val_acc']:.4f}, "
          f"val_loss={log_data['final_val_loss']:.4f}")
    if log_data.get("format") == "multitask":
        print(f"             real={log_data.get('final_val_accuracy_real', 0):.4f}, "
              f"synth={log_data.get('final_val_accuracy_synthetic', 0):.4f}, "
              f"domain_gap={log_data.get('final_domain_gap', 0):.4f}")

    # Discover companion artifacts
    print(f"\n[2/5] Discovering model artifacts ...")
    artifacts = discover_artifacts(args.weights)
    print(f"  [FOUND]    {len(artifacts)} artifact(s) to copy")

    # Create output directory
    print(f"\n[3/5] Creating version directory ...")
    dest = ensure_output_dir(args.version)

    # Copy model artifacts + log
    print(f"\n[4/5] Copying files ...")
    copy_files(artifacts, dest)
    copy_files([args.log], dest)

    weights_dir = args.weights.parent
    copy_pipeline_scripts(weights_dir, dest, args.scripts)

    # Generate metadata
    print(f"\n[5/5] Generating metadata ...")
    generate_metadata(args.version, log_data, dest)

    print(f"\n{'=' * 50}")
    print(f"DONE — Version {args.version} packaged at {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
