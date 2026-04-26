/** Shared domain types — expanded in later commits; shapes match DESIGN_SYSTEM.md / backend schemas. */

export type AnalyzeJobStatus = 'queued' | 'processing' | 'complete' | 'failed'

/** Lesson payload from GET /analyze/{job_id} when status is complete — matches `backend/app/schemas.py` with extras allowed. */
/** Optional payload for POST /analyze — matches `backend/app/schemas.py` `PlayerProfile`. */
/** User-declared tier + optional focus notes — merged into POST `/analyze` and coach context. */
export interface LearningContextPayload {
  experience_level?: 'beginner' | 'intermediate' | 'advanced'
  /** Mirrors Settings “Style focus” for coach conditioning. */
  solo_focus_notes?: string
}

export interface PlayerProfilePayload {
  weak_areas?: string[]
  skill_nodes?: Array<{ id: string; label?: string | null; score?: number }>
  taste_profile?: TasteProfilePayload
  learning_context?: LearningContextPayload
  focus_area?: 'timing' | 'vibrato' | 'dynamics' | 'phrasing' | 'bending' | 'rhythm' | 'expression'
}

export interface CurriculumSuggestion {
  job_id: string
  reason_label: string
  technique_focus: string
}

export interface CurriculumSuggestResponse {
  ranked: CurriculumSuggestion[]
}

/** POST /practice/plan (commit 70). */
export type PracticeSlotType = 'warmup' | 'technique' | 'song_section' | 'free_jam'
export type MoodState = 'focused' | 'loose' | 'tired' | 'on_fire'

/** Matches `FretboardGuideCell` / pool `fretboard_guide.cells` (tab string 1 = high E). */
export type WarmupFretboardGuideVariant = 'primary' | 'secondary'

export interface WarmupFretboardGuideCellPayload {
  string: number
  fret: number
  variant: WarmupFretboardGuideVariant
}

/** Curriculum-authored fretboard highlights (pool → POST /practice/plan). */
export interface WarmupFretboardGuidePayload {
  cells: WarmupFretboardGuideCellPayload[]
  caption?: string | null
}

/** Commit 73 — nested warm-up steps on the first drill slot. */
export interface WarmupExercisePayload {
  name: string
  description: string
  duration_seconds: number
  tab_snippet_gp5_base64?: string | null
  technique_tag: string
  bpm: number
  fretboard_guide?: WarmupFretboardGuidePayload | null
}

export interface WarmupPlanPayload {
  exercises: WarmupExercisePayload[]
  total_duration_seconds: number
}

export interface DrillSlotPayload {
  slot_type: PracticeSlotType
  duration_seconds: number
  title: string
  coach_intro: string
  lesson_ref?: string | null
  exercise_ref?: string | null
  technique_focus?: string | null
  warmup_plan?: WarmupPlanPayload | null
}

export interface PracticePlanPayload {
  slots: DrillSlotPayload[]
  total_duration_seconds: number
}

/** GET /taste/spotify — commit 67 (no tokens). */
export interface SpotifyTasteProfile {
  top_genres: string[]
  top_artists: string[]
  energy_avg: number
  tempo_avg: number
  instrumentalness_avg: number
}

/** GET /spotify/playback — commit 77. */
export interface SpotifyPlaybackStatePayload {
  is_playing: boolean
  progress_ms: number
  playback_rate: number
  track_id?: string | null
  track_name?: string | null
  artists: string[]
}

/** POST /taste/derive response — commit 68. */
export interface TasteProfilePayload {
  style_label: string
  technique_affinity: string[]
  bpm_comfort_range: [number, number]
  song_candidates: string[]
  source: 'spotify' | 'quiz' | 'manual'
}

/** POST /taste/derive quiz branch — commit 68 / 69. */
export interface QuizAnswersPayload {
  selected_artists: string[]
  selected_style: string
  experience_level: 'beginner' | 'intermediate' | 'advanced'
}

export interface CoachHydrationSectionPayload {
  index: number
  coach_note: string
  coach_explanation: string
}

export interface CoachHydrationStatusPayload {
  status: 'pending' | 'complete' | 'fallback'
  sections: CoachHydrationSectionPayload[]
  fallback_reason?: string | null
}

export interface BeatGrid {
  bpm: number
  pulse_bpm: number
  beats: number[]
  downbeats: number[]
  time_signature: { numerator: number; denominator: number }
  tick_value: number
}

export interface ChordEvent {
  timestamp: number
  chord: string
  confidence: number
}

export interface ChordTimeline {
  events: ChordEvent[]
}

export interface SoloNote {
  start_time: number
  duration: number
  pitch: number
  velocity: number
}

export interface SoloNotes {
  notes: SoloNote[]
}

export interface LessonSection {
  label?: string | null
  confidence?: number | null
  start_time_seconds?: number | null
  transcription_metadata?: Record<string, unknown> | null
  beat_grid?: BeatGrid | null
  chord_timeline?: ChordTimeline | null
  solo_notes?: SoloNotes | null
  tab_full_gp5_base64?: string | null
  tab_skeleton_gp5_base64?: string | null
  tab_alt_position_gp5_base64?: string | null
  coach_note?: string | null
  coach_explanation?: string | null
  [key: string]: unknown
}

