import type {
  MentorConfidence,
  MentorDnaSummary,
  MentorHistorySummary,
  MentorLibrarySong,
  MentorMode,
  MentorPlanSummary,
  MentorSkillDelta,
  MentorTrajectoryRequest,
  MentorWeakNode,
} from '@/src/api/mentor'
import type {
  JamSnapshotRow,
  PracticePlanCompletionRow,
  PracticePlanRow,
  SessionArchiveRow,
  SkillNodeRow,
  UserFeedbackRow,
} from '@/src/db/types'
import { DEFAULT_SKILL_NODES } from '@/src/db/schema'
import { sessionOverallAccuracy } from '@/src/home/sessionAccuracy'
import { CHROMATIC_NOTE_NAMES } from '@/src/music/noteNames'
import type { PlayerDNA } from '@/src/music/dnaComputer'
import type { LearningContextPayload, TasteProfilePayload } from '@/src/types'
import { parseScoreSnapshot } from '@/src/utils/parseScoreSnapshot'

const DAY_MS = 24 * 60 * 60 * 1000

export const MENTOR_MIN_HISTORY_DAYS = 30
export const MENTOR_WINDOW_DAYS = 90
export const MENTOR_MAX_ACCURACY_POINTS = 30
export const MENTOR_REFRESH_DAYS = 30
export const MENTOR_RETRY_THROTTLE_MS = 6 * 60 * 60 * 1000

export interface MentorTrajectoryInput {
  mode: MentorMode
  now?: Date
  sessions: readonly SessionArchiveRow[]
  jams: readonly JamSnapshotRow[]
  completions: readonly PracticePlanCompletionRow[]
  activePlan: PracticePlanRow | null
  skillNodes: readonly SkillNodeRow[]
  feedback: readonly UserFeedbackRow[]
  dna: PlayerDNA | null
  taste: TasteProfilePayload | null
  learningContext: LearningContextPayload | null
  librarySongs: readonly MentorLibrarySong[]
  tasteSongCandidates: readonly string[]
}

export interface MentorTrajectoryBuildResult {
  eligible: boolean
  historyDays: number
  evidenceCount: number
  payload: MentorTrajectoryRequest
}

function parseDateMs(value: string | null | undefined): number | null {
  if (!value) return null
  const parsed = new Date(value).getTime()
  return Number.isNaN(parsed) ? null : parsed
}

function mean(values: readonly number[]): number {
  if (values.length === 0) return 0
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(1, value))
}

function skillLabel(id: string): string {
  const known = DEFAULT_SKILL_NODES.find((node) => node.id === id)
  if (known) return known.label
  return id
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

function buildPlanSummary(
  planRaw: string | null | undefined,
  adaptationRaw: string | null | undefined,
  resultRaw: string | null | undefined,
): MentorPlanSummary | null {
  if (!planRaw?.trim()) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(planRaw)
  } catch (error) {
    console.warn('[Mentor] could not parse plan_json', error)
    return null
  }
  const plan = asRecord(parsed)
  if (!plan) return null

  const slots = Array.isArray(plan.slots) ? plan.slots.map(asRecord).filter((slot): slot is Record<string, unknown> => slot != null) : []
  const slotTypes = new Set<string>()
  const targetSkills = new Set<string>()
  for (const slot of slots) {
    const slotType = asString(slot.slot_type)
    if (slotType) slotTypes.add(slotType)
    const targetSkill = asString(slot.target_skill)
    if (targetSkill) targetSkills.add(targetSkill)
  }

  const parseArray = (raw: string | null | undefined): unknown[] => {
    if (!raw?.trim()) return []
    try {
      const value = JSON.parse(raw)
      return Array.isArray(value) ? value : []
    } catch (error) {
      console.warn('[Mentor] could not parse plan history array', error)
      return []
    }
  }
  const adaptations = [
    ...(Array.isArray(plan.adaptation_log) ? plan.adaptation_log : []),
    ...parseArray(adaptationRaw),
  ]
  const slotResults = [
    ...(Array.isArray(plan.slot_results) ? plan.slot_results : []),
    ...parseArray(resultRaw),
  ]

  let remediationCount = 0
  let skipCount = 0
  for (const item of adaptations) {
    const record = asRecord(item)
    if (!record) continue
    if (record.action === 'insert_remediation') remediationCount += 1
    if (record.action === 'skip_easier') skipCount += 1
  }

  const accuracies: number[] = []
  for (const item of slotResults) {
    const record = asRecord(item)
    const accuracy = asNumber(record?.accuracy)
    if (accuracy != null) accuracies.push(clamp01(accuracy))
  }

  return {
    slot_count: slots.length,
    slot_types: [...slotTypes],
    target_skills: [...targetSkills],
    remediation_count: remediationCount,
    skip_count: skipCount,
    avg_slot_accuracy: accuracies.length > 0 ? mean(accuracies) : null,
  }
}

