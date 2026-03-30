"""Pydantic API models — stubs for OpenAPI shape; fields filled in by later commits."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AnalyzeRequest(BaseModel):
    """YouTube URL or omitted when sending multipart audio instead."""

    url: str | None = None


class LessonSectionStub(BaseModel):
    """One teachable slice of the song — expand per README LessonJSON.sections."""

    model_config = ConfigDict(extra="allow")

    label: str | None = None
    confidence: float | None = None


class LessonJSON(BaseModel):
    """Full lesson payload returned when a job completes — see README LessonJSON schema."""

    model_config = ConfigDict(extra="allow")

    job_id: str | None = None
    song_title: str | None = None
    artist: str | None = None
    key: str | None = None
    key_confidence: float | None = None
    tempo: float | None = None
    tempo_confidence: float | None = None
    transcription_confidence: float | None = None
    beat_grid: list[float] = Field(default_factory=list)
    bar_timestamps: list[float] = Field(default_factory=list)
    stems: dict[str, str] = Field(default_factory=dict)
    lyrics_aligned: list[dict[str, Any]] = Field(default_factory=list)
    sections: list[LessonSectionStub] = Field(default_factory=list)


class JobStatus(BaseModel):
    """Polling response for GET /analyze/{job_id}."""

    status: Literal["processing", "complete", "failed"] = "processing"
    result: LessonJSON | None = None
    error: str | None = None