export interface LessonJSON {
  job_id?: string | null
  song_title?: string | null
  artist?: string | null
  style_label?: string | null
  key?: string | null
  key_confidence?: number | null
  tempo?: number | null
  tempo_confidence?: number | null
  transcription_confidence?: number | null
  beat_grid?: number[]
  /** Positive: delay metronome vs stems (seconds). Optional backend / manual calibration. */
  beat_align_offset_sec?: number | null
  bar_timestamps?: number[]
  /** Chord timeline from transcription analysis - may be at lesson level or section level. */
  chord_timeline?: { events: Array<{ timestamp: number; chord: string; confidence: number }> } | null
  /** Solo notes from transcription analysis - may be at lesson level or section level. */
  solo_notes?: { notes: Array<{ start_time: number; duration: number; pitch: number; velocity?: number }> } | null
  stems?: Record<string, string>
  lyrics_aligned?: Array<Record<string, unknown>>
  sections?: LessonSection[]
  /** Backend stem isolation heuristic — guitar bleed / piano-led mix (`backend/app/stem_quality.py`). */
  stem_isolation_warning?: string | null
  stem_quality_flags?: string[]
  guitar_stem_usable?: boolean | null
  /** `guitar_stem` | `full_mix` | `piano_stem` — which source librosa used for tempo/beat structure. */
  analysis_audio_role?: string | null
  /** e.g. `no_isolated_guitar` when Basic Pitch was skipped. */
  tabs_unavailable_reason?: string | null
  /** Optional AlphaTab SVG prerender hints — see `backend/app/alphatab_prerender.py`. */
  alphatab_prerender_hints?: {
    alphatab_version?: string
    preset_version?: string
    score_sha256?: string
    cache_key?: string
    master_bar_count?: number
    total_width?: number
    total_height?: number
    partial_count?: number
    artifact_rel?: string | null
  } | null
}

export interface AnalyzeJob {
  status: AnalyzeJobStatus
  result: LessonJSON | null
  error: string | null
  /** Present when status is failed; stable code for `mapAnalyzeFlowError`. */
  error_code?: string | null
  /** 0–1 while processing; from GET /analyze/{id} when backend reports it. */
  progress?: number | null
  stage_label?: string | null
  /** Unix seconds when processing began (server); optional for older backends. */
  processing_started_at?: number | null
}

/** POST /score response — see README.md */
export interface ScoreResult {
  pitch_accuracy: number
  note_duration_deltas: number[]
  phrasing_score: number
  bend_pitch_error_cents: number
  rushing_score: number
  /** Short coaching paragraph from POST `/score` when the backend provides it. */
  coach_paragraph?: string | null
  node_scores: Record<string, number>
  waveform_comparison: {
    user_wav_base64: string
    reference_wav_base64: string
  }
  diagnostics?: {
    signal_quality: number
    voiced_ratio: number
    harmonic_ratio: number
    timing_residual_p50_ms: number
    timing_residual_p95_ms: number
    reliability_flags: string[]
  }
  reliability?: {
    score_contract_version: string
    confidence: 'low' | 'medium' | 'high'
    signal_quality: number
    reliability_flags: string[]
  }
}

/** POST /jam-score response */
export interface JamResult {
  coach_summary: string
  /** Legacy alias during migration. */
  scale_position_map: Record<string, number>
  pitch_class_weight_map: Record<string, number>
  position_weight_map: Record<string, number>
  inferred_scale_label?: string | null
  inference_confidence?: 'low' | 'medium' | 'high' | null
  focus_pitch_class_key?: string | null
  focus_pitch_class_weight?: number | null
  reliability_tags?: string[]
  reliability?: {
    score_contract_version: string
    confidence: 'low' | 'medium' | 'high'
    signal_quality: number
    reliability_flags: string[]
  }
}

export interface Annotation {
  bar: number
  text: string
}

export interface SkillNode {
  id: string
  label: string
  score: number
  sessions_count: number
  last_session_date: string
  easiness_factor: number
  interval_days: number
  next_review_date: string
}

export interface Lick {
  id: string
  song_title: string
  artist: string
  key: string
}

/** Discovery agent suggestions (commit 91). */
export interface DiscoverySuggestion {
  job_id: string
  song_title: string | null
  artist: string | null
  key: string | null
  style_label: string | null
  tempo: number | null
  reasonLabel: string
  similarityScore: number
  techniqueFocus: string
}

/** Discovery request payload (commit 91). */
export interface DiscoveryRequest {
  mastered_job_ids: string[]
  library_lessons?: LessonJSON[]
  skill_nodes?: Array<{ id: string; label?: string | null; score?: number }>
  limit?: number
  min_similarity?: number
}

/** Discovery response (commit 91). */
export interface DiscoveryResponse {
  suggestions: DiscoverySuggestion[]
}

/** Musical tolerance mode for scoring (commit 92). */
export type MusicalToleranceMode = 'expressive' | 'technique'
