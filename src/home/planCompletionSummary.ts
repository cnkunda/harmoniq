import type { PracticePlanCompletionRow } from '@/src/db/types'
import type { PracticePlanPayload } from '@/src/types'

export function summaryFromPlanCompletionRow(row: PracticePlanCompletionRow): {
  stepCount: number
  firstTitle: string | null
} {
  try {
    const o = JSON.parse(row.plan_json) as PracticePlanPayload
    const slots = Array.isArray(o.slots) ? o.slots : []
    const first = typeof slots[0]?.title === 'string' ? slots[0]!.title.trim() || null : null
    return { stepCount: slots.length, firstTitle: first }
  } catch {
    return { stepCount: 0, firstTitle: null }
  }
}
