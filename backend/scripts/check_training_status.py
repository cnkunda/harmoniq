#!/usr/bin/env python3
"""Check training pipeline status — data readiness, model artifacts, tmux state.

Usage:
    python scripts/check_training_status.py

Exits with code 0 if pipeline is complete and training is running/idle.
Exits with code 1 if something is missing or training failed.
"""

import sys
import json
import subprocess
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
APP_DIR = Path(__file__).resolve().parent.parent / "app"

PASS = "✓"
FAIL = "✗"


def check(condition: bool, label: str, detail: str = "") -> bool:
    icon = PASS if condition else FAIL
    msg = f"  {icon} {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return condition


def main() -> int:
    print("=== Harmoniq Training Pipeline Status ===\n")

    all_pass = True

    # ---- Data Pipeline ----

    print("Data Pipeline:")
    all_pass &= check(
        (DATA_DIR / "annotations" / "isophonics" / "beatles").exists(),
        "Isophonics Beatles annotations",
        f"{len(list((DATA_DIR / 'annotations' / 'isophonics' / 'beatles').glob('*.lab')))} .lab files"
        if (DATA_DIR / "annotations" / "isophonics" / "beatles").exists() else ""
    )
    all_pass &= check(
        (DATA_DIR / "annotations" / "billboard" / "full.lab").exists(),
        "Billboard annotations",
    )
    all_pass &= check(
        (DATA_DIR / "annotations" / "transition_matrix_empirical.npy").exists(),
        "Empirical transition matrix",
    )
    all_pass &= check(
        (DATA_DIR / "annotations" / "chord_distribution.json").exists(),
        "Chord distribution stats",
    )
    all_pass &= check(
        (DATA_DIR / "guitarset" / "raw" / "audio_mono-mix").exists(),
        "GuitarSet audio files",
        f"{len(list((DATA_DIR / 'guitarset' / 'raw' / 'audio_mono-mix').glob('*.wav')))} WAVs"
        if (DATA_DIR / "guitarset" / "raw" / "audio_mono-mix").exists() else ""
    )
    all_pass &= check(
        (DATA_DIR / "guitarset" / "raw" / "annotation").exists(),
        "GuitarSet annotations",
        f"{len(list((DATA_DIR / 'guitarset' / 'raw' / 'annotation').glob('*.jams')))} JAMS"
        if (DATA_DIR / "guitarset" / "raw" / "annotation").exists() else ""
    )
    all_pass &= check(
        (DATA_DIR / "guitarset" / "processed" / "timelines").exists(),
        "GuitarSet parsed timelines",
        f"{len(list((DATA_DIR / 'guitarset' / 'processed' / 'timelines').glob('*.json')))} JSON"
        if (DATA_DIR / "guitarset" / "processed" / "timelines").exists() else ""
    )
    all_pass &= check(
        (DATA_DIR / "guitarset" / "processed" / "cqt").exists(),
        "GuitarSet CQT features",
        f"{len(list((DATA_DIR / 'guitarset' / 'processed' / 'cqt').glob('*.npz')))} .npz"
        if (DATA_DIR / "guitarset" / "processed" / "cqt").exists() else ""
    )

    # ---- Model Artifacts ----

    print("\nModel Artifacts:")
    for fname in ["chord_model.tflite", "chord_model.keras", "chord_model.weights.h5"]:
        exists = (APP_DIR / fname).exists()
        size = (APP_DIR / fname).stat().st_size if exists else 0
        all_pass &= check(
            exists,
            fname,
            f"{size / 1024 / 1024:.1f} MB" if exists else ""
        )

    # ---- Tmux Session ----

    print("\nTraining Process:")
    try:
        result = subprocess.run(
            ["tmux", "list-sessions"],
            capture_output=True, text=True, timeout=5
        )
        sessions = result.stdout.strip()
        if "harmoniq-train" in sessions:
            # Get window info
            win = subprocess.run(
                ["tmux", "list-windows", "-t", "harmoniq-train"],
                capture_output=True, text=True, timeout=5
            )
            print(f"  {PASS} Tmux session 'harmoniq-train' is running")
            print(f"    Windows: {win.stdout.strip()}")
        else:
            print(f"  {FAIL} No 'harmoniq-train' tmux session found")
            all_pass = False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(f"  {FAIL} tmux not available or session check timed out")
        all_pass = False

    # ---- Summary ----

    print()
    if all_pass:
        print("All checks PASSED — training pipeline is ready.")
        return 0
    else:
        print("Some checks FAILED — see details above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
