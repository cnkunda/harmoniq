"""Pydantic API models — stubs for OpenAPI shape; fields filled in by later commits."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SkillNode(BaseModel):
    """One skill row snapshot for personalized coach context (analyze)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    label: str | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)


class QuizAnswers(BaseModel):
    """Cold-start quiz payload (commit 69); commit 68 derives `TasteProfile` from it."""

    model_config = ConfigDict(extra="ignore")

    selected_artists: list[str] = Field(default_factory=list)
    selected_style: str = ""
    experience_level: Literal["beginner", "intermediate", "advanced"] = "intermediate"


class TasteProfile(BaseModel):
    """Derived teaching taste — curriculum + coach read via `PlayerProfile.taste_profile` (commit 68)."""

    model_config = ConfigDict(extra="ignore")

    style_label: str = "pop"
    technique_affinity: list[str] = Field(default_factory=list)
    bpm_comfort_range: tuple[int, int] = (80, 120)
    song_candidates: list[str] = Field(default_factory=list)
    source: Literal["spotify", "quiz", "manual"] = "spotify"


class LearningContext(BaseModel):
    """User-declared tier + optional focus notes from app Settings / taste quiz."""

    model_config = ConfigDict(extra="ignore")

    experience_level: Literal["beginner", "intermediate", "advanced"] | None = None
    solo_focus_notes: str | None = Field(default=None, max_length=800)


class PlayerProfile(BaseModel):
    """Optional client-provided profile for coach conditioning on POST /analyze."""

    model_config = ConfigDict(extra="ignore")

    weak_areas: list[str] = Field(default_factory=list)
    skill_nodes: list[SkillNode] = Field(default_factory=list)
    taste_profile: TasteProfile | None = None
    learning_context: LearningContext | None = None


class CurriculumSuggestRequest(BaseModel):
    """POST /curriculum/suggest payload (commit 65)."""

    model_config = ConfigDict(extra="ignore")

    player_profile: PlayerProfile | None = None
    job_ids: list[str] = Field(default_factory=list)


class CurriculumSuggestionItem(BaseModel):
    job_id: str
    reason_label: str
    technique_focus: str


class CurriculumSuggestResponse(BaseModel):
    ranked: list[CurriculumSuggestionItem] = Field(default_factory=list)


SlotType = Literal["warmup", "technique", "song_section", "free_jam"]

FretboardGuideVariant = Literal["primary", "secondary"]


class FretboardGuideCell(BaseModel):
    """Tab string (1 = high E) + fret for warm-up fretboard highlights."""

    model_config = ConfigDict(extra="ignore")

    string: int = Field(..., ge=1, le=6)
    fret: int = Field(..., ge=0, le=12)
    variant: FretboardGuideVariant = "primary"


class FretboardGuide(BaseModel):
    """Curriculum-authored cells + optional caption (pool → API → client)."""

    model_config = ConfigDict(extra="ignore")

    cells: list[FretboardGuideCell] = Field(default_factory=list)
    caption: str | None = Field(default=None, max_length=500)


