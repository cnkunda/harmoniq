import type { Href } from 'expo-router'

import { upsertLessonFromAnalysis } from '@/src/db/client'
import { sessionEntryHref } from '@/src/constants/sessionFlow'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
import type { LessonJSON } from '@/src/types'

import { getDemoLesson } from './demoLesson'

type SaveLesson = (lesson: LessonJSON) => void
type SetLessonSectionIndex = (index: number) => void

/** Persists demo to the library, loads the session store, opens Listen. */
export async function startDemoSession(
  router: { push: (href: Href) => void },
  saveLesson: SaveLesson,
  setLessonSectionIndex: SetLessonSectionIndex,
): Promise<void> {
  const lesson = getDemoLesson()
  saveLesson(lesson)
  setLessonSectionIndex(0)
  await upsertLessonFromAnalysis(lesson)
  router.push(sessionEntryHref(useSessionPrefsStore.getState().skipTuneStep) as Href)
}
