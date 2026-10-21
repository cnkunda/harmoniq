import type { AnalyticsEventRow, UserFeedbackStats } from '@/src/db/types'

export type EngagementMetrics = {
  totalSessions: number
  completedSessions: number
  completionRate: number
  averageSessionLengthSec: number
  totalPlayAlongSec: number
  averagePlayAlongSec: number
  /** Blank/null song titles are ignored here; counted in `sessionsWithoutSongTitle`. */
  mostPracticedSongs: Array<{ song_title: string; count: number }>
  mostCorrectedChords: Array<{ chord: string; count: number }>
  /** Oldest-to-newest, 7 local calendar days ending on `now`. */
  sessionsByDay: Array<{ date: string; count: number }>
  /** Sum of `sessionsByDay` (rolling 7 local days). */
  sessionsThisWeek: number
  sessionsWithoutSongTitle: number
}

type PayloadRecord = Record<string, unknown>

function parsePayload(raw: string): PayloadRecord | null {
  if (!raw.trim()) return null
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    return parsed as PayloadRecord
  } catch {
    return null
  }
}

function finiteNonNegative(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null
}

function localDayKey(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function safeDate(timestamp: string): Date | null {
  const date = new Date(timestamp)
  return Number.isNaN(date.getTime()) ? null : date
}

/**
 * Pure engagement aggregation over local analytics rows + feedback stats.
 * Malformed `payload_json` values are ignored rather than thrown.
 */
export function computeEngagementMetrics(
  events: AnalyticsEventRow[],
  feedbackStats: UserFeedbackStats,
  now: Date,
): EngagementMetrics {
  let totalSessions = 0
  let completedSessions = 0
  let sessionsWithoutSongTitle = 0
  let sessionDurationTotal = 0
  let sessionDurationCount = 0
  let totalPlayAlongSec = 0
  let playAlongCount = 0
  const songCounts = new Map<string, number>()
  const dayCounts = new Map<string, number>()

  const dayKeys: string[] = []
  for (let offset = 6; offset >= 0; offset -= 1) {
    const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() - offset)
    const key = localDayKey(day)
    dayKeys.push(key)
    dayCounts.set(key, 0)
  }

  for (const event of events) {
    const payload = parsePayload(event.payload_json)

    if (event.event_type === 'session_start') {
      totalSessions += 1
      const title = payload && typeof payload.song_title === 'string' ? payload.song_title.trim() : ''
      if (title) {
        songCounts.set(title, (songCounts.get(title) ?? 0) + 1)
      } else {
        sessionsWithoutSongTitle += 1
      }
      const date = safeDate(event.timestamp)
      if (date) {
        const key = localDayKey(date)
        if (dayCounts.has(key)) dayCounts.set(key, (dayCounts.get(key) ?? 0) + 1)
      }
      continue
    }

    if (event.event_type === 'session_complete') {
      completedSessions += 1
      const duration = payload ? finiteNonNegative(payload.duration_sec) : null
      if (duration != null) {
        sessionDurationTotal += duration
        sessionDurationCount += 1
      }
      continue
    }

    if (event.event_type === 'play_along_complete') {
      const duration = payload ? finiteNonNegative(payload.duration_sec) : null
      if (duration != null) {
        totalPlayAlongSec += duration
        playAlongCount += 1
      }
    }
  }

  const mostPracticedSongs = [...songCounts.entries()]
    .map(([song_title, count]) => ({ song_title, count }))
    .sort((a, b) => b.count - a.count || a.song_title.localeCompare(b.song_title))
    .slice(0, 5)

  const sessionsByDay = dayKeys.map((date) => ({ date, count: dayCounts.get(date) ?? 0 }))

  return {
    totalSessions,
    completedSessions,
    completionRate: totalSessions > 0 ? completedSessions / totalSessions : 0,
    averageSessionLengthSec: sessionDurationCount > 0 ? sessionDurationTotal / sessionDurationCount : 0,
    totalPlayAlongSec,
    averagePlayAlongSec: playAlongCount > 0 ? totalPlayAlongSec / playAlongCount : 0,
    mostPracticedSongs,
    mostCorrectedChords: [...feedbackStats.most_corrected_chords],
    sessionsByDay,
    sessionsThisWeek: sessionsByDay.reduce((sum, day) => sum + day.count, 0),
    sessionsWithoutSongTitle,
  }
}