function buildDnaSummary(dna: PlayerDNA | null): MentorDnaSummary {
  if (dna == null) {
    return {
      timing_feel: 'centered',
      top_pitch_classes: [],
      top_positions: [],
      technique_frequency: {},
    }
  }
  const topPitchClasses = dna.pitch_class_bias
    .map((value, index) => ({ value, index }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value || a.index - b.index)
    .slice(0, 3)
    .map((item) => CHROMATIC_NOTE_NAMES[item.index] ?? 'C')
  const topPositions = dna.position_bias
    .map((value, index) => ({ value, index }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value || a.index - b.index)
    .slice(0, 3)
    .map((item) => (item.index === 0 ? 'frets 0–1' : `frets ${item.index * 2}–${item.index * 2 + 1}`))
  return {
    timing_feel: dna.timing_feel,
    top_pitch_classes: topPitchClasses,
    top_positions: topPositions,
    technique_frequency: { ...dna.technique_frequency },
  }
}

function buildSkillDeltas(
  sessions: readonly { row: SessionArchiveRow; ts: number }[],
  skillNodes: readonly SkillNodeRow[],
): MentorSkillDelta[] {
  const valuesBySkill = new Map<string, Array<{ ts: number; value: number }>>()
  for (const session of sessions) {
    const score = parseScoreSnapshot(session.row.review_snapshot)
    if (!score) continue
    for (const [id, value] of Object.entries(score.node_scores)) {
      if (!Number.isFinite(value)) continue
      const bucket = valuesBySkill.get(id) ?? []
      bucket.push({ ts: session.ts, value: clamp01(value) })
      valuesBySkill.set(id, bucket)
    }
  }

  const knownOrder = new Map<string, number>(DEFAULT_SKILL_NODES.map((node, index) => [node.id, index]))
  const nodesById = new Map(skillNodes.map((node) => [node.id, node]))

  const deltas: MentorSkillDelta[] = []
  for (const [id, values] of valuesBySkill) {
    if (values.length < 2) continue
    const sorted = [...values].sort((a, b) => a.ts - b.ts)
    const split = Math.floor(sorted.length / 2)
    const priorValues = sorted.slice(0, split).map((item) => item.value)
    const recentValues = sorted.slice(split).map((item) => item.value)
    if (priorValues.length === 0 || recentValues.length === 0) continue
    const prior = mean(priorValues)
    const recent = mean(recentValues)
    deltas.push({
      id,
      label: nodesById.get(id)?.label ?? skillLabel(id),
      prior,
      recent,
      delta: recent - prior,
    })
  }

  return deltas.sort((a, b) => {
    const orderA = knownOrder.get(a.id) ?? Number.MAX_SAFE_INTEGER
    const orderB = knownOrder.get(b.id) ?? Number.MAX_SAFE_INTEGER
    return orderA - orderB || a.id.localeCompare(b.id)
  })
}

/**
 * Build the compact monthly trajectory Claude sees. Pure — no I/O, safe for unit tests.
 * Returns `eligible: false` when the player does not yet have 30 days / 3 evidence items.
 */
export function buildMentorTrajectory(input: MentorTrajectoryInput): MentorTrajectoryBuildResult {
  const now = input.now ?? new Date()
  const nowMs = now.getTime()

  const sessionRows = input.sessions
    .map((session) => ({ row: session, ts: parseDateMs(session.date) }))
    .filter((item): item is { row: SessionArchiveRow; ts: number } => item.ts != null)
  const jamRows = input.jams
    .map((jam) => ({ row: jam, ts: parseDateMs(jam.date) }))
    .filter((item): item is { row: JamSnapshotRow; ts: number } => item.ts != null)
  const completionRows = input.completions
    .map((completion) => ({ row: completion, ts: parseDateMs(completion.completed_at) }))
    .filter((item): item is { row: PracticePlanCompletionRow; ts: number } => item.ts != null)

  const allTimestamps = [
    ...sessionRows.map((item) => item.ts),
    ...jamRows.map((item) => item.ts),
    ...completionRows.map((item) => item.ts),
  ]
  const latest = allTimestamps.length > 0 ? Math.max(...allTimestamps) : nowMs
  const windowStart = latest - MENTOR_WINDOW_DAYS * DAY_MS
  const inWindow = (ts: number): boolean => ts >= windowStart && ts <= latest

  const windowSessions = sessionRows
    .filter((item) => inWindow(item.ts))
    .sort((a, b) => a.ts - b.ts)
  const windowJams = jamRows.filter((item) => inWindow(item.ts))
  const windowCompletions = completionRows
    .filter((item) => inWindow(item.ts))
    .sort((a, b) => a.ts - b.ts)

  const windowTimestamps = [
    ...windowSessions.map((item) => item.ts),
    ...windowJams.map((item) => item.ts),
    ...windowCompletions.map((item) => item.ts),
  ]
  const windowOldest = windowTimestamps.length > 0 ? Math.min(...windowTimestamps) : null
  const historyDays = windowOldest == null ? 0 : Math.max(0, Math.floor((latest - windowOldest) / DAY_MS))
  const totalEvidence = windowSessions.length + windowJams.length + windowCompletions.length
  const eligible = historyDays >= MENTOR_MIN_HISTORY_DAYS && totalEvidence >= 3

  const accuracyPoints = windowSessions
    .map((item) => {
      const accuracy = sessionOverallAccuracy(item.row)
      if (accuracy == null || !Number.isFinite(accuracy)) return null
      return { date: item.row.date, accuracy: clamp01(accuracy) }
    })
    .filter((point): point is { date: string; accuracy: number } => point != null)
    .slice(-MENTOR_MAX_ACCURACY_POINTS)

  const feedback = input.feedback
    .map((row) => ({ row, ts: parseDateMs(row.timestamp) }))
    .filter((item): item is { row: UserFeedbackRow; ts: number } => item.ts != null && inWindow(item.ts))

  const byType: Record<string, number> = {}
  const chordCounts = new Map<string, number>()
  for (const { row } of feedback) {
    byType[row.feedback_type] = (byType[row.feedback_type] ?? 0) + 1
    if (row.feedback_type === 'chord_correction' || row.feedback_type === 'wrong_chord') {
      const chord = (row.original_value || row.corrected_value || '').trim()
      if (chord) chordCounts.set(chord, (chordCounts.get(chord) ?? 0) + 1)
    }
  }
  const mostCorrectedChords = [...chordCounts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 5)
    .map(([chord, count]) => ({ chord, count }))

  const weakNodes: MentorWeakNode[] = [...input.skillNodes]
    .filter((node) => Number.isFinite(node.score))
    .sort((a, b) => a.score - b.score || a.id.localeCompare(b.id))
    .slice(0, 3)
    .map((node) => ({
      id: node.id,
      label: node.label?.trim() || skillLabel(node.id),
      score: clamp01(node.score),
    }))

  let plan: MentorPlanSummary | null = null
  if (input.activePlan) {
    plan = buildPlanSummary(
      input.activePlan.plan_json,
      input.activePlan.adaptation_log,
      input.activePlan.slot_results_json,
    )
  }
  if (plan == null && windowCompletions.length > 0) {
    const latestCompletion = windowCompletions[windowCompletions.length - 1]!
    plan = buildPlanSummary(latestCompletion.row.plan_json, null, null)
  }

  const confidence: MentorConfidence =
    historyDays >= 60 && windowSessions.length >= 8
      ? 'high'
      : historyDays >= MENTOR_MIN_HISTORY_DAYS && windowSessions.length >= 3
        ? 'medium'
        : 'low'

  const history: MentorHistorySummary = {
    days: historyDays,
    session_count: windowSessions.length,
    jam_count: windowJams.length,
    plan_count: windowCompletions.length,
    correction_count: feedback.length,
    confidence,
  }

  const tasteCandidates = [...new Set(input.tasteSongCandidates.map((title) => title.trim()).filter(Boolean))].slice(0, 12)

  const payload: MentorTrajectoryRequest = {
    mode: input.mode,
    generated_at: now.toISOString(),
    history,
    accuracy_points: accuracyPoints,
    skill_deltas: buildSkillDeltas(windowSessions, input.skillNodes),
    weak_nodes: weakNodes,
    goals: {
      experience_level: input.learningContext?.experience_level ?? null,
      style_focus: input.learningContext?.solo_focus_notes ?? null,
      style_label: input.taste?.style_label ?? null,
      technique_affinity: input.taste?.technique_affinity ?? [],
      song_candidates: tasteCandidates,
    },
    dna: buildDnaSummary(input.dna),
    corrections: {
      total: feedback.length,
      by_type: byType,
      most_corrected_chords: mostCorrectedChords,
    },
    plan,
    library_songs: input.librarySongs.map((song) => ({ ...song, techniques: [...song.techniques] })),
    taste_song_candidates: tasteCandidates,
  }

  return { eligible, historyDays, evidenceCount: totalEvidence, payload }
}
