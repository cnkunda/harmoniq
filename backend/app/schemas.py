"""Pydantic API models — stubs for OpenAPI shape; fields filled in by later commits."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SkillNode(BaseModel):
    """One skill row snapshot for personalized coach context (analyze)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    label: str | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)


class PlayerProfile(BaseModel):
    """Optional client-provided profile for coach conditioning on POST /analyze."""

    model_config = ConfigDict(extra="ignore")

    weak_areas: list[str] = Field(default_factory=list)
    skill_nodes: list[SkillNode] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    """YouTube URL or omitted when sending multipart audio instead."""

    url: str | None = None
    player_profile: PlayerProfile | None = None


class AnalyzeJobCreated(BaseModel):
    """Immediate response from POST /analyze — processing is stubbed as complete in-memory."""

    job_id: str


class LessonSectionStub(BaseModel):
    """One teachable slice of the song — expand per README LessonJSON.sections."""

    model_config = ConfigDict(extra="allow")

    label: str | None = None
    confidence: float | None = None
    # Start time in seconds for Listen step section chips (librosa segments).
    start_time_seconds: float | None = None


class LessonJSON(BaseModel):
    """Full lesson payload returned when a job completes — see README LessonJSON schema."""

    model_config = ConfigDict(extra="allow")

    job_id: str | None = None
    song_title: str | None = None
    artist: str | None = None
    style_label: str | None = None
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


class ScoreRequest(BaseModel):
    """POST /score request payload."""

    model_config = ConfigDict(extra="allow")

    recording_wav_base64: str
    recording_mime_type: str | None = None
    section: dict[str, Any] = Field(default_factory=dict)
    skill_nodes: list[str] = Field(default_factory=list)


class ScoreWaveformComparison(BaseModel):
    user_wav_base64: str = ""
    reference_wav_base64: str = ""


class ScoreResult(BaseModel):
    """POST /score response payload."""

    pitch_accuracy: float
    note_duration_deltas: list[float] = Field(default_factory=list)
    phrasing_score: float
    bend_pitch_error_cents: float
    rushing_score: float
    node_scores: dict[str, float] = Field(default_factory=list)
    waveform_comparison: ScoreWaveformComparison


class OnboardingPlacementRequest(BaseModel):
    """Aggregated placement metrics for coach paragraph (PRIORITIES §32)."""

    pitch_avg: float = Field(ge=0.0, le=1.0)
    phrasing_avg: float = Field(ge=0.0, le=1.0)
    timing_avg: float = Field(ge=0.0, le=1.0)
    bend_error_cents_avg: float = Field(ge=0.0)


class OnboardingPlacementResponse(BaseModel):
    coach_paragraph: str


class JamScoreRequest(BaseModel):
    """POST /jam-score — passive jam summary (PRIORITIES §36)."""

    model_config = ConfigDict(extra="allow")

    recording_wav_base64: str = ""
    duration_seconds: int = Field(ge=0, default=0)
    scale_position_map: dict[str, float] = Field(default_factory=dict)
    inferred_scale_label: str | None = None


class JamScoreResult(BaseModel):
    coach_summary: str
    scale_position_map: dict[str, float] = Field(default_factory=dict)


QuickAccuracyLabel = Literal["hit", "close", "miss"]


class QuickFeedbackRequest(BaseModel):
    """POST /quick-feedback — per-beat accuracy from Play step (PRIORITIES §49)."""

    accuracy_pattern: list[QuickAccuracyLabel] = Field(default_factory=list, max_length=64)


class QuickFeedbackResponse(BaseModel):
    message: str
