import { ApiError, parseFastApiDetail } from '@/src/api/analyze'
import { API_BASE_URL } from '@/src/config'

export type MentorMode = 'single' | 'plan'
export type MentorConfidence = 'low' | 'medium' | 'high'

export interface MentorHistorySummary {
  days: number
  session_count: number
  jam_count: number
  plan_count: number
  correction_count: number
  confidence: MentorConfidence
}

export interface MentorAccuracyPoint {
  date: string
  accuracy: number
}

export interface MentorSkillDelta {
  id: string
  label: string
  prior: number
  recent: number
  delta: number
}

export interface MentorWeakNode {
  id: string
  label: string
  score: number
}

export interface MentorGoalContext {
  experience_level?: string | null
  style_focus?: string | null
  style_label?: string | null
  technique_affinity: string[]
  song_candidates: string[]
}

export interface MentorDnaSummary {
  timing_feel: string
  top_pitch_classes: string[]
  top_positions: string[]
  technique_frequency: Record<string, number>
}

export interface MentorCorrectionSummary {
  total: number
  by_type: Record<string, number>
  most_corrected_chords: Array<{ chord: string; count: number }>
}

export interface MentorPlanSummary {
  slot_count: number
  slot_types: string[]
  target_skills: string[]
  remediation_count: number
  skip_count: number
  avg_slot_accuracy?: number | null
}

export interface MentorLibrarySong {
  job_id: string
  title: string
  artist?: string | null
  style_label?: string | null
  tempo?: number | null
  techniques: string[]
}

export interface MentorTrajectoryRequest {
  mode: MentorMode
  generated_at: string
  history: MentorHistorySummary
  accuracy_points: MentorAccuracyPoint[]
  skill_deltas: MentorSkillDelta[]
  weak_nodes: MentorWeakNode[]
  goals: MentorGoalContext
  dna: MentorDnaSummary
  corrections: MentorCorrectionSummary
  plan: MentorPlanSummary | null
  library_songs: MentorLibrarySong[]
  taste_song_candidates: string[]
}

export interface MentorNextMonthItem {
  title: string
  why: string
  skill_focus: string
  mode: MentorMode
}

export interface MentorSongSuggestion {
  title: string
  artist?: string | null
  reason: string
  source: 'library' | 'taste'
}

export interface MentorNote {
  headline: string
  trajectory_summary: string
  confidence: MentorConfidence
  plateau_diagnosis?: string | null
  next_month: MentorNextMonthItem[]
  next_songs: MentorSongSuggestion[]
  plan_guidance?: string | null
  generated_at: string
  model: string
}

interface MentorTrajectoryResponse {
  note: MentorNote
}

const MENTOR_REQUEST_TIMEOUT_MS = 45_000

/** Commit 179: ask the backend mentor for a note based on the compact local trajectory. */
export async function requestMentorNote(payload: MentorTrajectoryRequest): Promise<MentorNote> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), MENTOR_REQUEST_TIMEOUT_MS)
  try {
    const res = await fetch(`${API_BASE_URL}/mentor/trajectory`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new ApiError(res.status, parseFastApiDetail(text) || text || res.statusText)
    }
    const body = (await res.json()) as MentorTrajectoryResponse
    if (!body?.note?.headline) {
      throw new Error('Mentor returned an empty note.')
    }
    return body.note
  } catch (e) {
    if (e instanceof ApiError) throw e
    const name = e instanceof Error ? e.name : ''
    const message = e instanceof Error ? e.message : String(e)
    if (name === 'AbortError' || message.toLowerCase().includes('aborted')) {
      throw new ApiError(408, 'Mentor request timed out. Check your connection and try again.')
    }
    throw e
  } finally {
    clearTimeout(timeoutId)
  }
}
