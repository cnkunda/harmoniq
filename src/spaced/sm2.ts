/**
 * SM-2 spaced repetition + README weighted skill score (PRIORITIES §30).
 * Pure functions — no I/O.
 */

export type Sm2CardState = {
  easinessFactor: number
  intervalDays: number
  repetitions: number
}

/** Quality 0–5 per SM-2: 0 = complete blackout … 5 = perfect response */
export type Sm2Quality = 0 | 1 | 2 | 3 | 4 | 5

export function initialSm2State(): Sm2CardState {
  return { easinessFactor: 2.5, intervalDays: 1, repetitions: 0 }
}

/**
 * One SM-2 review step. On quality < 3, interval collapses to 1 day and repetitions reset.
 */
export function sm2Step(state: Sm2CardState, quality: number): Sm2CardState {
  const q = Math.max(0, Math.min(5, Math.floor(quality)))
  let { easinessFactor, intervalDays, repetitions } = state

  if (q < 3) {
    return { easinessFactor, intervalDays: 1, repetitions: 0 }
  }

  repetitions += 1
  if (repetitions === 1) {
    intervalDays = 1
  } else if (repetitions === 2) {
    intervalDays = 6
  } else {
    intervalDays = Math.max(1, Math.round(intervalDays * easinessFactor))
  }

  const delta = 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)
  easinessFactor = Math.max(1.3, easinessFactor + delta)

  return { easinessFactor, intervalDays, repetitions }
}

/** README: new_score = old × 0.8 + session × 0.2 */
export function weightedSkillScore(oldScore: number, sessionScore: number): number {
  const o = Number.isFinite(oldScore) ? oldScore : 0
  const s = Number.isFinite(sessionScore) ? Math.max(0, Math.min(1, sessionScore)) : 0
  return o * 0.8 + s * 0.2
}

/** Map 0–1 session metric to SM-2 quality (integer 0–5). */
export function sessionScoreToQuality(score01: number): number {
  const s = Math.max(0, Math.min(1, score01))
  return Math.round(s * 5)
}

/** ISO date string YYYY-MM-DD */
export function addCalendarDays(isoDate: string, days: number): string {
  const [y, m, d] = isoDate.split('-').map((x) => Number.parseInt(x, 10))
  const dt = new Date(Date.UTC(y, m - 1, d))
  dt.setUTCDate(dt.getUTCDate() + days)
  const yy = dt.getUTCFullYear()
  const mm = String(dt.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(dt.getUTCDate()).padStart(2, '0')
  return `${yy}-${mm}-${dd}`
}

export function todayIsoDate(): string {
  const dt = new Date()
  const yy = dt.getUTCFullYear()
  const mm = String(dt.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(dt.getUTCDate()).padStart(2, '0')
  return `${yy}-${mm}-${dd}`
}

export function nextReviewDateIso(intervalDays: number, fromDateIso?: string): string {
  const base = fromDateIso ?? todayIsoDate()
  return addCalendarDays(base, Math.max(1, Math.round(intervalDays)))
}

/** DB row slice + session metric → fields to persist after one review (PRIORITIES §30). */
export type SkillNodeSessionUpdate = {
  score: number
  easiness_factor: number
  interval_days: number
  sm2_repetitions: number
  next_review_date: string
  sessions_count: number
  last_session_date: string
  progress_confidence: 'low' | 'medium' | 'high'
  progress_note: string
}

export type ProgressSignals = {
  accuracyScore01?: number
  timingStability01?: number
  reliabilityScore01?: number
  confidence?: 'low' | 'medium' | 'high'
  reliabilityFlags?: string[]
}

export function deriveSkillNodeAfterSession(
  current: {
    score: number
    easiness_factor: number
    interval_days: number
    sm2_repetitions: number
    sessions_count: number
  },
  sessionScore01: number,
  signals?: ProgressSignals,
): SkillNodeSessionUpdate {
  const reliabilityScore = Math.max(0, Math.min(1, signals?.reliabilityScore01 ?? 0.75))
  const timingScore = Math.max(0, Math.min(1, signals?.timingStability01 ?? sessionScore01))
  const accuracyScore = Math.max(0, Math.min(1, signals?.accuracyScore01 ?? sessionScore01))
  const confidence = signals?.confidence ?? (reliabilityScore >= 0.8 ? 'high' : reliabilityScore >= 0.58 ? 'medium' : 'low')
  const reliabilityPenalty = confidence === 'low' ? 0.65 : confidence === 'medium' ? 0.86 : 1
  const composite = Math.max(0, Math.min(1, (accuracyScore * 0.5 + timingScore * 0.25 + sessionScore01 * 0.25) * reliabilityPenalty))
  const newScore = weightedSkillScore(current.score, composite)
  const q = sessionScoreToQuality(composite)
  const sm2 = sm2Step(
    {
      easinessFactor: current.easiness_factor,
      intervalDays: current.interval_days,
      repetitions: current.sm2_repetitions,
    },
    q,
  )
  const today = todayIsoDate()
  return {
    score: newScore,
    easiness_factor: sm2.easinessFactor,
    interval_days: sm2.intervalDays,
    sm2_repetitions: sm2.repetitions,
    next_review_date: nextReviewDateIso(sm2.intervalDays, today),
    sessions_count: current.sessions_count + 1,
    last_session_date: today,
    progress_confidence: confidence,
    progress_note:
      confidence === 'low'
        ? 'Muted update due to low capture confidence.'
        : confidence === 'medium'
          ? 'Applied confidence-weighted update.'
          : 'Applied full-confidence update.',
  }
}
