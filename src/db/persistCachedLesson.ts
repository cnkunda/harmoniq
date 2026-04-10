import type { LessonJSON } from '@/src/types'

/** Native / non-web: no-op (lesson lives in memory only). */
export async function persistCachedLessonIfWeb(_lesson: LessonJSON): Promise<void> {}

export async function clearCachedLessonIfWeb(): Promise<void> {}
