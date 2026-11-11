"""Merge W1 pseudo-label shard reports into one G1 report.

Usage (from ``backend/``)::

    python scripts/merge_w1_reports.py \
        --report /tmp/w1_main_0_500.json \
        --report /tmp/w1_shard_500.json \
        --report /tmp/w1_shard_750.json \
        --out ../docs/audit/amt/w1_pseudo_label_full.json

Tracks are deduplicated by id. A record that actually ran is preferred over
an ``existing`` (skip-existing) record, and the larger window count wins.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

_DEFAULT_OUT = _REPO_ROOT / "docs" / "audit" / "amt" / "w1_pseudo_label_full.json"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "tracks" not in payload:
        raise ValueError(f"report has no tracks: {path}")
    return payload


def _prefer(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_ran = left.get("reason") != "existing"
    right_ran = right.get("reason") != "existing"
    if left_ran != right_ran:
        return left if left_ran else right
    return left if int(left.get("windows_kept", 0)) >= int(right.get("windows_kept", 0)) else right


def merge_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge report payloads, deduplicating tracks by id."""
    if not reports:
        raise ValueError("no reports to merge")

    tracks: dict[str, dict[str, Any]] = {}
    for report in reports:
        for record in report.get("tracks", []):
            track_id = str(record["id"])
            existing = tracks.get(track_id)
            tracks[track_id] = record if existing is None else _prefer(existing, record)

    merged_tracks = [tracks[key] for key in sorted(tracks)]
    totals = {
        "selected": len(merged_tracks),
        "labeled": sum(1 for record in merged_tracks if record["status"] == "labeled"),
        "skipped": sum(1 for record in merged_tracks if record["status"] == "skipped"),
        "windows_total": sum(int(record.get("windows_total", 0)) for record in merged_tracks),
        "windows_kept": sum(int(record.get("windows_kept", 0)) for record in merged_tracks),
    }
    totals["retention"] = round(
        totals["windows_kept"] / max(totals["windows_total"], 1), 6
    )

    sources: dict[str, dict[str, Any]] = {}
    for record in merged_tracks:
        source = str(record["source"])
        bucket = sources.setdefault(
            source,
            {"selected": 0, "labeled": 0, "skipped": 0, "windows_kept": 0},
        )
        bucket["selected"] += 1
        bucket[record["status"]] += 1
        bucket["windows_kept"] += int(record.get("windows_kept", 0))

    first = reports[0]
    return {
        "schema_version": 1,
        "manifest_id": first.get("manifest_id"),
        "teacher": first.get("teacher"),
        "config": first.get("config", {}),
        "progress": {
            "processed": len(merged_tracks),
            "selected": len(merged_tracks),
            "partial": False,
            "merged_reports": len(reports),
        },
        "totals": totals,
        "sources": dict(sorted(sources.items())),
        "tracks": merged_tracks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    args = parser.parse_args(argv)

    reports = [_load(path) for path in args.report]
    merged = merge_reports(reports)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    totals = merged["totals"]
    print(
        f"[DONE] merged {len(reports)} report(s): "
        f"selected={totals['selected']} labeled={totals['labeled']} "
        f"windows_kept={totals['windows_kept']} out={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
