import { API_BASE_URL } from '@/src/config'
import type { LessonJSON } from '@/src/types'

/** Build fetch URL for a stem path from `LessonJSON.stems` (server-relative POSIX path). */
export function lessonStemUrl(relPath: string): string {
  const rel = relPath.replace(/\\/g, '/').replace(/^\//, '')
  const q = encodeURIComponent(rel)
  return `${API_BASE_URL}/lesson-file?rel=${q}`
}

export function parseSectionRecord(section: Record<string, unknown> | undefined): {
  label: string
  startTimeSeconds: number | null
} {
  if (!section) {
    return { label: 'Section', startTimeSeconds: null }
  }
  const labelRaw = section.label
  const label = typeof labelRaw === 'string' && labelRaw.trim() ? labelRaw.trim() : 'Section'
  const st =
    section.start_time_seconds ?? section.start_s ?? section.startTimeSeconds
  const startTimeSeconds =
    typeof st === 'number' && Number.isFinite(st) ? Math.max(0, st) : null
  return { label, startTimeSeconds }
}

/**
 * Resolve seek time for section `index` using explicit start times, then bar grid, then beats.
 */
export function sectionSeekSeconds(lesson: LessonJSON, index: number): number {
  const sections = lesson.sections ?? []
  const sec = sections[index] as Record<string, unknown> | undefined
  const { startTimeSeconds } = parseSectionRecord(sec)
  if (startTimeSeconds != null) {
    return startTimeSeconds
  }

  const bars = lesson.bar_timestamps ?? []
  if (bars.length > 0) {
    if (index <= 0) return Math.max(0, bars[0] ?? 0)
    if (index < bars.length) return Math.max(0, bars[index]!)
    return Math.max(0, bars[bars.length - 1] ?? 0)
  }

  const beats = lesson.beat_grid ?? []
  const n = sections.length || 1
  if (beats.length > 0) {
    const bi = Math.min(Math.max(0, index), beats.length - 1)
    return Math.max(0, beats[bi] ?? 0)
  }

  return 0
}
