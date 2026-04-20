/**
 * Pure skill-node mutation from per-beat accuracy + section technique tags (commit 63).
 * No I/O — safe for unit tests and backend reference tests.
 */

import type { NoteResultLabel } from '@/src/session/noteAccuracyBeats'

/** Per-session beat sequence from Play / `useAppStore` (commit 49 naming). */
export type NoteAccuracyBeats = NoteResultLabel[]

export const SKILL_MUTATION_EMA_OLD = 0.85
export const SKILL_MUTATION_EMA_SESSION = 0.15

/** Last N raw session accuracies (0–1) for rolling weak-area detection. */
export const SKILL_MUTATION_ROLL_WINDOW = 3

/** Rolling mean below this across three sessions marks weak (alongside score threshold). */
export const SKILL_MUTATION_ROLL_WEAK_MAX = 0.5

export function parseTechniqueRollJson(raw: string | null | undefined): number[] {
  if (raw == null || raw.trim() === '') return []
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    const out: number[] = []
    for (const x of parsed) {
      if (typeof x === 'number' && Number.isFinite(x)) out.push(Math.max(0, Math.min(1, x)))
    }
    return out.slice(-SKILL_MUTATION_ROLL_WINDOW)
  } catch {
    return []
  }
}

export function stringifyTechniqueRoll(scores: number[]): string | null {
  const trimmed = scores.slice(-SKILL_MUTATION_ROLL_WINDOW)
  if (trimmed.length === 0) return null
  return JSON.stringify(trimmed)
}

/** Normalize lesson section markers → DEFAULT_SKILL_NODES ids (commit 29). */
export function techniqueMarkerToSkillNodeId(marker: string): string | null {
  const key = marker.trim().toLowerCase().replace(/\s+/g, '-')
  if (!key) return null
  const compact = key.replace(/-/g, '')
  if (
    key === 'bend' ||
    key === 'bends' ||
    key === 'bending' ||
    compact === 'bendrelease' ||
    key.includes('bend')
  ) {
    return 'bend_accuracy'
  }
  if (key === 'vibrato' || compact === 'vibrato') return 'vibrato_control'
  if (
    key === 'slide' ||
    key === 'slides' ||
    key === 'gliss' ||
    key.includes('slide')
  ) {
    return 'phrasing'
  }
  if (
    key === 'alternate-picking' ||
    key === 'alternatepicking' ||
    key === 'alt-picking' ||
    compact === 'alternatepicking'
  ) {
    return 'timing'
  }
  if (
    key === 'hammer-on' ||
    key === 'pull-off' ||
    key === 'hammer' ||
    key === 'pull' ||
    key === 'legato'
  ) {
    return 'phrasing'
  }
  return null
}

export function extractTechniqueTagsFromSection(section: unknown): string[] {
  if (!section || typeof section !== 'object') return []
  const o = section as Record<string, unknown>
  const raw = o.technique_tags ?? o.techniques ?? o.technique_hints
  if (typeof raw === 'string') {
    const t = raw.trim()
    return t ? [t] : []
  }
  if (!Array.isArray(raw)) return []
  const out: string[] = []
  for (const x of raw) {
    if (typeof x === 'string' && x.trim()) out.push(x.trim())
  }
  return out
}

/** Fraction of scored beats that are hit / close / vibrato (miss = 0). Ignores `ignored`. */
export function sessionAccuracyFromBeats(beats: NoteAccuracyBeats): number | null {
  const scored = beats.filter((b) => b !== 'ignored')
  if (scored.length === 0) return null
  let good = 0
  for (const b of scored) {
    if (b === 'hit' || b === 'close' || b === 'vibrato') good += 1
  }
  return good / scored.length
}

export function applySkillEma(oldScore: number, sessionAccuracy: number): number {
  const o = Number.isFinite(oldScore) ? oldScore : 0
  const s = Number.isFinite(sessionAccuracy) ? Math.max(0, Math.min(1, sessionAccuracy)) : 0
  const next = o * SKILL_MUTATION_EMA_OLD + s * SKILL_MUTATION_EMA_SESSION
  return Math.max(0, Math.min(1, next))
}

export function appendRollingSessionScores(prevJson: string | null | undefined, sessionAccuracy: number): number[] {
  const prev = parseTechniqueRollJson(prevJson)
  const next = [...prev, Math.max(0, Math.min(1, sessionAccuracy))]
  return next.slice(-SKILL_MUTATION_ROLL_WINDOW)
}

export function rollingSessionsWeak(rolling: number[]): boolean {
  if (rolling.length < SKILL_MUTATION_ROLL_WINDOW) return false
  const sum = rolling.reduce((a, x) => a + x, 0)
  return sum / rolling.length < SKILL_MUTATION_ROLL_WEAK_MAX
}

export type SkillMutationUpdate = {
  id: string
  score: number
  technique_roll_json: string | null
}

/**
 * For each technique-tagged skill node on the section, apply EMA to `score` and refresh rolling history.
 * Only returns rows that need persisting (at least one section node with session accuracy).
 */
export function computeSkillMutations(input: {
  /** Current DB rows keyed by id */
  nodesById: Map<string, { score: number; technique_roll_json: string | null }>
  beats: NoteAccuracyBeats
  section: unknown
}): SkillMutationUpdate[] {
  const sessionAcc = sessionAccuracyFromBeats(input.beats)
  if (sessionAcc == null) return []

  const tags = extractTechniqueTagsFromSection(input.section)
  const nodeIds = new Set<string>()
  for (const t of tags) {
    const id = techniqueMarkerToSkillNodeId(t)
    if (id) nodeIds.add(id)
  }
  if (nodeIds.size === 0) return []

  const out: SkillMutationUpdate[] = []
  for (const id of nodeIds) {
    const row = input.nodesById.get(id)
    if (!row) continue
    const newScore = applySkillEma(row.score, sessionAcc)
    const rolling = appendRollingSessionScores(row.technique_roll_json, sessionAcc)
    out.push({
      id,
      score: newScore,
      technique_roll_json: stringifyTechniqueRoll(rolling),
    })
  }
  return out
}
