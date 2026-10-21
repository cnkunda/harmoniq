import { describe, expect, it } from 'vitest'

import { normalizePracticePlan } from '@/src/session/planNormalization'
import type { PracticePlanPayload } from '@/src/types'

describe('normalizePracticePlan', () => {
  it('preserves backend IDs and slot metadata', () => {
    const plan = {
      plan_id: 'plan-1',
      total_duration_seconds: 600,
      slots: [
        {
          slot_id: 'slot-1',
          slot_type: 'technique',
          duration_seconds: 300,
          title: 'Bending',
          coach_intro: 'Slow and clean.',
          difficulty: 1,
          intent: 'remediation',
          target_skill: 'bend_accuracy',
          remediation_for_slot_id: 'slot-0',
        },
      ],
    } as PracticePlanPayload

    expect(normalizePracticePlan(plan)).toMatchObject({
      plan_id: 'plan-1',
      total_duration_seconds: 300,
      slots: [
        {
          slot_id: 'slot-1',
          slot_type: 'technique',
          difficulty: 1,
          intent: 'remediation',
          target_skill: 'bend_accuracy',
          remediation_for_slot_id: 'slot-0',
        },
      ],
    })
  })

  it('fills missing IDs and defaults from legacy payloads', () => {
    const plan = {
      slots: [
        {
          slot_type: 'warmup',
          duration_seconds: 120.4,
          title: 'Warm up',
          coach_intro: '',
        },
        {
          slot_type: 'song_section',
          duration_seconds: -10,
          title: '  ',
          coach_intro: 'x',
          difficulty: 9,
          intent: 'unknown',
        },
      ],
    } as unknown as PracticePlanPayload

    const normalized = normalizePracticePlan(plan)

    expect(normalized.plan_id).toBeTruthy()
    expect(normalized.slots[0]?.slot_id).toBeTruthy()
    expect(normalized.slots[1]?.slot_id).toBeTruthy()
    expect(normalized.slots[0]).toMatchObject({ difficulty: 2, intent: 'practice', duration_seconds: 120 })
    expect(normalized.slots[1]).toMatchObject({
      slot_type: 'song_section',
      title: 'Practice step 2',
      difficulty: 3,
      intent: 'practice',
      duration_seconds: 0,
    })
    expect(normalized.total_duration_seconds).toBe(120)
  })

  it('falls back to technique for unknown slot types', () => {
    const plan = {
      plan_id: 'plan-2',
      slots: [{ slot_type: 'mystery', duration_seconds: 60, title: 'Mystery', coach_intro: '' }],
    } as unknown as PracticePlanPayload

    expect(normalizePracticePlan(plan).slots[0]).toMatchObject({
      slot_type: 'technique',
      difficulty: 2,
      intent: 'practice',
    })
  })
})
