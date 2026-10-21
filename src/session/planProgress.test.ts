import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Router } from 'expo-router'

import { toast } from '@/components/ToastConfig'
import { adaptPracticePlan } from '@/src/api/analyze'
import { insertPracticePlanCompletionRow, insertSessionRow, markPracticePlanStatus } from '@/src/db/client'
import { completeSession } from '@/src/analytics/sessionTracker'
import { saveActivePlanProgress } from '@/src/session/activePlanPersistence'
import { completePracticePlanSlot } from '@/src/session/planProgress'
import { navigateToPracticePlanSlot } from '@/src/session/practicePlanNavigation'
import { usePlanStore } from '@/src/stores/planStore'
import type { DrillSlotPayload, PracticePlanPayload } from '@/src/types'

vi.mock('@/components/ToastConfig', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('@/src/api/analyze', () => ({ adaptPracticePlan: vi.fn() }))
vi.mock('@/src/db/client', () => ({
  insertPracticePlanCompletionRow: vi.fn(),
  insertSessionRow: vi.fn(),
  markPracticePlanStatus: vi.fn(),
}))
vi.mock('@/src/analytics/sessionTracker', () => ({ completeSession: vi.fn() }))
vi.mock('@/src/session/activePlanPersistence', () => ({ saveActivePlanProgress: vi.fn() }))
vi.mock('@/src/session/practicePlanNavigation', () => ({ navigateToPracticePlanSlot: vi.fn() }))
vi.mock('@/src/stores/lessonStore', () => ({ useLessonStore: { getState: () => ({ lesson: null }) } }))

function makeSlot(slotId: string, intent: DrillSlotPayload['intent'] = 'practice'): DrillSlotPayload {
  return {
    slot_id: slotId,
    slot_type: 'technique',
    duration_seconds: 240,
    title: slotId,
    coach_intro: '',
    difficulty: 2,
    intent,
  }
}

function makePlan(): PracticePlanPayload {
  return {
    plan_id: 'plan-1',
    slots: [makeSlot('slot-a'), makeSlot('slot-b')],
    total_duration_seconds: 480,
  }
}

const router = { push: vi.fn(), replace: vi.fn() } as unknown as Router
const deps = { saveLesson: vi.fn(), setLessonSectionIndex: vi.fn() }

describe('completePracticePlanSlot', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    usePlanStore.getState().clearPlan()
  })

  it('records the result, applies adaptation, and advances to the adapted slot', async () => {
    const plan = makePlan()
    const remediation = makeSlot('slot-remediation', 'remediation')
    const adaptedPlan: PracticePlanPayload = {
      ...plan,
      slots: [plan.slots[0]!, remediation, plan.slots[1]!],
      total_duration_seconds: 660,
    }
    vi.mocked(adaptPracticePlan).mockResolvedValue({
      plan: adaptedPlan,
      next_slot_index: 1,
      slot_result: {
        slot_id: 'slot-a',
        slot_type: 'technique',
        title: 'slot-a',
        accuracy: 0.3,
        timing: 0.6,
        confidence: 'high',
        completion: true,
      },
      adaptation: {
        slot_id: 'slot-a',
        action: 'insert_remediation',
        reason: 'low accuracy',
        original_duration_seconds: 480,
        new_duration_seconds: 660,
        inserted_slot_id: 'slot-remediation',
      },
    })
    usePlanStore.getState().setPlan(plan)

    await completePracticePlanSlot({
      router,
      deps,
      slotIndex: 0,
      performance: {
        slot_id: 'slot-a',
        slot_type: 'technique',
        title: 'slot-a',
        accuracy: 0.3,
        timing: 0.6,
        confidence: 'high',
        completion: true,
      },
    })

    expect(adaptPracticePlan).toHaveBeenCalledTimes(1)
    const state = usePlanStore.getState()
    expect(state.currentPlan?.slots.map((slot) => slot.slot_id)).toEqual([
      'slot-a',
      'slot-remediation',
      'slot-b',
    ])
    expect(state.currentSlotIndex).toBe(1)
    expect(state.slotResults).toHaveLength(1)
    expect(state.adaptationLog).toEqual([expect.objectContaining({ action: 'insert_remediation' })])
    expect(saveActivePlanProgress).toHaveBeenCalledWith(
      expect.objectContaining({ slotIndex: 1, plan: expect.objectContaining({ plan_id: 'plan-1' }) }),
    )
    expect(navigateToPracticePlanSlot).toHaveBeenCalledWith(router, deps, 1)
  })

  it('records completion-only results for unscored steps without adapting', async () => {
    const plan = makePlan()
    usePlanStore.getState().setPlan(plan)

    await completePracticePlanSlot({ router, deps, slotIndex: 0, performance: null })

    expect(adaptPracticePlan).not.toHaveBeenCalled()
    const state = usePlanStore.getState()
    expect(state.slotResults[0]).toMatchObject({
      slot_id: 'slot-a',
      completion: true,
      accuracy: null,
      timing: null,
    })
    expect(saveActivePlanProgress).toHaveBeenCalledWith(expect.objectContaining({ slotIndex: 1 }))
    expect(navigateToPracticePlanSlot).toHaveBeenCalledWith(router, deps, 1)
  })

  it('continues without changing the plan when adaptation fails', async () => {
    const plan = makePlan()
    vi.mocked(adaptPracticePlan).mockRejectedValue(new Error('backend unavailable'))
    usePlanStore.getState().setPlan(plan)

    await completePracticePlanSlot({
      router,
      deps,
      slotIndex: 0,
      performance: {
        slot_id: 'slot-a',
        slot_type: 'technique',
        title: 'slot-a',
        accuracy: 0.2,
        timing: null,
        confidence: 'high',
        completion: true,
      },
    })

    const state = usePlanStore.getState()
    expect(state.currentPlan?.slots).toHaveLength(2)
    expect(state.adaptationLog).toEqual([
      expect.objectContaining({ action: 'none', reason: 'adapt_failed' }),
    ])
    expect(saveActivePlanProgress).toHaveBeenCalledWith(expect.objectContaining({ slotIndex: 1 }))
    expect(navigateToPracticePlanSlot).toHaveBeenCalledWith(router, deps, 1)
  })

  it('finalizes when adaptation removes the remaining slot', async () => {
    const plan = makePlan()
    const adaptedPlan: PracticePlanPayload = {
      ...plan,
      slots: [plan.slots[0]!],
      total_duration_seconds: 240,
    }
    vi.mocked(adaptPracticePlan).mockResolvedValue({
      plan: adaptedPlan,
      next_slot_index: 1,
      slot_result: {
        slot_id: 'slot-a',
        slot_type: 'technique',
        title: 'slot-a',
        accuracy: 0.95,
        timing: 0.9,
        confidence: 'high',
        completion: true,
      },
      adaptation: {
        slot_id: 'slot-a',
        action: 'skip_easier',
        reason: 'high accuracy',
        original_duration_seconds: 480,
        new_duration_seconds: 240,
      },
    })
    usePlanStore.getState().setPlan(plan)

    await completePracticePlanSlot({
      router,
      deps,
      slotIndex: 0,
      performance: {
        slot_id: 'slot-a',
        slot_type: 'technique',
        title: 'slot-a',
        accuracy: 0.95,
        timing: 0.9,
        confidence: 'high',
        completion: true,
      },
    })

    expect(insertPracticePlanCompletionRow).toHaveBeenCalledTimes(1)
    expect(markPracticePlanStatus).toHaveBeenCalledWith('plan-1', 'completed')
    expect(usePlanStore.getState().currentPlan).toBeNull()
    expect(navigateToPracticePlanSlot).not.toHaveBeenCalled()
    expect(router.replace).toHaveBeenCalledWith('/(tabs)')
  })

  it('finalizes the plan with enriched slot history on the last slot', async () => {
    const plan = makePlan()
    plan.slots = [plan.slots[0]!]
    usePlanStore.getState().setPlan(plan)

    await completePracticePlanSlot({ router, deps, slotIndex: 0, performance: null })

    expect(insertPracticePlanCompletionRow).toHaveBeenCalledTimes(1)
    const insert = vi.mocked(insertPracticePlanCompletionRow).mock.calls[0]![0]
    const completion = JSON.parse(insert.plan_json) as PracticePlanPayload & {
      slot_results: Array<Record<string, unknown>>
    }
    expect(completion.slot_results).toHaveLength(1)
    expect(completion.slot_results[0]).toMatchObject({
      slot_id: 'slot-a',
      completion: true,
      accuracy: null,
      timing: null,
    })
    expect(insertSessionRow).toHaveBeenCalledTimes(1)
    expect(markPracticePlanStatus).toHaveBeenCalledWith('plan-1', 'completed')
    expect(completeSession).toHaveBeenCalledTimes(1)
    expect(toast.success).toHaveBeenCalledWith('Practice plan complete.')
    expect(usePlanStore.getState().currentPlan).toBeNull()
    expect(router.replace).toHaveBeenCalledWith('/(tabs)')
  })
})