class WarmupExercise(BaseModel):
    """One step inside the session opener (commit 73)."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    duration_seconds: int = Field(..., ge=30, le=300)
    tab_snippet_gp5_base64: str | None = Field(default=None, max_length=2_000_000)
    technique_tag: str = Field(..., min_length=1, max_length=80)
    bpm: int = Field(..., ge=40, le=240)
    fretboard_guide: FretboardGuide | None = None


class WarmupPlan(BaseModel):
    """Three-move personalized warm-up (~3 minutes)."""

    model_config = ConfigDict(extra="ignore")

    exercises: list[WarmupExercise] = Field(default_factory=list)
    total_duration_seconds: int = Field(ge=0, default=0)


class DrillSlot(BaseModel):
    """One ordered step in a generated practice session (commit 70)."""

    model_config = ConfigDict(extra="ignore")

    slot_type: SlotType
    duration_seconds: int = Field(..., ge=60, le=7200)
    title: str = Field(..., min_length=1, max_length=200)
    coach_intro: str = Field(default="", max_length=500)
    lesson_ref: str | None = Field(default=None, max_length=80)
    exercise_ref: str | None = Field(default=None, max_length=80)
    technique_focus: str | None = Field(default=None, max_length=80)
    warmup_plan: WarmupPlan | None = None


class PracticePlan(BaseModel):
    """Ordered drills for one sitting — client drives navigation + lesson load."""

    model_config = ConfigDict(extra="ignore")

    slots: list[DrillSlot] = Field(default_factory=list)
    total_duration_seconds: int = Field(ge=0, default=0)


class PracticePlanRequest(BaseModel):
    """POST /practice/plan payload (commit 70)."""

    model_config = ConfigDict(extra="ignore")

    player_profile: PlayerProfile | None = None
    job_ids: list[str] = Field(default_factory=list)
    duration_minutes: int = Field(default=25, ge=10, le=120)
    library_lessons: list[LessonJSON] = Field(
        default_factory=list,
        description="Full LessonJSON from device when server job store has no completed result.",
    )


class SpotifyTasteProfile(BaseModel):
    """Aggregated listening taste from Spotify Web API (commit 67) — no tokens."""

    model_config = ConfigDict(extra="ignore")

    top_genres: list[str] = Field(default_factory=list)
    top_artists: list[str] = Field(default_factory=list)
    energy_avg: float = 0.0
    tempo_avg: float = 0.0
    instrumentalness_avg: float = 0.0


class TasteDeriveRequest(BaseModel):
    """POST /taste/derive — exactly one of Spotify-shaped taste or quiz answers."""

    model_config = ConfigDict(extra="ignore")

    spotify_profile: SpotifyTasteProfile | None = None
    quiz_answers: QuizAnswers | None = None
    taste_source: Literal["spotify", "manual"] | None = Field(
        default=None,
        description="When using `spotify_profile`, set `manual` for curated non-Spotify taste payloads.",
    )

    @model_validator(mode="after")
    def _exactly_one_input(self) -> TasteDeriveRequest:
        has_spotify = self.spotify_profile is not None
        has_quiz = self.quiz_answers is not None
        if has_spotify == has_quiz:
            raise ValueError("Provide exactly one of spotify_profile or quiz_answers.")
        return self


class AnalyzeRequest(BaseModel):
    """YouTube URL or omitted when sending multipart audio instead."""

    url: str | None = None
    player_profile: PlayerProfile | None = None


class AnalyzeJobCreated(BaseModel):
    """Immediate response from POST /analyze — processing is stubbed as complete in-memory."""

    job_id: str


class AlphaTabPartialPrerender(BaseModel):
    """One SVG fragment produced by AlphaTab ScoreRenderer (Node bridge)."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    svg: str = ""


class AlphaTabPrerenderBundle(BaseModel):
    """Disk artifact next to job outputs — fetched by the client for faster first paint."""

    model_config = ConfigDict(extra="ignore")

    ok: bool = True
    alphatab_version: str = ""
    preset_version: str = ""
    score_sha256: str = ""
    master_bar_count: int = 0
    total_width: int = 0
    total_height: int = 0
    partial_count: int = 0
    partials: list[AlphaTabPartialPrerender] = Field(default_factory=list)


class AlphaTabPrerenderHints(BaseModel):
    """Lesson-root pointers to prerender artifacts (small JSON)."""

    model_config = ConfigDict(extra="ignore")

    alphatab_version: str
    preset_version: str
    score_sha256: str
    cache_key: str
    master_bar_count: int
    total_width: int
    total_height: int
    partial_count: int
    artifact_rel: str | None = None


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
    alphatab_prerender_hints: AlphaTabPrerenderHints | None = None


class JobStatus(BaseModel):
    """Polling response for GET /analyze/{job_id}."""

    status: Literal["processing", "complete", "failed"] = "processing"
    result: LessonJSON | None = None
    error: str | None = None
    progress: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Approximate progress 0–1 while processing.",
    )
    stage_label: str | None = Field(
        default=None,
        description="Short stage label while processing.",
    )
    processing_started_at: float | None = Field(
        default=None,
        description="Unix timestamp when processing began (server clock).",
    )


class CoachHydrationSection(BaseModel):
    index: int
    coach_note: str = ""
    coach_explanation: str = ""


class CoachHydrationStatus(BaseModel):
    """GET /analyze/{job_id}/coach status payload (commit 66)."""

    status: Literal["pending", "complete", "fallback"] = "pending"
    sections: list[CoachHydrationSection] = Field(default_factory=list)
    fallback_reason: str | None = None


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


class ScoreDiagnostics(BaseModel):
    signal_quality: float = Field(ge=0.0, le=1.0, default=0.0)
    voiced_ratio: float = Field(ge=0.0, le=1.0, default=0.0)
    harmonic_ratio: float = Field(ge=0.0, le=1.0, default=0.0)
    timing_residual_p50_ms: float = 0.0
    timing_residual_p95_ms: float = 0.0
    reliability_flags: list[str] = Field(default_factory=list)


