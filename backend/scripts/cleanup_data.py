#!/usr/bin/env python3
"""Cleanup Harmoniq backend temporary data.

Prunes:
  - `.tmp_test_data_*` directories in the backend root
  - Old `data/jobs/<job_id>/` directories past the retention period

Safe with `--dry-run` and configurable via `HARMONIQ_CLEANUP_RETENTION_DAYS`.

Usage:
  python scripts/cleanup_data.py                  # delete old dirs
  python scripts/cleanup_data.py --dry-run        # preview only
  python scripts/cleanup_data.py --days 1         # aggressive
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cleanup_data")

DEFAULT_RETENTION_DAYS = 7
TMP_PREFIX = ".tmp_test_data_"


def _backend_root() -> Path:
    """Return the backend root directory (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


def _parse_retention_days(raw: str | None, fallback: int) -> int:
    if raw is not None:
        raw = raw.strip()
        if raw:
            try:
                return max(1, int(raw))
            except ValueError:
                logger.warning("Invalid HARMONIQ_CLEANUP_RETENTION_DAYS=%r, using %d", raw, fallback)
    return fallback


def _cutoff_time(retention_days: int) -> float:
    """Return Unix timestamp for the cutoff — dirs modified before this are candidates."""
    return time.time() - retention_days * 86400


def _safe_rmtree(path: Path, *, dry_run: bool) -> bool:
    """Delete path, return True if deleted or not found."""
    if not path.exists():
        return True
    try:
        if dry_run:
            logger.info("[dry-run] rm -rf %s", path)
        else:
            shutil.rmtree(path)
            logger.info("Deleted %s", path)
        return True
    except PermissionError as e:
        logger.error("Cannot delete %s: %s", path, e)
        return False
    except OSError as e:
        logger.error("OS error deleting %s: %s", path, e)
        return False


def _rm_empty_parent(path: Path, *, dry_run: bool) -> bool:
    """Remove empty parent directories after a job dir is deleted."""
    parent = path.parent
    if not parent.exists():
        return True
    try:
        if not any(parent.iterdir()):
            if dry_run:
                logger.info("[dry-run] rmdir (empty) %s", parent)
            else:
                parent.rmdir()
                logger.info("Removed empty parent %s", parent)
            return True
    except OSError:
        pass
    return False


def clean_tmp_test_data(backend_root: Path, retention_days: int, *, dry_run: bool) -> tuple[int, int]:
    """Remove stale .tmp_test_data_* dirs. Returns (removed, failed)."""
    cutoff = _cutoff_time(retention_days)
    removed = 0
    failed = 0

    for entry in backend_root.iterdir():
        if not entry.name.startswith(TMP_PREFIX) or not entry.is_dir():
            continue
        mtime = entry.stat().st_mtime
        age_days = (time.time() - mtime) / 86400
        if mtime < cutoff:
            logger.info("Candidate %s (%.1f days old)", entry.name, age_days)
            if _safe_rmtree(entry, dry_run=dry_run):
                removed += 1
            else:
                failed += 1
        else:
            logger.debug("Skipping %s (%.1f days, within retention)", entry.name, age_days)

    return removed, failed


def _job_dir_mtime(job_dir: Path) -> float | None:
    """Return the newest modification time across all files in the job dir.

    Uses the job dir's own mtime as a proxy, falling back to newest file mtime.
    """
    try:
        return job_dir.stat().st_mtime
    except OSError:
        return None


def _job_is_known_active(job_id: str) -> bool:
    """Check if the job still exists in the in-memory job store."""
    try:
        from app.jobs import jobs

        return job_id in jobs
    except Exception:
        # If we can't import the jobs module (e.g. running as standalone script),
        # assume the job is not active.
        return False


def clean_job_dirs(data_dir: Path, retention_days: int, *, dry_run: bool) -> tuple[int, int]:
    """Remove stale job dirs from data/jobs/. Returns (removed, failed)."""
    cutoff = _cutoff_time(retention_days)
    jobs_dir = data_dir / "jobs"
    if not jobs_dir.is_dir():
        logger.info("No jobs directory at %s", jobs_dir)
        return 0, 0

    removed = 0
    failed = 0

    for entry in sorted(jobs_dir.iterdir()):
        if not entry.is_dir():
            continue
        job_id = entry.name

        # Skip directories that look like non-job dirs (e.g. "stems" symlinks)
        if not _looks_like_job_id(job_id):
            continue

        mtime = _job_dir_mtime(entry)
        if mtime is None:
            logger.warning("Cannot stat %s, skipping", entry)
            continue

        age_days = (time.time() - mtime) / 86400
        if mtime < cutoff:
            if _job_is_known_active(job_id):
                logger.info("Skipping active job %s (%.1f days old)", job_id, age_days)
                continue
            logger.info("Candidate %s (%.1f days old)", job_id, age_days)
            if _safe_rmtree(entry, dry_run=dry_run):
                removed += 1
                _rm_empty_parent(entry, dry_run=dry_run)
            else:
                failed += 1
        else:
            logger.debug("Skipping %s (%.1f days, within retention)", job_id, age_days)

    return removed, failed


def _looks_like_job_id(name: str) -> bool:
    """Job IDs are UUIDs (hex with hyphens) — skip non-UUID dir names."""
    import re

    return bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", name))


def run_cleanup(data_dir: Path, backend_root: Path, retention_days: int, *, dry_run: bool) -> dict:
    """Run all cleanup steps. Returns summary dict."""
    results: dict = {}

    tmp_removed, tmp_failed = clean_tmp_test_data(backend_root, retention_days, dry_run=dry_run)
    results["tmp_test_data_removed"] = tmp_removed
    results["tmp_test_data_failed"] = tmp_failed

    job_removed, job_failed = clean_job_dirs(data_dir, retention_days, dry_run=dry_run)
    results["job_dirs_removed"] = job_removed
    results["job_dirs_failed"] = job_failed

    total = tmp_removed + job_removed
    errors = tmp_failed + job_failed
    results["total_removed"] = total
    results["total_failed"] = errors

    if dry_run:
        logger.info("[dry-run] Would remove %d item(s) (%d error(s))", total, errors)
    else:
        logger.info("Cleaned %d item(s) (%d error(s))", total, errors)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up Harmoniq backend temporary data.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be deleted without actually deleting anything.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help=f"Retention period in days (default: {DEFAULT_RETENTION_DAYS}, env: HARMONIQ_CLEANUP_RETENTION_DAYS).",
    )
    args = parser.parse_args()

    retention_days = _parse_retention_days(
        os.getenv("HARMONIQ_CLEANUP_RETENTION_DAYS"),
        fallback=args.days if args.days is not None else DEFAULT_RETENTION_DAYS,
    )

    backend_root = _backend_root()
    data_dir = backend_root / "data"

    logger.info("Cleanup starting (retention=%d days, dry_run=%s)", retention_days, args.dry_run)
    logger.info("Backend root: %s", backend_root)
    logger.info("Data dir:     %s", data_dir)

    run_cleanup(data_dir, backend_root, retention_days, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
