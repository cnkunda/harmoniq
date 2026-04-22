import type { Router } from 'expo-router'

import { speak } from '@/src/audio/voiceCoach'
import { sessionEntryHref } from '@/src/constants/sessionFlow'
import { getLessonByJobId } from '@/src/db/client'
import { usePlanStore } from '@/src/stores/planStore'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
import type { LessonJSON, PracticePlanPayload } from '@/src/types'

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
  setCurrentSlotIndex(slotIndex)
  const intro = typeof slot.coach_intro === 'string' ? slot.coach_intro.trim() : ''
  if (intro) speak(intro)
  const skipTune = useSessionPrefsStore.getState().skipTuneStep

  if (slot.slot_type === 'song_section' && slot.lesson_ref) {
    const lesson = await getLessonByJobId(slot.lesson_ref)
    if (!lesson) {
      throw new Error(`No saved lesson for job ${slot.lesson_ref}. Open the song from Library first.`)
    }
    deps.saveLesson(lesson)
    deps.setLessonSectionIndex(0)
    router.replace(sessionEntryHref(skipTune))
    return
  }
  if (slot.slot_type === 'free_jam') {
    router.replace('/(tabs)/jam')
    return
  }
  if (slot.slot_type === 'warmup' && slot.warmup_plan?.exercises?.length) {
    router.replace('/session/warmup')
    return
  }
  if (slot.slot_type === 'technique') {
    router.replace('/session/study')
    return
  }
  router.replace('/session/slow')
}

export async function startPracticePlanFromHome(
  router: Router,
  deps: {
    saveLesson: (lesson: LessonJSON) => void
    setLessonSectionIndex: (index: number) => void
  },
  plan: PracticePlanPayload,
): Promise<void> {
  usePlanStore.getState().setPlan(plan)
  await navigateToPracticePlanSlot(router, deps, 0)
}
