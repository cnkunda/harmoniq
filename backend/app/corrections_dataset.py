"""Export in-app corrections into a training/evaluation dataset.

Corrections are written by the PATCH endpoints to ``<DATA_DIR>/jobs/<job_id>/corrections.json``.
This module turns them into deterministic JSONL rows (original -> corrected) that W3/W4
can consume without touching the practice database.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

CORRECTION_DATASET_SCHEMA_VERSION = 1


def correction_history_path(job_dir: Path) -> Path:
    """Location of a job's correction history file."""
    return job_dir / "corrections.json"


def iter_correction_records(data_dir: Path) -> Iterator[dict[str, Any]]:
    """Yield every correction record found under ``<data_dir>/jobs/*``.

    Records are yielded in stable ``(job_id, applied_at, index)`` order so exports
    are reproducible. Raises ``ValueError`` on malformed JSON (fail loudly).
    """
    jobs_dir = data_dir / "jobs"
    if not jobs_dir.is_dir():
        return
    job_dirs = sorted(p for p in jobs_dir.iterdir() if p.is_dir())
    for job_dir in job_dirs:
        history_path = correction_history_path(job_dir)
        if not history_path.is_file():
            continue
        try:
            raw = json.loads(history_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed correction history: {history_path}") from exc
        if not isinstance(raw, list):
            raise ValueError(f"Correction history must be a list: {history_path}")
        for record in sorted(
            (r for r in raw if isinstance(r, dict)),
            key=lambda r: (str(r.get("applied_at") or ""), int(r.get("index") or 0)),
        ):
            yield {"job_id": job_dir.name, **record}


def build_correction_rows(data_dir: Path) -> list[dict[str, Any]]:
    """Build the dataset rows (adds the schema version to every row)."""
    rows: list[dict[str, Any]] = []
    for record in iter_correction_records(data_dir):
        rows.append(
            {
                "schema_version": CORRECTION_DATASET_SCHEMA_VERSION,
                "job_id": record.get("job_id"),
                "correction_type": record.get("correction_type"),
                "index": record.get("index"),
                "original_value": record.get("original_value"),
                "corrected_value": record.get("corrected_value"),
                "reason": record.get("reason"),
                "applied_at": record.get("applied_at"),
            }
        )
    return rows


def write_correction_dataset(rows: list[dict[str, Any]], out_path: Path) -> int:
    """Write rows as JSONL and return the number written."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fh.write("\n")
    return len(rows)