class ReliabilityEnvelope(BaseModel):
    score_contract_version: str = "v2"
    confidence: Literal["low", "medium", "high"] = "low"
    signal_quality: float = Field(ge=0.0, le=1.0, default=0.0)
    reliability_flags: list[str] = Field(default_factory=list)


class ScoreResult(BaseModel):
    """POST /score response payload."""

    pitch_accuracy: float
    note_duration_deltas: list[float] = Field(default_factory=list)
    phrasing_score: float
    bend_pitch_error_cents: float
    rushing_score: float
    node_scores: dict[str, float] = Field(default_factory=list)
    waveform_comparison: ScoreWaveformComparison
    diagnostics: ScoreDiagnostics = Field(default_factory=ScoreDiagnostics)
    reliability: ReliabilityEnvelope = Field(default_factory=ReliabilityEnvelope)


class OnboardingPlacementRequest(BaseModel):
    """Aggregated placement metrics for coach paragraph (PRIORITIES §32)."""

    pitch_avg: float = Field(ge=0.0, le=1.0)
    phrasing_avg: float = Field(ge=0.0, le=1.0)
    timing_avg: float = Field(ge=0.0, le=1.0)
    bend_error_cents_avg: float = Field(ge=0.0)
    placement_confidence: Literal["low", "medium", "high"] | None = None
    reliability_flags: list[str] = Field(default_factory=list)


class OnboardingPlacementResponse(BaseModel):
    coach_paragraph: str
    confidence_note: str | None = None


class JamScoreRequest(BaseModel):
    """POST /jam-score — passive jam summary (PRIORITIES §36)."""

    model_config = ConfigDict(extra="allow")

    recording_wav_base64: str = ""
    duration_seconds: int = Field(ge=0, default=0)
    # Legacy alias; kept while app migrates to explicit pitch map naming.
    scale_position_map: dict[str, float] = Field(default_factory=dict)
    pitch_class_weight_map: dict[str, float] = Field(default_factory=dict)
    position_weight_map: dict[str, float] = Field(default_factory=dict)
    inferred_scale_label: str | None = None
    inference_confidence: Literal["low", "medium", "high"] | None = None
    track_id: str | None = None
    track_label: str | None = None
    track_key: str | None = None
    track_bpm: int | None = Field(default=None, ge=0)


class JamScoreResult(BaseModel):
    coach_summary: str
    # Legacy alias for older clients.
    scale_position_map: dict[str, float] = Field(default_factory=dict)
    pitch_class_weight_map: dict[str, float] = Field(default_factory=dict)
    position_weight_map: dict[str, float] = Field(default_factory=dict)
    inferred_scale_label: str | None = None
    inference_confidence: Literal["low", "medium", "high"] | None = None
    focus_pitch_class_key: str | None = None
    focus_pitch_class_weight: float | None = None
    reliability_tags: list[str] = Field(default_factory=list)
    reliability: ReliabilityEnvelope = Field(default_factory=ReliabilityEnvelope)


QuickAccuracyLabel = Literal["hit", "close", "miss", "vibrato"]


class QuickFeedbackRequest(BaseModel):
    """POST /quick-feedback — per-beat accuracy from Play step (PRIORITIES §49)."""

    accuracy_pattern: list[QuickAccuracyLabel] = Field(default_factory=list, max_length=64)


class QuickFeedbackResponse(BaseModel):
    message: str


class JamBackingRequest(BaseModel):
    """POST /jam/backing — instrumental practice bed via Gemini Lyria (fallback-capable)."""

    model_config = ConfigDict(extra="ignore")

    musical_key: str = Field(..., min_length=1, max_length=80)
    bpm: int | None = Field(default=None, ge=40, le=240)
    weak_areas: list[str] = Field(default_factory=list, max_length=24)
    style_hint: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=64)


class JamBackingResponse(BaseModel):
    audio_base64: str
    mime_type: str = "audio/wav"
    format: Literal["wav"] = "wav"
    prompt_used: str
    duration_ms: int | None = None


class ExportRequest(BaseModel):
    """POST /export — Guitar Pro 5 binary (base64) to MIDI or MusicXML (PRIORITIES §58)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    gp5_base64: str = Field(..., min_length=8, max_length=40_000_000)
    export_format: Literal["midi", "musicxml", "pdf", "png"] = Field(
        ...,
        alias="format",
        description="Target export format; pdf/png may be rejected by the server build.",
    )
    title: str | None = Field(default=None, max_length=200, description="Optional filename stem hint.")
