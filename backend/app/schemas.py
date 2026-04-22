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
    focus_area: CoachFocusArea | None = Field(
        default=None,
        description="Coach focus area for this session (commit 90): varies across sessions to prevent feedback redundancy.",
    )


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

MoodState = Literal["focused", "loose", "tired", "on_fire"]

CoachFocusArea = Literal["timing", "vibrato", "dynamics", "phrasing", "bending", "rhythm", "expression"]

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
    mood: MoodState | None = Field(
        default=None,
        description="Pre-session self-reported state — adapts slot mix, duration budget, BPM hints, coach tone (commit 76).",
    )
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


class SpotifyPlaybackState(BaseModel):
    """Normalized Spotify playback snapshot for listening follow mode (commit 77)."""

    model_config = ConfigDict(extra="ignore")

    is_playing: bool = False
    progress_ms: int = Field(default=0, ge=0)
    playback_rate: float = Field(default=1.0, ge=0.25, le=2.0)
    track_id: str | None = None
    track_name: str | None = None
    artists: list[str] = Field(default_factory=list)


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


class TimeSignature(BaseModel):
    numerator: int
    denominator: int


class BeatGrid(BaseModel):
    """Quantization grid from beat tracking (commit 78)."""
    model_config = ConfigDict(extra="ignore")

    bpm: float = Field(..., ge=20.0, le=900.0) # Increased max to account for subdivided grid BPMs
    beats: list[float] = Field(default_factory=list)
    downbeats: list[float] = Field(default_factory=list)
    time_signature: TimeSignature
    tick_value: float
    

class StemRoutingHints(BaseModel):
    """Stem selection hints handed off to chord/solo inference (commit 79 hook)."""

    model_config = ConfigDict(extra="ignore")

    chord_mix_stems: list[str] = Field(default_factory=lambda: ["bass", "other"])
    melodic_preference_order: list[str] = Field(default_factory=list)
    selected_melodic_stem: str = "guitar"


class TranscriptionPrepareResponse(BaseModel):
    """`POST /transcription/prepare` payload (commit 78)."""

    model_config = ConfigDict(extra="ignore")

    job_id: str
    stems: dict[str, str] = Field(default_factory=dict)
    beat_grid: BeatGrid
    stem_routing: StemRoutingHints
    audio_chunk_paths: list[str] = Field(default_factory=list)
    invalidated_artifacts: list[str] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    """YouTube URL or omitted when sending multipart audio instead."""

    url: str | None = None
    player_profile: PlayerProfile | None = None
    focus_area: CoachFocusArea | None = Field(
        default=None,
        description="Coach focus area for this session (commit 90): varies across sessions to prevent feedback redundancy.",
    )


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
    # Transcription validation metadata (commit #82)
    transcription_metadata: dict[str, Any] | None = None


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
    # Post–Demucs heuristics: piano-led / bleed (see app/stem_quality.py, docs/MANUAL_QA.md)
    stem_isolation_warning: str | None = None
    stem_quality_flags: list[str] = Field(default_factory=list)
    guitar_stem_usable: bool | None = None
    analysis_audio_role: str | None = None
    tabs_unavailable_reason: str | None = None
    # Commit 82: Low SNR warning for pre-emptive transcription quality warning
    low_snr_warning: bool | None = None


class JobStatus(BaseModel):
    """Polling response for GET /analyze/{job_id}."""

    status: Literal["processing", "complete", "failed"] = "processing"
    result: LessonJSON | None = None
    error: str | None = None
    error_code: str | None = Field(
        default=None,
        description="Stable machine code when status=failed; client maps in mapAnalyzeFlowError.",
    )
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
    solo_notes: SoloNotes | None = Field(default=None, description="MIDI note events for timing reference (commit 83)")


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
    coach_paragraph: str = Field(default="", description="Short coaching copy for journal / UI.")
    node_scores: dict[str, float] = Field(default_factory=dict)
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


class MusicXMLJsonExportRequest(BaseModel):
    """POST /export/musicxml-from-json — MusicXML from Harmoniq JSON artifacts."""

    model_config = ConfigDict(extra="forbid")

    beat_grid: BeatGrid
    chord_timeline: ChordTimeline
    solo_notes: SoloNotes
    title: str = Field("Harmoniq Score", max_length=200, description="Optional title for the score.")
    artist: str = Field("Harmoniq AI", max_length=200, description="Optional artist for the score.")
    key_signature: str | None = Field(
        default=None,
        max_length=80,
        description="Optional key signature (e.g., 'C major', 'A minor'). If omitted, C major is used.",
    )

# Commit 79 Schemas

class ChordEvent(BaseModel):
    timestamp: float = Field(..., description="Start time of the chord in seconds")
    chord: str = Field(..., description="Chord symbol (e.g., 'C:maj', 'N')")
    confidence: float = Field(..., ge=0.0, le=1.0)

class ChordTimeline(BaseModel):
    events: list[ChordEvent]

class SoloNote(BaseModel):
    start_time: float = Field(..., description="Quantized start time in seconds")
    duration: float = Field(..., description="Quantized duration in seconds", ge=0)
    pitch: int = Field(..., description="MIDI pitch number (e.g., 60 for Middle C)")
    velocity: int = Field(..., ge=0, le=127)

class SoloNotes(BaseModel):
    notes: list[SoloNote]

# Commit 82 Schemas

class TranscriptionVerifyRequest(BaseModel):
    """POST /transcription/verify — user corrections for low-confidence transcriptions."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., description="Job ID to apply corrections to")
    section_index: int | None = Field(default=None, description="Section index to apply corrections to (optional, applies to all sections if null)")
    stem_routing_override: str | None = Field(default=None, description="User-selected stem override (e.g., 'guitar_stem', 'full_mix')")
    user_confirmed: bool = Field(default=False, description="Whether user confirmed the transcription is correct")
    user_notes: str | None = Field(default=None, description="Optional user notes about the correction")

class TranscriptionVerifyResponse(BaseModel):
    """Response from POST /transcription/verify."""

    success: bool
    message: str
    corrections_applied: bool

# Commit 84 Schemas

class OrientClipRequest(BaseModel):
    """POST /session/orient-clip — request for generating orient clip."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., description="Job ID to generate clip for")
    style_label: str | None = Field(default=None, description="Musical style (e.g., 'rock', 'blues')")
    technique: str | None = Field(default=None, description="Target technique (e.g., 'bend', 'hammer-on')")
    key: str | None = Field(default=None, description="Musical key (e.g., 'C major')")
    bpm: float | None = Field(default=None, description="Tempo in beats per minute")

class OrientClipResponse(BaseModel):
    """Response from POST /session/orient-clip."""

    wav_path: str = Field(..., description="Path to generated WAV file")
    annotation: str = Field(..., description="What to listen for in the clip")
    duration: float = Field(..., description="Duration in seconds")
    used_placeholder: bool = Field(default=False, description="Whether a placeholder was used")
    placeholder_reason: str | None = Field(default=None, description="Reason for placeholder if used")

# Commit 85 Schemas

class TheoryAnnotationRequest(BaseModel):
    """POST /theory/annotation — plain-language theory rationale for a chord in a key context (PRIORITIES §85)."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., description="Musical key (e.g., 'C major', 'A minor')")
    chord: str = Field(..., description="Chord symbol (e.g., 'C:maj', 'D:min')")
    chord_function: str = Field(..., description="Roman numeral function (e.g., 'I', 'IV', 'V')")


class TheoryAnnotationResponse(BaseModel):
    """Response from POST /theory/annotation."""

    rationale: str = Field(..., description="Plain-language explanation of the chord's function")

class AnalyzeTranscriptionResponse(BaseModel):
    job_id: str
    chord_timeline: ChordTimeline
    solo_notes: SoloNotes