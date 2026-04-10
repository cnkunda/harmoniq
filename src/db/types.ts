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
}

export type ReviewSkillUpdateInput = {
  node_scores: Record<string, number>
  targeted_node_ids: string[]
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
  scale_position_map: Record<string, number>
  recurring_gestures: string[]
  coach_summary: string
}

export type JamSnapshotInsertInput = {
  id: string
  date: string
  duration_seconds: number
  scale_position_map: Record<string, number>
  recurring_gestures: string[]
  coach_summary: string
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
  coach_oneliner: string | null
  technique_tags: string[]
  user_annotations: Array<{ bar: number; text: string }>
  date_saved: string
}
