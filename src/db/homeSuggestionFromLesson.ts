import type { HomeSuggestion } from '@/src/db/types'
import type { LessonJSON } from '@/src/types'

/** When there is no session journal yet but the user has an analyzed lesson in memory or cache. */
export function tryHomeSuggestionFromLesson(
  lesson: LessonJSON | null | undefined,
): Extract<HomeSuggestion, { kind: 'active_lesson' }> | null {
  if (!lesson) return null
  const title = typeof lesson.song_title === 'string' ? lesson.song_title.trim() : ''
  if (!title) return null
  const section0 = lesson.sections?.[0]
  const sectionLabel =
    section0 && typeof section0 === 'object' && typeof (section0 as Record<string, unknown>).label === 'string'
      ? ((section0 as Record<string, unknown>).label as string)
      : null
  return {
    kind: 'active_lesson',
    song: {
      song_title: title,
      artist: typeof lesson.artist === 'string' ? lesson.artist : null,
      section_label: sectionLabel,
      date: new Date().toISOString(),
    },
  }
}
