import { describe, expect, it } from 'vitest'

import {
  addCalendarDays,
  deriveSkillNodeAfterSession,
  initialSm2State,
  sessionScoreToQuality,
  sm2Step,
  weightedSkillScore,
} from '@/src/spaced/sm2'

describe('weightedSkillScore', () => {
  it('matches README formula', () => {
    expect(weightedSkillScore(0.5, 1.0)).toBeCloseTo(0.6, 5)
    expect(weightedSkillScore(0.8, 0.5)).toBeCloseTo(0.74, 5)
  })
})

describe('sm2Step interval expansion', () => {
  it('increases interval after repeated good reviews', () => {
    let s = initialSm2State()
    s = sm2Step(s, 4) // rep 1 -> 1 day
    expect(s.repetitions).toBe(1)
    expect(s.intervalDays).toBe(1)

    s = sm2Step(s, 4) // rep 2 -> 6 days
    expect(s.repetitions).toBe(2)
    expect(s.intervalDays).toBe(6)

    s = sm2Step(s, 4) // rep 3+ -> round(6 * EF)
    expect(s.repetitions).toBe(3)
    expect(s.intervalDays).toBeGreaterThan(6)
  })
})

describe('sm2Step interval contraction', () => {
  it('resets to 1 day when quality < 3', () => {
    let s = initialSm2State()
    s = sm2Step(s, 5)
    s = sm2Step(s, 5)
    s = sm2Step(s, 5)
    expect(s.intervalDays).toBeGreaterThan(1)

    s = sm2Step(s, 2)
    expect(s.repetitions).toBe(0)
    expect(s.intervalDays).toBe(1)
  })
})

describe('sessionScoreToQuality', () => {
  it('maps endpoints', () => {
    expect(sessionScoreToQuality(0)).toBe(0)
    expect(sessionScoreToQuality(1)).toBe(5)
  })
})

describe('addCalendarDays', () => {
  it('rolls month correctly', () => {
    expect(addCalendarDays('2026-01-30', 5)).toBe('2026-02-04')
  })
})

describe('deriveSkillNodeAfterSession', () => {
  it('bumps sessions_count and sets next_review_date from interval', () => {
    const u = deriveSkillNodeAfterSession(
      {
        score: 0.5,
        easiness_factor: 2.5,
        interval_days: 1,
        sm2_repetitions: 0,
        sessions_count: 2,
      },
      1.0,
    )
    expect(u.sessions_count).toBe(3)
    expect(u.score).toBeCloseTo(0.6, 5)
    expect(u.last_session_date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(u.next_review_date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})
