import type { LessonJSON } from '@/src/types'

/**
 * Build a lesson-wide, beat-aligned chord events array.
 *
 * Preferred order:
 * 1. If lesson.chord_timeline.events exists and is non-empty, return a sorted copy.
 * 2. Otherwise, merge per-section chord_timeline.events across lesson.sections,
 *    applying a defensive offset when section events look relative to the section start.
 *
 * Returns null when no chord events are available.
 */
export function getLessonWideChordEvents(lesson: LessonJSON | null | undefined)
  : Array<{ timestamp: number; chord: string; confidence?: number }> | null {
  if (!lesson) return null

  const lessonEvents = lesson.chord_timeline?.events
  if (Array.isArray(lessonEvents) && lessonEvents.length > 0) {
    // return a sorted shallow copy to avoid mutating upstream arrays
    return lessonEvents.slice().sort((a, b) => a.timestamp - b.timestamp)
  }

  const sections = lesson.sections ?? []
  const merged: Array<{ timestamp: number; chord: string; confidence?: number }> = []

  for (const rawSec of sections) {
    const sec = rawSec as Record<string, unknown>
    const secTimeline = (sec?.chord_timeline as { events?: Array<{ timestamp: number; chord: string; confidence?: number }> } | undefined)
    if (!secTimeline || !Array.isArray(secTimeline.events) || secTimeline.events.length === 0) continue

    const events = secTimeline.events

    // Defensive detection: if section has a non-zero start time and the events are near-zero
    // we assume the section events are relative and offset them. This is conservative.
    const stRaw = sec.start_time_seconds ?? sec.start_s ?? sec.startTimeSeconds
    const sectionStart = typeof stRaw === 'number' && Number.isFinite(stRaw) ? stRaw : null
    const minEvt = Math.min(...events.map((e) => (typeof e.timestamp === 'number' ? e.timestamp : Infinity)))
    const shouldOffset = sectionStart != null && sectionStart > 0.5 && minEvt < 0.5
    const offset = shouldOffset ? sectionStart : 0

    for (const e of events) {
      if (!e || typeof e.timestamp !== 'number' || !Number.isFinite(e.timestamp)) continue
      merged.push({ timestamp: e.timestamp + offset, chord: e.chord, confidence: e.confidence })
    }
  }

  if (merged.length === 0) return null

  // sort and dedupe (timestamp rounded to ms + chord)
  merged.sort((a, b) => a.timestamp - b.timestamp)
  const out: Array<{ timestamp: number; chord: string; confidence?: number }> = []
  const seen = new Set<string>()
  for (const e of merged) {
    const key = `${e.timestamp.toFixed(3)}:${e.chord ?? ''}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push(e)
  }

  return out
}

export default getLessonWideChordEvents
