import type { Router } from 'expo-router'

import { toast } from '@/components/ToastConfig'
import { adaptPracticePlan } from '@/src/api/analyze'
import { completeSession } from '@/src/analytics/sessionTracker'
import { finalizePracticePlan } from '@/src/db/client'
import { navigateToPracticePlanSlot } from '@/src/session/practicePlanNavigation'
import { saveActivePlanProgress } from '@/src/session/activePlanPersistence'
import { normalizePracticePlan } from '@/src/session/planNormalization'
import {
  sessionAccuracy01FromScoreResult,
  timingStability01FromScoreResult,
} from '@/src/session/scoreProgressSignals'
import { useLessonStore } from '@/src/stores/lessonStore'
import { usePlanStore } from '@/src/stores/planStore'
import type {
  CompletedPracticePlanPayload,
  DrillSlotPayload,
  LessonJSON,
  PlanAdaptationPayload,
  PlanConfidence,
  PlanSlotPerformancePayload,
  PlanSlotResultPayload,
  PracticePlanPayload,
  ScoreResult,
} from '@/src/types'

const LOG_PREFIX = '[planProgress]'

function createId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

/** Build the per-slot performance payload from Review's score result. */
export function slotPerformanceFromScoreResult(
  slot: DrillSlotPayload,
  result: ScoreResult | null,
): PlanSlotPerformancePayload {
  const confidence: PlanConfidence | null = result?.reliability?.confidence ?? null
  return {
    slot_id: slot.slot_id,
    slot_type: slot.slot_type,
    title: slot.title,
    accuracy: result ? sessionAccuracy01FromScoreResult(result) : null,
    timing: result ? timingStability01FromScoreResult(result) : null,
    confidence,
    completion: true,
  }
}

function completionOnlyPerformance(slot: DrillSlotPayload): PlanSlotPerformancePayload {
  return {
    slot_id: slot.slot_id,
    slot_type: slot.slot_type,
    title: slot.title,
    accuracy: null,
    timing: null,
    confidence: null,
    completion: true,
  }
}

async function finalizePlan(plan: PracticePlanPayload): Promise<void> {
  const state = usePlanStore.getState()
  const results = state.slotResults
  const adaptationLog = state.adaptationLog
  const completionPlan: CompletedPracticePlanPayload = {
    ...plan,
    slot_results: results,
    adaptation_log: adaptationLog,
  }
  const lesson = useLessonStore.getState().lesson
  const firstSlot = plan.slots[0]
  let persistenceFailed = false

  const runStep = async (label: string, step: () => Promise<void>): Promise<void> => {
    try {
      await step()
    } catch (e) {
      persistenceFailed = true
      console.error(`${LOG_PREFIX} failed to ${label}`, e)
    }
  }

  await runStep('finalize plan', () =>
    finalizePracticePlan({
      plan_id: plan.plan_id,
      completion: {
        id: createId(),
        completed_at: new Date().toISOString(),
        plan_json: JSON.stringify(completionPlan),
      },
      session: {
        id: createId(),
        song_title: firstSlot?.title ?? 'Practice session',
        artist: typeof lesson?.artist === 'string' ? lesson.artist : null,
        section_label: `${plan.slots.length}-section plan`,
        date: new Date().toISOString(),
        coach_review: null,
        pitch_accuracy: null,
        phrasing_score: null,
        nodes_targeted: [],
        job_id: typeof lesson?.job_id === 'string' ? lesson.job_id.trim() : null,
        section_index: null,
        is_ghost_reference: false,
      },
    }),
  )

  completeSession()
  usePlanStore.getState().setHomePreviewPlan(null)
  usePlanStore.getState().clearPlan()
  if (persistenceFailed) {
    toast.error('Practice plan finished, but some progress could not be saved.')
  } else {
    toast.success('Practice plan complete.')
  }
}

/**
 * Complete one plan slot, adapt the remainder, then advance or finalize.
 * Returns after routing so callers can avoid double-handling.
 */
export async function completePracticePlanSlot(args: {
  router: Router
  deps: {
    saveLesson: (lesson: LessonJSON) => void
    setLessonSectionIndex: (index: number) => void
  }
  slotIndex: number
  performance: PlanSlotPerformancePayload | null
}): Promise<void> {
  const state = usePlanStore.getState()
  const plan = state.currentPlan
  if (!plan) {
    args.router.replace('/(tabs)')
    return
  }
  const slot = plan.slots[args.slotIndex]
  if (!slot) {
    console.error(`${LOG_PREFIX} missing slot ${args.slotIndex} in active plan`)
    args.router.replace('/(tabs)')
    return
  }

  const performance = args.performance ?? completionOnlyPerformance(slot)
  const slotResult: PlanSlotResultPayload = {
    ...performance,
    slot_id: slot.slot_id,
    slot_type: slot.slot_type,
    title: slot.title,
    completion: true,
    completed_at: new Date().toISOString(),
  }
  usePlanStore.getState().appendSlotResult(slotResult)

  const nextIndex = args.slotIndex + 1
  if (nextIndex >= plan.slots.length) {
    await saveActivePlanProgress({
      slotIndex: nextIndex,
      slotResults: usePlanStore.getState().slotResults,
      adaptationLog: usePlanStore.getState().adaptationLog,
      plan,
    })
    await finalizePlan(plan)
    args.router.replace('/(tabs)')
    return
  }

  let nextPlan = plan
  let adaptationLog = usePlanStore.getState().adaptationLog
  if (performance.accuracy != null) {
    try {
      const response = await adaptPracticePlan({
        plan,
        slot_index: args.slotIndex,
        slot_performance: performance,
      })
      nextPlan = normalizePracticePlan(response.plan)
      usePlanStore.getState().restorePlan(
        nextPlan,
        response.next_slot_index,
        usePlanStore.getState().slotResults,
        adaptationLog,
        usePlanStore.getState().activePlanStartedAt,
      )
      if (response.adaptation) {
        usePlanStore.getState().appendAdaptation(response.adaptation)
        adaptationLog = usePlanStore.getState().adaptationLog
      }
    } catch (e) {
      console.error(`${LOG_PREFIX} adaptation failed; continuing with current plan`, e)
      const noop: PlanAdaptationPayload = {
        slot_id: slot.slot_id,
        action: 'none',
        reason: 'adapt_failed',
        original_duration_seconds: plan.total_duration_seconds,
        new_duration_seconds: plan.total_duration_seconds,
      }
      usePlanStore.getState().appendAdaptation(noop)
      adaptationLog = usePlanStore.getState().adaptationLog
    }
  }

  if (nextIndex >= nextPlan.slots.length) {
    await saveActivePlanProgress({
      slotIndex: nextIndex,
      slotResults: usePlanStore.getState().slotResults,
      adaptationLog,
      plan: nextPlan,
    })
    await finalizePlan(nextPlan)
    args.router.replace('/(tabs)')
    return
  }

  await saveActivePlanProgress({
    slotIndex: nextIndex,
    slotResults: usePlanStore.getState().slotResults,
    adaptationLog,
    plan: nextPlan,
  })
  await navigateToPracticePlanSlot(args.router, args.deps, nextIndex)
}
