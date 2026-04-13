/** Shared domain types — expanded in later commits; shapes match DESIGN_SYSTEM.md / backend schemas. */

export type AnalyzeJobStatus = 'processing' | 'complete' | 'failed'

/** Lesson payload from GET /analyze/{job_id} when status is complete — matches `backend/app/schemas.py` with extras allowed. */
/** Optional payload for POST /analyze — matches `backend/app/schemas.py` `PlayerProfile`. */
export interface PlayerProfilePayload {
  weak_areas?: string[]
  skill_nodes?: Array<{ id: string; label?: string | null; score?: number | null }>
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
  stems?: Record<string, string>
  lyrics_aligned?: Array<Record<string, unknown>>
  sections?: Array<Record<string, unknown>>
}

export interface AnalyzeJob {
  status: AnalyzeJobStatus
  result: LessonJSON | null
  error: string | null
  /** 0–1 while processing; from GET /analyze/{id} when backend reports it. */
  progress?: number | null
  stage_label?: string | null
}

/** POST /score response — see README.md */
export interface ScoreResult {
  pitch_accuracy: number
  note_duration_deltas: number[]
  phrasing_score: number
  bend_pitch_error_cents: number
  rushing_score: number
  node_scores: Record<string, number>
  waveform_comparison: {
    user_wav_base64: string
    reference_wav_base64: string
  }
}

/** POST /jam-score response */
export interface JamResult {
  coach_summary: string
  scale_position_map: Record<string, number>
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
  scale: string
  position: string
  tab_gp5_base64: string
  audio_segment_path?: string
  coach_oneliner: string
  technique_tags: string[]
  user_annotations: Annotation[]
  date_saved: string
}
