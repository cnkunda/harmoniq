import {
  getActivePracticePlanRow,
  markPracticePlanStatus,
  startActivePracticePlanRow,
  updatePracticePlanRowState,
} from '@/src/db/client'
import type { PracticePlanRow } from '@/src/db/types'
import { normalizePracticePlan } from '@/src/session/planNormalization'
import { usePlanStore } from '@/src/stores/planStore'
import type {
  PlanAdaptationPayload,
  PlanSlotResultPayload,
  PracticePlanPayload,
} from '@/src/types'

const LOG_PREFIX = '[planPersistence]'

function parseArray<T>(raw: string | null | undefined, label: string): T[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) {
      console.error(`${LOG_PREFIX} ${label} is not an array; ignoring`)
      return []
    }
    return parsed as T[]
  } catch (e) {
    console.error(`${LOG_PREFIX} failed to parse ${label}`, e)
    return []
  }
}

/** Persist a freshly started plan; navigation proceeds even if the DB write fails. */
export async function startActivePracticePlan(plan: PracticePlanPayload): Promise<PracticePlanPayload> {
  const normalized = normalizePracticePlan(plan)
  usePlanStore.getState().setPlan(normalized)
  const state = usePlanStore.getState()
  const startedAt = state.activePlanStartedAt ?? Date.now()
  try {
    await startActivePracticePlanRow({
      plan_id: normalized.plan_id,
      plan_json: JSON.stringify(normalized),
      current_slot_index: 0,
      slot_results_json: '[]',
      adaptation_log: '[]',
      started_at: new Date(startedAt).toISOString(),
    })
  } catch (e) {
    console.error(`${LOG_PREFIX} failed to start active plan`, e)
  }
  return normalized
}

/** Restore the persisted active plan, if any. Malformed rows are abandoned. */
export async function resumeActivePracticePlan(): Promise<PracticePlanPayload | null> {
  let row: PracticePlanRow | null = null
  try {
    row = await getActivePracticePlanRow()
  } catch (e) {
    console.error(`${LOG_PREFIX} failed to read active plan`, e)
    return null
  }
  if (!row) return null

  try {
    const parsed = JSON.parse(row.plan_json) as PracticePlanPayload
    const plan = normalizePracticePlan(parsed)
    if (plan.slots.length === 0) {
      throw new Error('persisted plan has no slots')
    }
    const index = Math.max(0, Math.min(plan.slots.length - 1, Math.floor(row.current_slot_index)))
    const slotResults = parseArray<PlanSlotResultPayload>(row.slot_results_json, 'slot_results_json')
    const adaptationLog = parseArray<PlanAdaptationPayload>(row.adaptation_log, 'adaptation_log')
    const startedMs = Date.parse(row.started_at)
    usePlanStore.getState().restorePlan(
      plan,
      index,
      slotResults,
      adaptationLog,
      Number.isFinite(startedMs) ? startedMs : null,
    )
    return plan
  } catch (e) {
    console.error(`${LOG_PREFIX} failed to restore active plan; abandoning it`, e)
    try {
      await markPracticePlanStatus(row.plan_id, 'abandoned')
    } catch (markError) {
      console.error(`${LOG_PREFIX} failed to abandon malformed plan`, markError)
    }
    usePlanStore.getState().clearPlan()
    return null
  }
}

/** Persist the active index/results/log; adapted plan JSON is included when supplied. */
export async function saveActivePlanProgress(input: {
  slotIndex: number
  slotResults: PlanSlotResultPayload[]
  adaptationLog: PlanAdaptationPayload[]
  plan?: PracticePlanPayload
}): Promise<void> {
  const plan = input.plan ?? usePlanStore.getState().currentPlan
  if (!plan) {
    console.error(`${LOG_PREFIX} cannot save progress without an active plan`)
    return
  }
  try {
    await updatePracticePlanRowState(plan.plan_id, {
      plan_json: JSON.stringify(plan),
      current_slot_index: input.slotIndex,
      slot_results_json: JSON.stringify(input.slotResults),
      adaptation_log: JSON.stringify(input.adaptationLog),
    })
  } catch (e) {
    console.error(`${LOG_PREFIX} failed to save active plan progress`, e)
  }
}

/** Mark the active row abandoned and clear in-memory session state. */
export async function abandonActivePlan(planId: string): Promise<void> {
  try {
    await markPracticePlanStatus(planId, 'abandoned')
  } catch (e) {
    console.error(`${LOG_PREFIX} failed to abandon active plan`, e)
  }
  usePlanStore.getState().clearPlan()
}
