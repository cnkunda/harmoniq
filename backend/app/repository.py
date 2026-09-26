"""Synchronous repository layer over Postgres for job state.

Used by both worker threads (sync) and wrapped in asyncio.to_thread() from
FastAPI endpoints. All mutations go through this layer so the DB is the
single source of truth.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.db import get_session
from app.models import (
    ChordEnrichmentModel,
    CoachHydrationModel,
    JobModel,
    RecomputeJobModel,
)
from app.schemas import (
    BeatGrid,
    ChordEnrichmentStatus,
    CoachHydrationSection,
    CoachHydrationStatus,
    JobStatus,
    LessonJSON,
)

logger = logging.getLogger("harmoniq.repository")

# ── Job CRUD ──────────────────────────────────────────────────────────────

def create_job(
    job_id: str,
    status: str = "processing",
    progress: float | None = 0.05,
    stage_label: str | None = "Queued\u2026",
    analysis_stage: str | None = "initializing",
) -> None:
    session = get_session()
    try:
        session.add(
            JobModel(
                job_id=job_id,
                status=status,
                progress=progress,
                stage_label=stage_label,
                analysis_stage=analysis_stage,
                processing_started_at=datetime.now(timezone.utc).timestamp(),
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def get_job(job_id: str) -> JobStatus | None:
    session = get_session()
    try:
        result = session.execute(select(JobModel).where(JobModel.job_id == job_id))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _job_model_to_status(row)
    finally:
        session.close()

def update_job_progress(
    job_id: str,
    *,
    progress: float | None = None,
    stage_label: str | None = None,
    analysis_stage: str | None = None,
) -> None:
    updates: dict = {"updated_at": datetime.now(timezone.utc)}
    if progress is not None:
        updates["progress"] = max(0.0, min(1.0, float(progress)))
    if stage_label is not None:
        updates["stage_label"] = stage_label
    if analysis_stage is not None:
        updates["analysis_stage"] = analysis_stage
    session = get_session()
    try:
        session.execute(
            update(JobModel).where(JobModel.job_id == job_id).values(**updates)
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def complete_job(job_id: str, result: LessonJSON) -> None:
    session = get_session()
    try:
        session.execute(
            update(JobModel)
            .where(JobModel.job_id == job_id)
            .values(
                status="complete",
                progress=1.0,
                stage_label="complete",
                analysis_stage="complete",
                result=result.model_dump(exclude_none=True),
                error=None,
                error_code=None,
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_active_jobs() -> list[JobStatus]:
    """Load all processing and complete jobs from DB. Used on startup to warm the cache."""
    session = get_session()
    try:
        rows = session.execute(
            select(JobModel).where(JobModel.status.in_(["processing", "complete"]))
        ).scalars().all()
        return [_job_model_to_status(r) for r in rows]
    finally:
        session.close()


def fail_job(
    job_id: str,
    error: str,
    error_code: str | None = None,
) -> None:
    session = get_session()
    try:
        session.execute(
            update(JobModel)
            .where(JobModel.job_id == job_id)
            .values(
                status="failed",
                error=error,
                error_code=error_code,
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _job_model_to_status(row: JobModel) -> JobStatus:
    result = None
    if row.result is not None:
        try:
            result = LessonJSON.model_validate(row.result)
        except Exception:
            logger.exception("Failed to parse stored result for job_id=%s", row.job_id)
    return JobStatus(
        status=row.status,
        result=result,
        error=row.error,
        error_code=row.error_code,
        progress=row.progress,
        stage_label=row.stage_label,
        processing_started_at=row.processing_started_at,
        analysis_stage=row.analysis_stage,
    )


# ── Coach Hydration ───────────────────────────────────────────────────────


def upsert_coach_hydration(
    job_id: str,
    status: str,
    sections: list[dict] | None = None,
    fallback_reason: str | None = None,
) -> None:
    session = get_session()
    try:
        existing = session.execute(
            select(CoachHydrationModel).where(CoachHydrationModel.job_id == job_id)
        )
        row = existing.scalar_one_or_none()
        if row is None:
            session.add(
                CoachHydrationModel(
                    job_id=job_id,
                    status=status,
                    sections=sections or [],
                    fallback_reason=fallback_reason,
                )
            )
        else:
            row.status = status
            if sections is not None:
                row.sections = sections
            row.fallback_reason = fallback_reason
            row.updated_at = datetime.now(timezone.utc)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_coach_hydration_status(job_id: str) -> CoachHydrationStatus | None:
    session = get_session()
    try:
        result = session.execute(
            select(CoachHydrationModel).where(CoachHydrationModel.job_id == job_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        sections = [
            CoachHydrationSection(**s) if isinstance(s, dict) else s
            for s in (row.sections or [])
        ]
        return CoachHydrationStatus(
            status=row.status,
            sections=sections,
            fallback_reason=row.fallback_reason,
        )
    finally:
        session.close()


# ── Chord Enrichment ──────────────────────────────────────────────────────


def upsert_chord_enrichment(
    job_id: str,
    status: str,
    *,
    total_events: int | None = None,
    corrected_events: int | None = None,
    llm_latency_p50: float | None = None,
    llm_latency_p95: float | None = None,
    fallback_reason: str | None = None,
) -> None:
    session = get_session()
    try:
        existing = session.execute(
            select(ChordEnrichmentModel).where(ChordEnrichmentModel.job_id == job_id)
        )
        row = existing.scalar_one_or_none()
        if row is None:
            session.add(
                ChordEnrichmentModel(
                    job_id=job_id,
                    status=status,
                    total_events=total_events,
                    corrected_events=corrected_events,
                    llm_latency_p50=llm_latency_p50,
                    llm_latency_p95=llm_latency_p95,
                    fallback_reason=fallback_reason,
                )
            )
        else:
            row.status = status
            if total_events is not None:
                row.total_events = total_events
            if corrected_events is not None:
                row.corrected_events = corrected_events
            if llm_latency_p50 is not None:
                row.llm_latency_p50 = llm_latency_p50
            if llm_latency_p95 is not None:
                row.llm_latency_p95 = llm_latency_p95
            row.fallback_reason = fallback_reason
            row.updated_at = datetime.now(timezone.utc)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_chord_enrichment_status(job_id: str) -> ChordEnrichmentStatus | None:
    session = get_session()
    try:
        result = session.execute(
            select(ChordEnrichmentModel).where(ChordEnrichmentModel.job_id == job_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return ChordEnrichmentStatus(
            status=row.status,
            total_events=row.total_events or 0,
            corrected_events=row.corrected_events or 0,
            llm_latency_p50=row.llm_latency_p50,
            llm_latency_p95=row.llm_latency_p95,
            fallback_reason=row.fallback_reason,
        )
    finally:
        session.close()


# ── Recompute Jobs ────────────────────────────────────────────────────────


def upsert_recompute_job(
    job_id: str,
    status: str,
    *,
    progress: float | None = None,
    stage_label: str | None = None,
    beat_grid: BeatGrid | None = None,
    chord_timeline: dict | None = None,
    solo_notes: dict | None = None,
    musicxml: str | None = None,
    bar_timestamps: list[float] | None = None,
    error: str | None = None,
) -> None:
    session = get_session()
    try:
        existing = session.execute(
            select(RecomputeJobModel).where(RecomputeJobModel.job_id == job_id)
        )
        row = existing.scalar_one_or_none()
        if row is None:
            session.add(
                RecomputeJobModel(
                    job_id=job_id,
                    status=status,
                    progress=progress,
                    stage_label=stage_label,
                    beat_grid=beat_grid.model_dump() if beat_grid else None,
                    chord_timeline=chord_timeline,
                    solo_notes=solo_notes,
                    musicxml=musicxml,
                    bar_timestamps=bar_timestamps,
                    error=error,
                )
            )
        else:
            row.status = status
            if progress is not None:
                row.progress = progress
            if stage_label is not None:
                row.stage_label = stage_label
            if beat_grid is not None:
                row.beat_grid = beat_grid.model_dump()
            if chord_timeline is not None:
                row.chord_timeline = chord_timeline
            if solo_notes is not None:
                row.solo_notes = solo_notes
            if musicxml is not None:
                row.musicxml = musicxml
            if bar_timestamps is not None:
                row.bar_timestamps = bar_timestamps
            if error is not None:
                row.error = error
            row.updated_at = datetime.now(timezone.utc)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_recompute_job_status(job_id: str) -> dict | None:
    session = get_session()
    try:
        result = session.execute(
            select(RecomputeJobModel).where(RecomputeJobModel.job_id == job_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "job_id": row.job_id,
            "status": row.status,
            "progress": row.progress,
            "stage_label": row.stage_label,
            "beat_grid": row.beat_grid,
            "chord_timeline": row.chord_timeline,
            "solo_notes": row.solo_notes,
            "musicxml": row.musicxml,
            "bar_timestamps": row.bar_timestamps,
            "error": row.error,
        }
    finally:
        session.close()
