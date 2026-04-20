import { describe, expect, it } from 'vitest'

import type { SkillNodeRow } from '@/src/db/types'

import { pickWeakAreaPulseNode } from '@/src/home/weakAreaPulseLogic'

function node(partial: Partial<SkillNodeRow> & Pick<SkillNodeRow, 'id' | 'score' | 'sessions_count'>): SkillNodeRow {
  return {
    label: null,
    easiness_factor: 2.5,
    interval_days: 1,
    next_review_date: null,
    sm2_repetitions: 0,
    last_session_date: null,
    technique_roll_json: null,
    ...partial,
  }
}

describe('pickWeakAreaPulseNode', () => {
  it('returns null when no node exceeds session threshold', () => {
    expect(pickWeakAreaPulseNode([node({ id: 'timing', score: 0.6, sessions_count: 3 })])).toBeNull()
    expect(pickWeakAreaPulseNode([node({ id: 'timing', score: 0.4, sessions_count: 2 })])).toBeNull()
  })

  it('returns lowest-scoring node among those with >2 sessions and score < 0.5', () => {
    const out = pickWeakAreaPulseNode([
      node({ id: 'bend_accuracy', label: 'Bending', score: 0.48, sessions_count: 4 }),
      node({ id: 'timing', label: 'Timing', score: 0.35, sessions_count: 5 }),
    ])
    expect(out?.id).toBe('timing')
  })
})
