export type SessionInsertInput = {
  id: string
  song_title: string | null
  artist: string | null
  section_label: string | null
  date: string
  coach_review: string | null
  pitch_accuracy: number | null
  phrasing_score: number | null
  nodes_targeted: string[]
  /** JSON string of `ScoreResult` for replay on Progress / archive Review. */
  review_snapshot?: string | null
  /** Optional file URIs when waveforms are stored on disk instead of snapshot. */
  waveform_user_path?: string | null
  waveform_ref_path?: string | null
  /** Commit 75: lesson identity for ghost lookup. */
  job_id?: string | null
  section_index?: number | null
  /** Commit 75: this row’s user take is the ghost reference for the section. */
  is_ghost_reference?: boolean
  /** Commit 75: song timeline position (seconds) when that take’s recording started. */
  ghost_anchor_sec?: number | null
  /** Commit 75: inline audio when file URI is unavailable (web). */
  ghost_audio_base64?: string | null
  /** Commit 75: e.g. `audio/webm` / `audio/m4a` for decoders. */
  ghost_recording_mime?: string | null
  /** Commit 76: pre-session self-reported mood. */
  mood?: 'focused' | 'loose' | 'tired' | 'on_fire' | null
}

/** Session row for journal list (newest first). */
export type SessionJournalRow = {
  id: string
  song_title: string | null
  artist: string | null
  section_label: string | null
  date: string
  coach_review: string | null
  pitch_accuracy: number | null
  phrasing_score: number | null
  nodes_targeted: string[]
  has_review_snapshot: boolean
  waveform_user_path: string | null
  waveform_ref_path: string | null
  job_id?: string | null
  section_index?: number | null
  is_ghost_reference?: boolean
  ghost_anchor_sec?: number | null
  ghost_audio_base64?: string | null
  ghost_recording_mime?: string | null
  mood?: 'focused' | 'loose' | 'tired' | 'on_fire' | null
  /** Review session length in minutes when recorded (optional; not yet persisted on all paths). */
  duration_min?: number | null
}

/** Commit 75: latest ghost reference row for Play / Review. */
export type GhostReferenceRow = {
  id: string
  date: string
  waveform_user_path: string | null
  ghost_anchor_sec: number | null
  ghost_audio_base64: string | null
  ghost_recording_mime: string | null
}

export type SessionArchiveRow = SessionJournalRow & {
  review_snapshot: string | null
}

/** Latest session row that targeted a skill node (for Progress node detail). */
export type NodeSessionSnippet = {
  coach_review: string | null
  date: string
  pitch_accuracy: number | null
  phrasing_score: number | null
}

/** Row shape for `skill_nodes` (native SQLite + web mirror). */
export type SkillNodeRow = {
  id: string
  label: string | null
  score: number
  sessions_count: number
  last_session_date: string | null
  easiness_factor: number
  interval_days: number
  next_review_date: string | null
  sm2_repetitions: number
  /** JSON array (max 3) of raw session accuracy samples for technique mutation rolling weak-area (commit 63). */
  technique_roll_json?: string | null
  /** Schema version for tracking skill_nodes structure changes (commit 88). */
  schema_version?: number
}

/** Persisted slice after pure skill mutation reducer (commit 63). */
export type SkillSessionMutationRow = {
  id: string
  score: number
  technique_roll_json: string | null
}

export type ReviewSkillUpdateInput = {
  node_scores: Record<string, number>
  targeted_node_ids: string[]
  node_confidence_map?: Partial<Record<string, 'low' | 'medium' | 'high'>>
  node_reliability_map?: Partial<Record<string, number>>
  reliability_flags?: string[]
  /** Session-level pitch / accuracy (0–1) for SM-2 multisignal composite. */
  session_accuracy01?: number
  /** Session-level timing stability (0–1); from rushing_score + diagnostics. */
  session_timing_stability01?: number
}

/** Latest persisted session that includes a song title (library proxy). */
export type LatestSessionSongRow = {
  song_title: string
  artist: string | null
  section_label: string | null
  date: string
}

