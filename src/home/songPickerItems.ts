import type { LessonListRow, SessionJournalRow } from '@/src/db/types'
import { sessionOverallAccuracy } from '@/src/home/sessionAccuracy'

export interface SongPickerSource {
  jobId: string
  title: string
  lastPlayedDate: string | null
  accuracy: number | null
  sectionCount: number
}

export interface BuildSongPickerSourcesInput {
  lessons: readonly LessonListRow[]
  sessions: readonly SessionJournalRow[]
  /** Home suggestion title to float to the top (matched case-insensitively). */
  suggestedTitle: string | null
  limit?: number
}

interface EnrichedSong extends SongPickerSource {
  sortTs: number
}

/**
 * Commit 179: order Home's song picker by last played / analyzed date, with the
 * suggested song first. Pure — safe for unit tests.
 */
export function buildSongPickerSources({
  lessons,
  sessions,
  suggestedTitle,
  limit = 3,
}: BuildSongPickerSourcesInput): SongPickerSource[] {
  const normalizedSuggestion = suggestedTitle?.trim().toLowerCase() || null
  const enriched: EnrichedSong[] = lessons.map((lesson) => {
    const title = lesson.song_title?.trim() || 'Untitled song'
    const session =
      sessions.find((row) => row.job_id === lesson.job_id) ??
      sessions.find((row) => row.song_title?.trim().toLowerCase() === title.toLowerCase())
    const playedTs = session ? new Date(session.date).getTime() : 0
    const analyzedTs = new Date(lesson.analyzed_at).getTime()
    return {
      jobId: lesson.job_id,
      title,
      lastPlayedDate: session?.date ?? null,
      accuracy: session ? sessionOverallAccuracy(session) : null,
      sectionCount: lesson.section_count,
      sortTs: Math.max(Number.isNaN(playedTs) ? 0 : playedTs, Number.isNaN(analyzedTs) ? 0 : analyzedTs),
    }
  })

  const suggested = normalizedSuggestion
    ? enriched.find((song) => song.title.toLowerCase() === normalizedSuggestion) ?? null
    : null
  const rest = enriched
    .filter((song) => song.jobId !== suggested?.jobId)
    .sort((a, b) => b.sortTs - a.sortTs || a.title.localeCompare(b.title))

  return (suggested ? [suggested, ...rest] : rest)
    .slice(0, Math.max(0, limit))
    .map((song) => ({
      jobId: song.jobId,
      title: song.title,
      lastPlayedDate: song.lastPlayedDate,
      accuracy: song.accuracy,
      sectionCount: song.sectionCount,
    }))
}
