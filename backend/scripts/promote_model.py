#!/usr/bin/env python3
"""Model promotion gatekeeper — only promotes a version if it improves metrics.

Usage:
    python scripts/promote_model.py --version 1.0.5
    python scripts/promote_model.py --version 1.0.5 --force  # skip metric check
    python scripts/promote_model.py --version 1.0.5 --metric val_accuracy_real
    python scripts/promote_model.py --list  # show all versions and active status
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"
RESEARCH_DIR = BACKEND_DIR / "research"
REGISTRY_PATH = APP_DIR / "model_registry.json"

MODEL_FILES = [
    "chord_model.weights.h5",
    "chord_model.keras",
    "chord_model_best.keras",
    "chord_model.tflite",
    "chord_model_qat.keras",
]

DEFAULT_METRIC = "val_accuracy"
HIGHER_IS_BETTER = True


def load_registry() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {
        "active_version": None,
        "versions": {},
        "promotion_metric": DEFAULT_METRIC,
        "promotion_direction": "higher_is_better",
    }


def save_registry(registry: dict) -> None:
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2) + "\n")


def load_version_metadata(version_dir: Path) -> dict | None:
    meta_path = version_dir / "metadata.json"
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text())


def compare_metrics(
    candidate: dict,
    current: dict,
    metric: str,
    higher_is_better: bool = True,
) -> tuple[bool, str]:
    """Compare candidate against current on the given metric.

    Returns (is_better, reason_string).
    """
    candidate_metrics = candidate.get("metrics", {})
    current_metrics = current.get("metrics", {})

    candidate_val = candidate_metrics.get(metric)
    current_val = current_metrics.get(metric)

    if candidate_val is None:
        return False, f"Candidate missing metric '{metric}'"
    if current_val is None:
        return True, f"Current version missing metric '{metric}' — auto-promote"

    diff = candidate_val - current_val
    pct = (diff / abs(current_val) * 100) if current_val != 0 else float("inf")

    if higher_is_better:
        is_better = diff > 0
    else:
        is_better = diff < 0

    direction = "higher" if higher_is_better else "lower"
    status = "BETTER" if is_better else "WORSE"
    return is_better, (
        f"{metric}: {candidate_val:.4f} vs {current_val:.4f} "
        f"(diff={diff:+.4f}, {pct:+.1f}%) — {status}"
    )


def list_versions() -> None:
    registry = load_registry()
    active = registry.get("active_version")
    versions = registry.get("versions", {})

    print(f"\nModel Registry — Active: v{active or 'none'}")
    print(f"{'=' * 60}")
    print(f"{'Version':<10} {'val_acc':>8} {'val_loss':>9} {'Architecture':<15} {'Status'}")
    print(f"{'-' * 60}")

    for ver, info in sorted(versions.items()):
        marker = " <-- ACTIVE" if ver == active else ""
        arch = info.get("architecture", "unknown")
        va = info.get("val_accuracy")
        vl = info.get("val_loss")
        va_str = f"{va:.4f}" if va is not None else "N/A"
        vl_str = f"{vl:.4f}" if vl is not None else "N/A"
        print(f"v{ver:<9} {va_str:>8} {vl_str:>9} {arch:<15}{marker}")

    print()


def promote(version: str, metric: str, force: bool = False) -> int:
    registry = load_registry()
    versions = registry.get("versions", {})
    active_version = registry.get("active_version")

    # Find candidate version directory
    candidate_dir = RESEARCH_DIR / f"h-gain-v{version}"
    if not candidate_dir.exists():
        print(f"ERROR: Version directory not found: {candidate_dir}")
        return 1

    # Load candidate metadata
    candidate_meta = load_version_metadata(candidate_dir)
    if candidate_meta is None:
        print(f"ERROR: No metadata.json in {candidate_dir}")
        return 1

    # Load current active version metadata
    current_meta = None
    if active_version:
        current_dir = RESEARCH_DIR / f"h-gain-v{active_version}"
        current_meta = load_version_metadata(current_dir)

    print(f"\nModel Promotion Check")
    print(f"{'=' * 60}")
    print(f"  Candidate:  v{version}")
    print(f"  Active:     v{active_version or 'none'}")
    print(f"  Metric:     {metric}")
    print()

    # Compare architectures
    candidate_arch = candidate_meta.get("architecture", "unknown")
    current_arch = current_meta.get("architecture", "unknown") if current_meta else "none"
    if candidate_arch != current_arch:
        print(f"  WARNING: Architecture mismatch — {current_arch} -> {candidate_arch}")
        if not force:
            print(f"  Use --force to promote across architectures")
            print(f"\n  RESULT: REJECTED (architecture mismatch)")
            return 1
        print(f"  --force specified, proceeding with cross-architecture promotion")
        print()

    # Compare metrics
    if current_meta and not force:
        is_better, reason = compare_metrics(
            candidate_meta, current_meta, metric, HIGHER_IS_BETTER
        )
        print(f"  {reason}")
        print()

        if not is_better:
            print(f"  RESULT: REJECTED — candidate is not better on {metric}")
            print(f"  Active model v{active_version} retained.")
            return 1
    else:
        print(f"  No active version or --force: skipping metric comparison")
        print()

    # Promote: copy model files to app/
    print(f"  Promoting v{version} -> app/ ...")
    for fname in MODEL_FILES:
        src = candidate_dir / fname
        dst = APP_DIR / fname
        if src.exists():
            shutil.copy2(str(src), str(dst))
            print(f"    [COPIED] {fname}")
        else:
            print(f"    [SKIPPED] {fname} (not in version archive)")

    # Update registry
    registry["active_version"] = version
    versions[version] = {
        "val_accuracy": candidate_meta.get("metrics", {}).get("val_accuracy"),
        "val_loss": candidate_meta.get("metrics", {}).get("val_loss"),
        "val_accuracy_real": candidate_meta.get("metrics", {}).get("val_accuracy_real"),
        "val_accuracy_synthetic": candidate_meta.get("metrics", {}).get("val_accuracy_synthetic"),
        "domain_gap": candidate_meta.get("metrics", {}).get("domain_gap"),
        "architecture": candidate_arch,
        "promoted_at": candidate_meta.get("timestamp"),
    }
    save_registry(registry)

    print(f"\n  RESULT: PROMOTED v{version} -> active")
    print(f"  Model files updated in app/")
    print(f"  Registry updated at {REGISTRY_PATH}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Model promotion gatekeeper")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--version", help="Version to promote (e.g. 1.0.5)")
    group.add_argument("--list", action="store_true", help="List all versions")
    parser.add_argument(
        "--metric", default=DEFAULT_METRIC,
        help=f"Metric to compare (default: {DEFAULT_METRIC})",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Skip metric comparison (for cross-architecture promotion)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list:
        list_versions()
        return 0
    return promote(args.version, args.metric, args.force)


if __name__ == "__main__":
    sys.exit(main())
