import type { Href } from 'expo-router'

import { sessionEntryHrefWithMoodCheck } from '@/src/constants/sessionFlow'
import { upsertLessonFromAnalysis } from '@/src/db/client'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
import type { LessonJSON } from '@/src/types'

import { DEMO_LESSON_JOB_ID } from './constants'
import { getDemoLesson } from './demoLesson'

type SaveLesson = (lesson: LessonJSON) => void
type SetLessonSectionIndex = (index: number) => void

/** Loads demo lesson in-memory only (not persisted to DB), loads the session store, opens Listen. */
export async function startDemoSession(
  router: { push: (href: Href) => void },
  saveLesson: SaveLesson,
  setLessonSectionIndex: SetLessonSectionIndex,
): Promise<void> {
  const lesson = getDemoLesson()
  saveLesson(lesson)
  setLessonSectionIndex(0)
  // Skip database persistence for demo lesson - it's in-memory only
  if (lesson.job_id !== DEMO_LESSON_JOB_ID) {
    await upsertLessonFromAnalysis(lesson)
  }
  const href = await sessionEntryHrefWithMoodCheck(useSessionPrefsStore.getState().skipTuneStep)
  router.push(href as Href)
}
