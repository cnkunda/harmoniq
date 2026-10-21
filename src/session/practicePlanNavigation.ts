import type { Router } from 'expo-router'

import { speak } from '@/src/audio/voiceCoach'
import { sessionEntryHref } from '@/src/constants/sessionFlow'
import { getLessonByJobId } from '@/src/db/client'
import {
  resumeActivePracticePlan,
  saveActivePlanProgress,
  startActivePracticePlan,
} from '@/src/session/activePlanPersistence'
import { usePlanStore } from '@/src/stores/planStore'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
import type { LessonJSON, PracticePlanPayload } from '@/src/types'

async function persistCurrentPosition(): Promise<void> {
  const state = usePlanStore.getState()
  await saveActivePlanProgress({
    slotIndex: state.currentSlotIndex,
    slotResults: state.slotResults,
    adaptationLog: state.adaptationLog,
  })
}

export async function navigateToPracticePlanSlot(
  router: Router,
  deps: {
    saveLesson: (lesson: LessonJSON) => void
    setLessonSectionIndex: (index: number) => void
  },
  slotIndex: number,
): Promise<void> {
  const { currentPlan, setCurrentSlotIndex } = usePlanStore.getState()
  if (!currentPlan?.slots?.length) return
  if (slotIndex < 0 || slotIndex >= currentPlan.slots.length) return
  const slot = currentPlan.slots[slotIndex]
  const skipTune = useSessionPrefsStore.getState().skipTuneStep

  if (slot.slot_type === 'song_section' && slot.lesson_ref) {
    const lesson = await getLessonByJobId(slot.lesson_ref)
    if (!lesson) {
      throw new Error(`No saved lesson for job ${slot.lesson_ref}. Open the song from Library first.`)
    }
    deps.saveLesson(lesson)
    deps.setLessonSectionIndex(0)
    setCurrentSlotIndex(slotIndex)
    await persistCurrentPosition()
    const intro = typeof slot.coach_intro === 'string' ? slot.coach_intro.trim() : ''
    if (intro) speak(intro)
    router.push(sessionEntryHref(skipTune))
    return
  }

  setCurrentSlotIndex(slotIndex)
  await persistCurrentPosition()
  const intro = typeof slot.coach_intro === 'string' ? slot.coach_intro.trim() : ''
  if (intro) speak(intro)
  if (slot.slot_type === 'free_jam') {
    router.push('/(tabs)/jam')
    return
  }
  if (slot.slot_type === 'warmup' && slot.warmup_plan?.exercises?.length) {
    router.push('/session/warmup')
    return
  }
  if (slot.slot_type === 'technique') {
    router.push('/session/study')
    return
  }
  router.push('/session/slow')
}

export async function startPracticePlanFromHome(
  router: Router,
  deps: {
    saveLesson: (lesson: LessonJSON) => void
    setLessonSectionIndex: (index: number) => void
  },
  plan: PracticePlanPayload,
): Promise<void> {
  await startActivePracticePlan(plan)
  await navigateToPracticePlanSlot(router, deps, 0)
}

export async function resumePracticePlanFromHome(
  router: Router,
  deps: {
    saveLesson: (lesson: LessonJSON) => void
    setLessonSectionIndex: (index: number) => void
  },
): Promise<void> {
  if (!usePlanStore.getState().currentPlan?.slots.length) {
    const restored = await resumeActivePracticePlan()
    if (!restored) throw new Error('No active practice plan to resume.')
  }
  const state = usePlanStore.getState()
  const plan = state.currentPlan
  if (!plan?.slots.length) throw new Error('No active practice plan to resume.')
  const index = Math.max(0, Math.min(plan.slots.length - 1, state.currentSlotIndex))
  await navigateToPracticePlanSlot(router, deps, index)
}
