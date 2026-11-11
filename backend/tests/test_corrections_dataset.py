"""Tests for correction dataset export (T5: corrections become training data)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.corrections_dataset import (
    CORRECTION_DATASET_SCHEMA_VERSION,
    build_correction_rows,
    write_correction_dataset,
)


def _seed_history(data_dir: Path, job_id: str, records: list[dict]) -> Path:
    job_dir = data_dir / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    path = job_dir / "corrections.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


class TestCorrectionDatasetExport:
    def test_exports_rows_with_schema_and_job_id(self, tmp_path: Path) -> None:
        _seed_history(
            tmp_path,
            "job-a",
            [
                {
                    "correction_type": "solo_note",
                    "index": 0,
                    "original_value": {"pitch": 60, "string": None, "fret": None},
                    "corrected_value": {"pitch": 60, "string": 2, "fret": 10},
                    "reason": "wrong string",
                    "applied_at": "2026-11-10T10:00:00",
                }
            ],
        )

        rows = build_correction_rows(tmp_path)
        assert rows == [
            {
                "schema_version": CORRECTION_DATASET_SCHEMA_VERSION,
                "job_id": "job-a",
                "correction_type": "solo_note",
                "index": 0,
                "original_value": {"pitch": 60, "string": None, "fret": None},
                "corrected_value": {"pitch": 60, "string": 2, "fret": 10},
                "reason": "wrong string",
                "applied_at": "2026-11-10T10:00:00",
            }
        ]

    def test_order_is_stable_across_jobs(self, tmp_path: Path) -> None:
        _seed_history(
            tmp_path,
            "job-b",
            [{"correction_type": "solo_note", "index": 1, "applied_at": "2026-11-10T09:00:00"}],
        )
        _seed_history(
            tmp_path,
            "job-a",
            [
                {"correction_type": "solo_note", "index": 2, "applied_at": "2026-11-10T10:00:00"},
                {"correction_type": "chord", "index": 0, "applied_at": "2026-11-10T08:00:00"},
            ],
        )

        rows = build_correction_rows(tmp_path)
        assert [(r["job_id"], r["applied_at"]) for r in rows] == [
            ("job-a", "2026-11-10T08:00:00"),
            ("job-a", "2026-11-10T10:00:00"),
            ("job-b", "2026-11-10T09:00:00"),
        ]

    def test_malformed_history_fails_loudly(self, tmp_path: Path) -> None:
        job_dir = tmp_path / "jobs" / "bad"
        job_dir.mkdir(parents=True)
        (job_dir / "corrections.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(ValueError, match="Malformed correction history"):
            build_correction_rows(tmp_path)

    def test_missing_jobs_dir_yields_no_rows(self, tmp_path: Path) -> None:
        assert build_correction_rows(tmp_path) == []

    def test_writes_jsonl(self, tmp_path: Path) -> None:
        rows = [{"schema_version": 1, "job_id": "j", "correction_type": "solo_note"}]
        out = tmp_path / "dataset" / "corrections.jsonl"
        assert write_correction_dataset(rows, out) == 1
        lines = out.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["job_id"] == "j"
