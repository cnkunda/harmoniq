"""Persistent analysis store — filesystem JSON-backed (Phase 3 Commit 109).

Replaces the in-memory jobs dict for analysis artifact persistence.
Analysis outputs (beat grid, chord timeline, solo notes, MusicXML) are
stored as JSON files in the job directory, surviving server restarts.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from app.schemas import (
    BeatGrid,
    ChordEvent,
    ChordTimeline,
    CorrectionRecord,
    LessonJSON,
    SoloNote,
    SoloNotes,
)

logger = logging.getLogger("harmoniq.analysis_store")

ARTIFACT_FILES = {
    "beat_grid": "BeatGrid.json",
    "chord_timeline": "chordTimeline.json",
    "solo_notes": "SoloNotes.json",
    "musicxml": "score.musicxml",
    "lesson": "lesson.json",
    "corrections": "corrections.json",
}


def _job_dir(job_id: str) -> Path:
    from app.ingest import get_job_dir
    return get_job_dir(job_id)


def save_artifact(job_id: str, artifact_name: str, data: str) -> None:
    """Save a string artifact to the job directory."""
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    filename = ARTIFACT_FILES.get(artifact_name, f"{artifact_name}.json")
    (job_dir / filename).write_text(data)


def load_artifact(job_id: str, artifact_name: str) -> str | None:
    """Load a string artifact from the job directory."""
    job_dir = _job_dir(job_id)
    filename = ARTIFACT_FILES.get(artifact_name, f"{artifact_name}.json")
    path = job_dir / filename
    if path.exists():
        return path.read_text()
    return None


def save_beat_grid(job_id: str, beat_grid: BeatGrid) -> None:
    save_artifact(job_id, "beat_grid", beat_grid.model_dump_json(indent=2))


def load_beat_grid(job_id: str) -> BeatGrid | None:
    raw = load_artifact(job_id, "beat_grid")
    if raw:
        return BeatGrid.model_validate_json(raw)
    return None


def save_chord_timeline(job_id: str, chord_timeline: ChordTimeline) -> None:
    save_artifact(job_id, "chord_timeline", chord_timeline.model_dump_json(indent=2))


def load_chord_timeline(job_id: str) -> ChordTimeline | None:
    raw = load_artifact(job_id, "chord_timeline")
    if raw:
        return ChordTimeline.model_validate_json(raw)
    return None


def save_solo_notes(job_id: str, solo_notes: SoloNotes) -> None:
    save_artifact(job_id, "solo_notes", solo_notes.model_dump_json(indent=2))


def load_solo_notes(job_id: str) -> SoloNotes | None:
    raw = load_artifact(job_id, "solo_notes")
    if raw:
        return SoloNotes.model_validate_json(raw)
    return None


def save_musicxml(job_id: str, musicxml: str) -> None:
    save_artifact(job_id, "musicxml", musicxml)


def load_musicxml(job_id: str) -> str | None:
    return load_artifact(job_id, "musicxml")


def save_lesson(job_id: str, lesson: LessonJSON) -> None:
    save_artifact(job_id, "lesson", lesson.model_dump_json(indent=2))


def load_lesson(job_id: str) -> LessonJSON | None:
    raw = load_artifact(job_id, "lesson")
    if raw:
        return LessonJSON.model_validate_json(raw)
    return None


def save_corrections(job_id: str, corrections: list[dict]) -> None:
    save_artifact(job_id, "corrections", json.dumps(corrections, indent=2))


def load_corrections(job_id: str) -> list[dict]:
    raw = load_artifact(job_id, "corrections")
    if raw:
        return json.loads(raw)
    return []


def list_persisted_jobs() -> list[str]:
    """List all job IDs that have persisted artifacts."""
    from app.ingest import get_data_dir
    data_dir = get_data_dir()
    jobs_dir = data_dir / "jobs"
    if not jobs_dir.exists():
        return []
    return [d.name for d in jobs_dir.iterdir() if d.is_dir() and (d / "lesson.json").exists()]


def cleanup_expired_jobs(ttl_hours: int = 24) -> int:
    """Remove persisted artifacts for jobs older than TTL."""
    from app.ingest import get_data_dir
    data_dir = get_data_dir()
    jobs_dir = data_dir / "jobs"
    if not jobs_dir.exists():
        return 0

    cutoff = time.time() - (ttl_hours * 3600)
    removed = 0
    for job_dir in jobs_dir.iterdir():
        if not job_dir.is_dir():
            continue
        lesson_path = job_dir / "lesson.json"
        if lesson_path.exists() and lesson_path.stat().st_mtime < cutoff:
            try:
                import shutil
                shutil.rmtree(job_dir)
                removed += 1
            except Exception:
                logger.exception("failed to remove expired job_dir=%s", job_dir)
    return removed
