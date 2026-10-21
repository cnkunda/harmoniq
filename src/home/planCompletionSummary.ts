import type { PracticePlanCompletionRow } from '@/src/db/types'
import type {
  CompletedPracticePlanPayload,
  PlanSlotResultPayload,
} from '@/src/types'

export interface PlanCompletionSummary {
  stepCount: number
  firstTitle: string | null
  slotResults: PlanSlotResultPayload[]
  remediationCount: number
  skippedCount: number
}

export function summaryFromPlanCompletionRow(row: PracticePlanCompletionRow): PlanCompletionSummary {
  try {
    const o = JSON.parse(row.plan_json) as CompletedPracticePlanPayload
    const slots = Array.isArray(o.slots) ? o.slots : []
    const first = typeof slots[0]?.title === 'string' ? slots[0]!.title.trim() || null : null
    const slotResults = Array.isArray(o.slot_results)
      ? o.slot_results.filter(
          (result): result is PlanSlotResultPayload =>
            result != null &&
            typeof result.slot_id === 'string' &&
            typeof result.slot_type === 'string' &&
            typeof result.title === 'string',
        )
      : []
    const adaptations = Array.isArray(o.adaptation_log) ? o.adaptation_log : []
    return {
      stepCount: slots.length,
      firstTitle: first,
      slotResults,
      remediationCount: adaptations.filter((a) => a?.action === 'insert_remediation').length,
      skippedCount: adaptations.filter((a) => a?.action === 'skip_easier').length,
    }
  } catch {
    return {
      stepCount: 0,
      firstTitle: null,
      slotResults: [],
      remediationCount: 0,
      skippedCount: 0,
    }
  }
}
