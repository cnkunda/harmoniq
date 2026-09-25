import { describe, expect, it } from 'vitest'
import getLessonWideChordEvents from './lessonChordTimeline'

const mkLesson = (sections: any[] = [], lessonEvents: any[] | null = null) => {
  const l: any = {}
  if (sections.length) l.sections = sections
  if (lessonEvents) l.chord_timeline = { events: lessonEvents }
  return l
}

describe('getLessonWideChordEvents', () => {
  it('returns lesson-level timeline when present', () => {
    const le = [{ timestamp: 0, chord: 'C' }, { timestamp: 2, chord: 'G' }]
    const out = getLessonWideChordEvents(mkLesson([], le))
    expect(out).not.toBeNull()
    expect(out!.map((e) => e.chord)).toEqual(['C', 'G'])
  })

  it('merges per-section events when lesson-level missing', () => {
    const s1 = { start_time_seconds: 0, chord_timeline: { events: [{ timestamp: 0, chord: 'Am' }] } }
    const s2 = { start_time_seconds: 10, chord_timeline: { events: [{ timestamp: 0, chord: 'F' }, { timestamp: 2, chord: 'G' }] } }
    const out = getLessonWideChordEvents(mkLesson([s1, s2]))
    expect(out).not.toBeNull()
    // s2 events should be offset by its start_time_seconds (10)
    expect(out!.map((e) => e.chord)).toEqual(['Am', 'F', 'G'])
    expect(out![1]!.timestamp).toBeCloseTo(10)
  })

  it('dedupes identical events', () => {
    const s1 = { start_time_seconds: 0, chord_timeline: { events: [{ timestamp: 0, chord: 'D' }] } }
    const s2 = { start_time_seconds: 0, chord_timeline: { events: [{ timestamp: 0, chord: 'D' }] } }
    const out = getLessonWideChordEvents(mkLesson([s1, s2]))
    expect(out).not.toBeNull()
    expect(out!.length).toBe(1)
    expect(out![0]!.chord).toBe('D')
  })

  it('returns null when no events', () => {
    expect(getLessonWideChordEvents(mkLesson([], null))).toBeNull()
    expect(getLessonWideChordEvents(mkLesson([], []))).toBeNull()
    expect(getLessonWideChordEvents(null)).toBeNull()
  })
})
