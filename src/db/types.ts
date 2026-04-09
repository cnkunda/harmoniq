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
