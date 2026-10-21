import { describe, expect, it } from 'vitest'

import { summaryFromPlanCompletionRow } from '@/src/home/planCompletionSummary'
import type { PracticePlanCompletionRow } from '@/src/db/types'

function rowWithPlan(plan: unknown): PracticePlanCompletionRow {
  return {
    id: 'completion-1',
    completed_at: '2026-10-21T10:00:00.000Z',
    plan_json: JSON.stringify(plan),
  }
}

describe('summaryFromPlanCompletionRow', () => {
  it('returns the legacy summary when slot results are absent', () => {
    const summary = summaryFromPlanCompletionRow(
      rowWithPlan({
        plan_id: 'plan-1',
        total_duration_seconds: 600,
        slots: [
          { title: 'Warm up', slot_type: 'warmup' },
          { title: 'Solo', slot_type: 'song_section' },
        ],
      }),
    )

    expect(summary).toEqual({
      stepCount: 2,
      firstTitle: 'Warm up',
      slotResults: [],
      remediationCount: 0,
      skippedCount: 0,
    })
  })

  it('parses enriched slot results and adaptation counts', () => {
    const summary = summaryFromPlanCompletionRow(
      rowWithPlan({
        plan_id: 'plan-2',
        total_duration_seconds: 420,
        slots: [{ title: 'Warm up', slot_type: 'warmup' }],
        slot_results: [
          {
            slot_id: 'slot-1',
            slot_type: 'warmup',
            title: 'Warm up',
            accuracy: 0.82,
            timing: 0.74,
            confidence: 'high',
            completion: true,
          },
          {
            slot_id: 'slot-2',
            slot_type: 'technique',
            title: 'Remediation — Bending',
            accuracy: null,
            timing: null,
            confidence: null,
            completion: true,
          },
        ],
        adaptation_log: [
          { slot_id: 'slot-1', action: 'insert_remediation', reason: 'low' },
          { slot_id: 'slot-2', action: 'skip_easier', reason: 'high' },
          { slot_id: 'slot-3', action: 'none', reason: 'none' },
        ],
      }),
    )

    expect(summary.stepCount).toBe(1)
    expect(summary.firstTitle).toBe('Warm up')
    expect(summary.slotResults).toHaveLength(2)
    expect(summary.slotResults[0]).toMatchObject({ slot_id: 'slot-1', accuracy: 0.82, timing: 0.74 })
    expect(summary.remediationCount).toBe(1)
    expect(summary.skippedCount).toBe(1)
  })

  it('returns an empty summary for malformed JSON', () => {
    const summary = summaryFromPlanCompletionRow({
      id: 'completion-2',
      completed_at: '2026-10-21T10:00:00.000Z',
      plan_json: '{not-json',
    })

    expect(summary).toEqual({
      stepCount: 0,
      firstTitle: null,
      slotResults: [],
      remediationCount: 0,
      skippedCount: 0,
    })
  })
})
