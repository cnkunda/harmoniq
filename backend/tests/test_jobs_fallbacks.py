"""Tests for Commit 8 jobs fallback observability."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import jobs
from app.schemas import JobStatus


def test_save_job_to_disk_failure_is_nonfatal_and_records_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[tuple[str, str]] = []

    def _record(stage: str, reason: str = "exception") -> None:
        recorded.append((stage, reason))

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(jobs, "record_fallback", _record)
    monkeypatch.setattr(Path, "write_text", _boom)
    jobs.jobs["job-disk"] = JobStatus(status="complete")
    try:
        jobs.save_job_to_disk("job-disk")  # must not raise
    finally:
        jobs.jobs.pop("job-disk", None)

    assert ("disk_persist", "exception") in recorded
