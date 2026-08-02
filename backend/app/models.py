from __future__ import annotations

import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class JobModel(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="processing", index=True)
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    stage_label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    analysis_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processing_started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


class CoachHydrationModel(Base):
    __tablename__ = "coach_hydration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    sections: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


class ChordEnrichmentModel(Base):
    __tablename__ = "chord_enrichment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    total_events: Mapped[int | None] = mapped_column(Integer, nullable=True)
    corrected_events: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_latency_p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_latency_p95: Mapped[float | None] = mapped_column(Float, nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


class RecomputeJobModel(Base):
    __tablename__ = "recompute_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    stage_label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    beat_grid: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    chord_timeline: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    solo_notes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    musicxml: Mapped[str | None] = mapped_column(Text, nullable=True)
    bar_timestamps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )
