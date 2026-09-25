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

MusicalToleranceMode = Literal["expressive", "technique"]


class FretboardGuideCell(BaseModel):
    """Tab string (1 = high E) + fret for warm-up fretboard highlights."""

    model_config = ConfigDict(extra="ignore")

    string: int = Field(..., ge=1, le=6)
    fret: int = Field(..., ge=0, le=24)
    variant: FretboardGuideVariant = "primary"
    finger: int | None = Field(default=None, ge=1, le=4, description="Finger to use (1=index, 2=middle, 3=ring, 4=pinky)")


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
    difficulty: int = Field(default=2, ge=1, le=3)


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

    bpm: float = Field(..., ge=20.0, le=900.0)  # Grid BPM (eighth notes for compound meters)
    pulse_bpm: float = Field(default=0.0, ge=20.0, le=300.0)  # Pulse tempo (e.g., dotted quarter for 6/8)
    beats: list[float] = Field(default_factory=list)
    downbeats: list[float] = Field(default_factory=list)
    time_signature: TimeSignature
    tick_value: float
    

class StemRoutingHints(BaseModel):
    """Stem selection hints and resolved paths for chord/solo inference (Commit 111).

    Pre-routing fields (``chord_mix_stems``, ``melodic_preference_order``,
    ``selected_melodic_stem``) come from ``build_stem_routing_hints``.
    Post-routing fields (``resolved_chord_path``, ``resolved_solo_path``,
    ``resolved_chord_mix_keys``, ``fallback_reason``) are populated by the
    analysis pipeline after the hint-aware chord/solo routing block runs.
    """

    model_config = ConfigDict(extra="ignore")

    # Pre-routing hints from build_stem_routing_hints
    chord_mix_stems: list[str] = Field(default_factory=lambda: ["bass", "other"])
    melodic_preference_order: list[str] = Field(default_factory=list)
    selected_melodic_stem: str = "guitar"

    # Commit 111 — populated after routing is resolved
    resolved_chord_path: str | None = None
    resolved_solo_path: str | None = None
    resolved_chord_mix_keys: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None


class TranscriptionPrepareResponse(BaseModel):
    """`POST /transcription/prepare` payload (commit 78)."""

    model_config = ConfigDict(extra="ignore")

    job_id: str
    stems: dict[str, str] = Field(default_factory=dict)
    beat_grid: BeatGrid
    stem_routing: StemRoutingHints
    audio_chunk_paths: list[str] = Field(default_factory=list)
    invalidated_artifacts: list[str] = Field(default_factory=list)


# Commit 109: Beat grid recompute schemas
class BeatGridRecomputeRequest(BaseModel):
    """Request body for POST /analyze/{job_id}/beat-grid/recompute."""

    model_config = ConfigDict(extra="ignore")

    time_signature: str | None = Field(
        default=None,
        description="New time signature, e.g. '4/4', '6/8', '3/4'. Omit to keep current.",
    )
    bpm_override: float | None = Field(
        default=None,
        description="New BPM override. Omit to keep current (librosa-estimated).",
    )


class BeatGridRecomputeResponse(BaseModel):
    """Response from POST /analyze/{job_id}/beat-grid/recompute — job-like status for async recompute."""

    model_config = ConfigDict(extra="ignore")

    job_id: str
    status: Literal["pending", "recomputing_beats", "recomputing_chords", "recomputing_solo", "rebuilding_musicxml", "complete", "failed"] = "pending"
    beat_grid: BeatGrid | None = None
    chord_timeline: ChordTimeline | None = None
    solo_notes: SoloNotes | None = None
    musicxml: str | None = None
    bar_timestamps: list[float] = Field(default_factory=list)
    error: str | None = None
    progress: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Approximate progress 0–1 while recomputing.",
    )
    stage_label: str | None = Field(
        default=None,
        description="Short stage label while recomputing.",
    )


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


class SectionConfusionScore(BaseModel):
    """Commit 121: Per-section instrument confusion metric from dual-path divergence."""

    model_config = ConfigDict(extra="ignore")

    section_index: int
    label: str = ""
    start_time: float | None = None
    end_time: float | None = None
    instrument_confusion: float = Field(ge=0.0, le=1.0, default=0.0)
    is_high_confusion: bool = False
    beat_count: int = 0
    disagreement_count: int = 0


class LessonSectionStub(BaseModel):
    """One teachable slice of the song — expand per README LessonJSON.sections."""

    model_config = ConfigDict(extra="allow")

    label: str | None = None
    confidence: float | None = None
    # Start time in seconds for Listen step section chips (librosa segments).
    start_time_seconds: float | None = None
    # Commit 117: end time for section boundaries (computed from next section start)
    end_time_seconds: float | None = None
    # Commit 117: confidence in the label assignment (0-1)
    label_confidence: float | None = None
    # Commit 118: repetition-aware section grouping
    repeat_group_id: int | None = None
    is_repeated: bool | None = None
    repeat_count: int | None = None
    repeat_index: int | None = None
    # Transcription validation metadata (commit #82)
    transcription_metadata: dict[str, Any] | None = None
    # Commit 108: MusicXML score for this section (canonical render format)
    musicxml: str | None = None


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
    # Full chord timeline for bar chip rendering (section-scoped timelines are for section views)
    chord_timeline: ChordTimeline | None = None
    # Commit 108: MusicXML lead sheet string (canonical render format)
    musicxml: str | None = None
    # Commit 108: Structured solo notes at top level
    solo_notes: SoloNotes | None = None
    # Commit 108: Structured BeatGrid at top level (flat beat_grid preserved for backward compat)
    beat_grid_structured: BeatGrid | None = None
    # Commit 111: Embedded stem routing telemetry (which stems fed chord/solo inference)
    stem_routing: StemRoutingHints | None = None
    # Commit 112: Continuous stem quality confidence (0-1) and instrument confusion metric
    stem_confidence: float | None = None
    instrument_confusion: float | None = None
    # Commit 123: Solo harmony enrichment
    harmonized_solo: HarmonizedSoloNotes | None = None
    per_bar_analysis: list[BarScope] | None = None
    # Phase 2 Milestone A: MT3 transcription source indicator
    transcription_source: str | None = Field(
        default=None,
        description="Which pipeline tier produced this transcription: 'mt3', 'crnn', 'chroma', or None",
    )


class JobStatus(BaseModel):
    """Polling response for GET /analyze/{job_id}."""

    status: Literal["queued", "processing", "complete", "failed"] = "processing"
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
    # Commit 109: Progressive analysis stage for frontend partial rendering
    analysis_stage: str | None = Field(
        default=None,
        description="Machine-readable analysis stage: initializing, stems_separating, mt3_inferring, chords_inferring, solo_inferring, building_musicxml, complete.",
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


class ChordEnrichmentStatus(BaseModel):
    """GET /analyze/{job_id}/chord-enrichment status payload (commit 116)."""

    status: Literal["pending", "processing", "complete", "skipped"] = "pending"
    total_events: int = 0
    corrected_events: int = 0
    llm_latency_p50: float | None = None
    llm_latency_p95: float | None = None
    fallback_reason: str | None = None


class ScoreRequest(BaseModel):
    """POST /score request payload."""

    model_config = ConfigDict(extra="allow")

    recording_wav_base64: str
    recording_mime_type: str | None = None
    section: dict[str, Any] = Field(default_factory=dict)
    skill_nodes: list[str] = Field(default_factory=list)
    solo_notes: SoloNotes | None = Field(default=None, description="MIDI note events for timing reference (commit 83)")
    musical_tolerance_mode: MusicalToleranceMode = Field(
        default="technique",
        description="Musical tolerance mode for scoring: 'expressive' (lenient) or 'technique' (strict) (commit 92)",
    )
    stem_confidence: float | None = Field(
        default=None,
        description="Continuous stem quality confidence (0-1) from Commit 112 dual-path fusion.",
    )
    instrument_confusion: float | None = Field(
        default=None,
        description="Commit 121: Global instrument confusion (0-1) from dual-path divergence.",
    )


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
    stem_confidence: float | None = Field(
        default=None,
        description="Continuous stem quality confidence (0-1) from Commit 112.",
    )
    instrument_confusion: float | None = Field(
        default=None,
        description="Commit 121: Global instrument confusion (0-1) from dual-path divergence.",
    )


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
    # Commit B8: bass note & inversion detection
    bass: str | None = Field(
        default=None,
        description="Detected bass note root (e.g., 'E', 'G#'). None when bass = chord root or unknown.",
    )
    inversion: int | None = Field(
        default=None,
        description="Inversion: None=root, 1=first, 2=second, 3=third. None when unknown or root position.",
    )
    # Commit B9: voicing shape & fret position detection
    voicing_shape: str | None = Field(
        default=None,
        description="Detected CAGED voicing shape: 'E', 'A', 'C', 'D', 'G', or None if unknown",
    )
    voicing_position: int | None = Field(
        default=None,
        ge=0, le=24,
        description="Fret position of the voicing (0 = open, 1-12 = barre position). None when unknown.",
    )
    # Commit 116: LLM enrichment fields
    roman_numeral: str | None = Field(
        default=None,
        description="Roman numeral functional label (e.g., 'I', 'ii7', 'V7')",
    )
    llm_corrected_chord: str | None = Field(
        default=None,
        description="LLM-corrected chord symbol when confidence delta exceeds threshold",
    )
    correction_applied: bool = Field(
        default=False,
        description="Whether an LLM correction was applied to this event",
    )
    correction_delta: float | None = Field(
        default=None,
        description="Confidence delta between original and LLM-corrected chord",
    )

class ChordTimeline(BaseModel):
    events: list[ChordEvent]
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Commit 99: Viterbi decoding metrics (flicker rate, beat alignment, etc.)",
    )

class SoloNote(BaseModel):
    start_time: float = Field(..., description="Quantized start time in seconds")
    duration: float = Field(..., description="Quantized duration in seconds", ge=0)
    pitch: int = Field(..., description="MIDI pitch number (e.g., 60 for Middle C)")
    velocity: int = Field(..., ge=0, le=127)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Combined model + coherence confidence")
    technique: list[str] = Field(default_factory=list, description="Technique tags: 'bend', 'vibrato', 'grace_note'")
    is_tied: bool = Field(default=False, description="True if this note is tied from a previous segment")

class SoloNotes(BaseModel):
    notes: list[SoloNote]


# Commit 123 Schemas — Solo Harmony Enrichment

class ChordToneAnalysis(BaseModel):
    """Per-note harmonic analysis: what role does this pitch play in the current chord?"""

    scale_degree: int | None = Field(
        default=None,
        description="Diatonic scale degree (1-7) for chord tones/tensions; None for chromatic passing tones",
    )
    scale_degree_name: str = Field(
        ...,
        description='Human-readable label: "R", "b3", "3", "4", "b5", "5", "b7", "7", "#4", etc.',
    )
    chord_tone_type: Literal["chord_tone", "tension", "chromatic", "pedal"] = Field(
        ...,
        description="Harmonic role of this note in the current chord",
    )
    semitone_distance: int = Field(
        ...,
        ge=0,
        le=11,
        description="Absolute distance from chord root in semitones (0-11)",
    )


class HarmonizedSoloNote(BaseModel):
    """Solo note enriched with harmonic context from the active chord."""

    start_time: float = Field(..., description="Quantized start time in seconds")
    duration: float = Field(..., description="Quantized duration in seconds", ge=0)
    pitch: int = Field(..., description="MIDI pitch number")
    velocity: int = Field(..., ge=0, le=127)
    chord: str | None = Field(
        default=None,
        description="Active chord symbol at note onset (e.g., 'C:maj7'); None if no chord",
    )
    chord_analysis: ChordToneAnalysis | None = Field(
        default=None,
        description="Harmonic analysis of this note; None when chord is unavailable or 'N'",
    )


class HarmonizedSoloNotes(BaseModel):
    """Enriched solo note list with per-note chord context and aggregate percentages."""

    notes: list[HarmonizedSoloNote] = Field(default_factory=list)
    note_count: int = Field(default=0, description="Total solo notes (including those over 'N' chords)")
    chord_tone_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of harmonically analyzed notes that are chord tones",
    )
    tension_note_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of harmonically analyzed notes that are tensions",
    )
    chromatic_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of harmonically analyzed notes that are chromatic",
    )


class BarScope(BaseModel):
    """Per-bar analysis: dominant chord, suggested scales, CAGED position, and note indices."""

    bar_index: int = Field(..., description="Zero-based bar index")
    start_time: float = Field(..., description="Bar start time in seconds")
    end_time: float = Field(..., description="Bar end time in seconds")
    chord: str | None = Field(
        default=None,
        description="Dominant chord in this bar; None if no chord events fall in this bar",
    )
    suggested_scales: list[str] = Field(
        default_factory=list,
        description="Suggested scale names for improvisation over this bar",
    )
    primary_position: str | None = Field(
        default=None,
        description='Inferred CAGED position (e.g., "position 2 (CAGED: E-form)")',
    )
    notes: list[int] = Field(
        default_factory=list,
        description="Indices into HarmonizedSoloNotes.notes for notes in this bar",
    )


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

# Commit 91 Schemas

class DiscoveryRequest(BaseModel):
    """POST /discovery/recommendations — song discovery based on harmonic similarity (PRIORITIES §91)."""

    model_config = ConfigDict(extra="forbid")

    mastered_job_ids: list[str] = Field(default_factory=list, description="Job IDs of songs the user has mastered")
    library_lessons: list[LessonJSON] = Field(default_factory=list, description="All lessons from user's library (database)")
    skill_nodes: list[SkillNode] = Field(default_factory=list, description="User's skill progress data")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum number of recommendations")
    min_similarity: float = Field(default=0.3, ge=0.0, le=1.0, description="Minimum similarity score threshold")


class DiscoverySuggestionItem(BaseModel):
    """Single discovery suggestion item."""

    job_id: str
    song_title: str | None
    artist: str | None
    key: str | None
    style_label: str | None
    tempo: float | None
    reason_label: str
    similarity_score: float
    technique_focus: str


class DiscoveryResponse(BaseModel):
    """Response from POST /discovery/recommendations."""

    suggestions: list[DiscoverySuggestionItem] = Field(default_factory=list)


# Commit 110 Schemas — Correction endpoints (server-side correction API)

class ChordCorrectionRequest(BaseModel):
    """PATCH /analyze/{job_id}/chord/{beat_index} — correct a chord symbol."""

    model_config = ConfigDict(extra="forbid")

    chord: str = Field(..., min_length=1, max_length=20, description="New chord symbol (e.g. 'G7', 'F#m7')")
    reason: str | None = Field(default=None, max_length=200, description="Optional reason for correction")


class SoloNoteCorrectionRequest(BaseModel):
    """PATCH /analyze/{job_id}/solo-note/{note_index} — correct a solo note."""

    model_config = ConfigDict(extra="forbid")

    pitch: int | None = Field(default=None, ge=0, le=127, description="MIDI pitch override")
    start_time: float | None = Field(default=None, ge=0, description="Start time override in seconds")
    duration: float | None = Field(default=None, ge=0, description="Duration override in seconds")
    velocity: int | None = Field(default=None, ge=0, le=127, description="Velocity override")
    string: int | None = Field(default=None, ge=1, le=6, description="Guitar string override (1=high E)")
    fret: int | None = Field(default=None, ge=0, le=24, description="Fret position override")
    reason: str | None = Field(default=None, max_length=200, description="Optional reason for correction")


class VoicingOverrideRequest(BaseModel):
    """PATCH /analyze/{job_id}/chord/{beat_index}/voicing — override CAGED voicing shape."""

    model_config = ConfigDict(extra="forbid")

    voicing_shape: str = Field(..., description="CAGED shape label (E-shape, A-shape, C-shape, D-shape, G-shape)")
    reason: str | None = Field(default=None, max_length=200, description="Optional reason for override")


class CorrectionRecord(BaseModel):
    """One correction applied to analysis output."""

    model_config = ConfigDict(extra="ignore")

    correction_type: Literal["chord", "solo_note", "voicing"]
    index: int = Field(..., description="Index into the relevant array (beat_index or note_index)")
    original_value: dict[str, Any] = Field(default_factory=dict)
    corrected_value: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    applied_at: str = Field(default="", description="ISO timestamp of correction")


class CorrectionHistory(BaseModel):
    """Correction history for a job."""

    job_id: str
    corrections: list[CorrectionRecord] = Field(default_factory=list)
    correction_count: int = 0
    correction_coverage: float = Field(default=0.0, ge=0.0, le=1.0, description="Fraction of ML-predicted events corrected")


class CorrectionRevertRequest(BaseModel):
    """POST /analyze/{job_id}/corrections/revert — revert a specific correction."""

    model_config = ConfigDict(extra="forbid")

    correction_index: int = Field(..., ge=0, description="Index into the corrections list to revert")


class CorrectionExportRequest(BaseModel):
    """POST /analyze/{job_id}/corrections/export — export corrections as training data."""

    model_config = ConfigDict(extra="forbid")

    include_solo_notes: bool = Field(default=True, description="Include solo note corrections")
    include_voicings: bool = Field(default=False, description="Include voicing overrides")
    format: Literal["json", "csv"] = Field(default="json", description="Export format")


# ---------------------------------------------------------------------------
# Commit 111: Jam Mode Summary Agent
# ---------------------------------------------------------------------------


class JamPhraseMetrics(BaseModel):
    """Per-phrase deterministic metrics extracted on-device."""

    model_config = ConfigDict(extra="forbid")

    duration_ms: float = Field(..., ge=0, description="Phrase duration in milliseconds")
    notes_per_second: float = Field(..., ge=0, description="Note density")
    unique_pitch_classes: int = Field(..., ge=0, le=12, description="Number of distinct pitch classes (0-11)")
    midi_span: int = Field(..., ge=0, description="MIDI range span (max - min pitch)")
    contour: Literal["rising", "falling", "arch", "static", "mixed"] = Field(
        default="mixed", description="Melodic contour shape"
    )
    beat_offset_mean: float = Field(default=0.0, description="Mean offset from beat grid (0=on-beat, 0.5=off-beat)")
    beat_offset_std: float = Field(default=0.0, ge=0, description="Std deviation of beat offset (rhythmic consistency)")
    home_pitch_class: str | None = Field(default=None, description="Most frequent pitch class in phrase (e.g. 'A', 'E')")
    transition_from: str | None = Field(default=None, description="Previous chord/scale context")
    transition_gap_ms: float = Field(default=0.0, ge=0, description="Silence gap before this phrase (ms)")


class JamVocabularyPattern(BaseModel):
    """Detected recurring vocabulary pattern across phrases."""

    model_config = ConfigDict(extra="forbid")

    pattern_id: str = Field(..., description="Unique pattern identifier (e.g. 'vocab_001')")
    pattern_type: Literal["motif", "sequence", "arpeggio", "scale_run", "bend_figure", "repeated_note"] = Field(
        ..., description="Category of detected pattern"
    )
    pitch_classes: list[str] = Field(..., description="Pitch classes in the pattern (e.g. ['A', 'C', 'E'])")
    occurrence_count: int = Field(..., ge=2, description="Number of times this pattern appeared")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence")
    description: str = Field(default="", description="Human-readable description of the pattern")


class JamSummaryBundle(BaseModel):
    """Model-to-coach JSON bundle — deterministic metrics + Claude-generated coaching."""

    model_config = ConfigDict(extra="forbid")

    # Deterministic metrics (computed on-device or server-side, no LLM)
    chord: str | None = Field(default=None, description="Detected chord/scale context (e.g. 'G:maj7')")
    clarity: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall playing clarity (0-1)")
    intonation_cents: dict[str, float] = Field(
        default_factory=dict, description="Per-string intonation offset in cents (e.g. {'B2': -8, 'high_E': +14})"
    )
    timing_ms: float = Field(default=0.0, description="Average timing offset from beat grid in milliseconds")
    transition_from: str | None = Field(default=None, description="Previous chord/scale context")
    transition_gap_ms: float = Field(default=0.0, ge=0, description="Gap before first phrase (ms)")

    # Phrase-level metrics
    phrase_count: int = Field(default=0, ge=0, description="Number of detected phrases")
    total_notes: int = Field(default=0, ge=0, description="Total note count")
    avg_notes_per_second: float = Field(default=0.0, ge=0, description="Average note density")
    dominant_contour: Literal["rising", "falling", "arch", "static", "mixed"] = Field(
        default="mixed", description="Most common melodic contour"
    )
    pitch_class_distribution: dict[str, float] = Field(
        default_factory=dict, description="Normalized pitch class weights (pc_C..pc_B)"
    )

    # Vocabulary patterns
    vocabulary_patterns: list[JamVocabularyPattern] = Field(
        default_factory=list, description="Detected recurring patterns"
    )
    vocabulary_diversity: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Vocabulary diversity score (0=repetitive, 1=varied)"
    )

    # Claude-generated coaching (the LLM output)
    coach_summary: str = Field(default="", description="1-3 sentence overall summary")
    coach_strengths: list[str] = Field(default_factory=list, description="What went well")
    coach_focus_areas: list[str] = Field(default_factory=list, description="Areas to work on")
    coach_next_step: str = Field(default="", description="Specific next practice suggestion")

    # Metadata
    persona: Literal["learner", "intermediate", "transcriber"] = Field(
        default="intermediate", description="Coaching persona used"
    )
    duration_seconds: int = Field(default=0, ge=0, description="Total jam duration")
    inferred_scale_label: str | None = Field(default=None, description="Detected scale")
    inference_confidence: Literal["low", "medium", "high"] | None = Field(default=None)


class JamSummaryRequest(BaseModel):
    """POST /jam/summary — Claude-powered post-jam analysis."""

    model_config = ConfigDict(extra="forbid")

    # Core jam data
    duration_seconds: int = Field(..., ge=0)
    pitch_class_weight_map: dict[str, float] = Field(default_factory=dict)
    inferred_scale_label: str | None = None
    inference_confidence: Literal["low", "medium", "high"] | None = None
    track_id: str | None = None
    track_label: str | None = None
    track_key: str | None = None
    track_bpm: int | None = None

    # Phrase-level data (persisted from device)
    phrases: list[JamPhraseMetrics] = Field(default_factory=list, description="Per-phrase metrics from device")

    # Player context for persona selection
    player_level: Literal["beginner", "intermediate", "advanced"] = Field(
        default="intermediate", description="Player skill level for persona selection"
    )
    persona: Literal["learner", "intermediate", "transcriber"] | None = Field(
        default=None, description="Explicit persona override (auto-detected from player_level if null)"
    )

    # Optional session context
    previous_jam_count: int = Field(default=0, ge=0, description="Number of previous jam sessions")
    weak_areas: list[str] = Field(default_factory=list, description="Known weak areas from skill tracking")


class JamSummaryResponse(BaseModel):
    """Response from POST /jam/summary."""

    bundle: JamSummaryBundle
    coach_summary: str = Field(default="", description="Legacy alias for bundle.coach_summary")


class ContributeRequest(BaseModel):
    """POST /analyze/{job_id}/contribute — contribute corrected audio to training."""

    contributor_id: str = Field(
        ...,
        description="Anonymous contributor identifier (client-generated UUID)",
        min_length=1,
        max_length=128,
    )
    license: str = Field(
        default="cc-by-4.0",
        description="License for the contributed recording",
    )


class ContributeResponse(BaseModel):
    """POST /analyze/{job_id}/contribute — contribution accepted."""

    status: str = Field(default="accepted")
    windows: int = Field(..., description="Number of CQT windows extracted")
    track_id: str = Field(..., description="Stored track identifier")


class SpotifySearchResult(BaseModel):
    """Raw GET /search response — pass-through from Spotify (no PII)."""

    model_config = ConfigDict(extra="ignore")

    tracks: dict[str, Any] | None = None
    artists: dict[str, Any] | None = None
    albums: dict[str, Any] | None = None
    playlists: dict[str, Any] | None = None
    shows: dict[str, Any] | None = None
    episodes: dict[str, Any] | None = None
    audiobooks: dict[str, Any] | None = None


class SpotifyRecommendationsResult(BaseModel):
    """Raw GET /recommendations response — pass-through from Spotify."""

    model_config = ConfigDict(extra="ignore")

    tracks: list[dict[str, Any]] = Field(default_factory=list)
    seeds: list[dict[str, Any]] = Field(default_factory=list)


class SpotifyAvailableGenreSeeds(BaseModel):
    """GET /recommendations/available-genre-seeds response."""

    model_config = ConfigDict(extra="ignore")

    genres: list[str] = Field(default_factory=list)


class SpotifyPlaylistList(BaseModel):
    """GET /me/playlists response — pass-through from Spotify."""

    model_config = ConfigDict(extra="ignore")

    href: str = ""
    limit: int = 0
    next: str | None = None
    offset: int = 0
    previous: str | None = None
    total: int = 0
    items: list[dict[str, Any]] = Field(default_factory=list)


class SpotifyPlaylistDetail(BaseModel):
    """GET /playlists/{playlist_id} response — pass-through from Spotify."""

    model_config = ConfigDict(extra="ignore")

    collaborative: bool = False
    description: str | None = None
    external_urls: dict[str, str] = Field(default_factory=dict)
    href: str = ""
    id: str = ""
    images: list[dict[str, Any]] = Field(default_factory=list)
    name: str = ""
    owner: dict[str, Any] = Field(default_factory=dict)
    public: bool | None = None
    snapshot_id: str = ""
    tracks: dict[str, Any] = Field(default_factory=dict)
    type: str = "playlist"
    uri: str = ""


class SpotifyPlaylistItems(BaseModel):
    """GET /playlists/{playlist_id}/items response — pass-through from Spotify."""

    model_config = ConfigDict(extra="ignore")

    href: str = ""
    limit: int = 0
    next: str | None = None
    offset: int = 0
    previous: str | None = None
    total: int = 0
    items: list[dict[str, Any]] = Field(default_factory=list)