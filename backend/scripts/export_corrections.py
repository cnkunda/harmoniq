"""Export in-app corrections to a JSONL dataset for W3/W4 training and evaluation.

Usage (from backend/):
    python scripts/export_corrections.py
    python scripts/export_corrections.py --data-dir ./data --out ./data/corrections/corrections.jsonl
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from app.corrections_dataset import build_correction_rows, write_correction_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Harmoniq corrections to JSONL")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.getenv("DATA_DIR", "./data")),
        help="Runtime data directory containing jobs/<job_id>/corrections.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("./data/corrections/corrections.jsonl"),
        help="Output JSONL path",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print counts without writing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = build_correction_rows(args.data_dir)
    if args.dry_run:
        print(f"{len(rows)} correction rows found under {args.data_dir}")
        return 0
    written = write_correction_dataset(rows, args.out)
    print(f"Wrote {written} correction rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