/** Home suggestion card: cold start vs SM-2 + last song (PRIORITIES §31). */
export type HomeSuggestion =
  | { kind: 'cold_start' }
  | { kind: 'active_lesson'; song: LatestSessionSongRow }
  | {
      kind: 'library_saved'
      lickCount: number
      latest: {
        id: string
        song_title: string | null
        artist: string | null
        position: string | null
        coach_oneliner: string | null
        date_saved: string
      }
    }
  | { kind: 'ready'; node: SkillNodeRow; song: LatestSessionSongRow }

export type LickInsertInput = {
  id: string
  song_title: string | null
  artist: string | null
  key: string | null
  scale: string | null
  position: string | null
  tab_gp5_base64: string
  audio_segment_path: string | null
  /** JSON.stringify(Record<string, string>) of non-empty stem rel paths from the lesson. */
  stems_json: string | null
  coach_oneliner: string | null
  technique_tags: string[]
  user_annotations: Array<{ bar: number; text: string }>
  date_saved: string
}

/** Row from `jam_snapshots` for export / listing. */
export type JamSnapshotRow = {
  id: string
  date: string
  duration_seconds: number
  /** Legacy alias; kept for backward compatibility during migration. */
  scale_position_map: Record<string, number>
  /** Canonical weighted usage map for pitch classes (`pc_C`..`pc_B`). */
  pitch_class_weight_map: Record<string, number>
  /** Optional future map for physical fretboard positions. */
  position_weight_map: Record<string, number>
  inferred_scale_label: string | null
  inference_confidence: 'low' | 'medium' | 'high' | null
  track_id: string | null
  track_label: string | null
  track_key: string | null
  track_bpm: number | null
  reliability_tags: string[]
  reliability_confidence: 'low' | 'medium' | 'high' | null
  reliability_signal_quality: number | null
  recurring_gestures: string[]
  coach_summary: string
  /** Serialized JamSummaryBundle from POST /jam/summary (commit 111). */
  summary_bundle_json: string | null
  /** Serialized JamPhraseMetrics[] captured during the jam session. */
  phrases_json: string | null
}

/** Row when the user finishes a practice plan from Jam (final step). */
export type PracticePlanCompletionRow = {
  id: string
  completed_at: string
  /** Serialized `PracticePlanPayload`. */
  plan_json: string
}

export type PracticePlanCompletionInsertInput = {
  id: string
  completed_at: string
  plan_json: string
}

export type JamSnapshotInsertInput = {
  id: string
  date: string
  duration_seconds: number
  /** Legacy alias; mirrored from `pitch_class_weight_map` while old exports migrate. */
  scale_position_map: Record<string, number>
  pitch_class_weight_map: Record<string, number>
  position_weight_map?: Record<string, number> | null
  inferred_scale_label?: string | null
  inference_confidence?: 'low' | 'medium' | 'high' | null
  track_id?: string | null
  track_label?: string | null
  track_key?: string | null
  track_bpm?: number | null
  reliability_tags?: string[] | null
  reliability_confidence?: 'low' | 'medium' | 'high' | null
  reliability_signal_quality?: number | null
  recurring_gestures: string[]
  coach_summary: string
  /** Serialized JamSummaryBundle from POST /jam/summary (commit 111). */
  summary_bundle_json?: string | null
  /** Serialized JamPhraseMetrics[] captured during the jam session. */
  phrases_json?: string | null
}

export type LickRow = {
  id: string
  song_title: string | null
  artist: string | null
  key: string | null
  scale: string | null
  position: string | null
  tab_gp5_base64: string
  audio_segment_path: string | null
  stems_json: string | null
  coach_oneliner: string | null
  technique_tags: string[]
  user_annotations: Array<{ bar: number; text: string }>
  date_saved: string
}

/** Library list row for analyzed full songs (metadata only). */
export type LessonListRow = {
  job_id: string
  song_title: string | null
  artist: string | null
  analyzed_at: string
  section_count: number
}

/** SQLite / IndexedDB row including serialized `LessonJSON`. */
export type LessonPersistRow = LessonListRow & {
  lesson_json: string
}
