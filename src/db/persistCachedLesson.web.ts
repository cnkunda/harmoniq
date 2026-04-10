import { getHarmoniqIdbHandle, idbClearLessonCache, idbWriteLessonCache } from '@/src/db/idbWeb'
import type { LessonJSON } from '@/src/types'

export async function persistCachedLessonIfWeb(lesson: LessonJSON): Promise<void> {
  await idbWriteLessonCache(getHarmoniqIdbHandle(), lesson)
}

export async function clearCachedLessonIfWeb(): Promise<void> {
  await idbClearLessonCache(getHarmoniqIdbHandle())
}
