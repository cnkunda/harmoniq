import { describe, expect, it } from 'vitest'

import { deriveLessonBed, lessonChordToSymbol, splitLessonKey, type LessonLike } from '@/src/jam/lessonBed'

const lesson: LessonLike = {
  key: 'A minor',
  tempo: 72.4,
  song_title: 'Test Song',
  chord_timeline: {
    events: [
      { timestamp: 0, chord: 'A:min' },
      { timestamp: 1, chord: 'A:min' },
      { timestamp: 2, chord: 'F:maj' },
      { timestamp: 3, chord: 'C:maj' },
      { timestamp: 4, chord: 'G:7' },
      { timestamp: 6, chord: 'N' },
    ],
  },
  sections: [
    { label: 'Intro', start_time_seconds: 0, end_time_seconds: 2 },
    { label: 'Verse', start_time_seconds: 2, end_time_seconds: 5 },
  ],
}

describe('lessonChordToSymbol', () => {
  it('maps lesson chord ids to jam symbols', () => {
    expect(lessonChordToSymbol('C:maj')).toBe('C')
    expect(lessonChordToSymbol('A:min')).toBe('Am')
    expect(lessonChordToSymbol('D:maj7')).toBe('Dmaj7')
    expect(lessonChordToSymbol('E:min7')).toBe('Em7')
    expect(lessonChordToSymbol('G:7')).toBe('G7')
  })

  it('drops no-chord and malformed values', () => {
    expect(lessonChordToSymbol('N')).toBeNull()
    expect(lessonChordToSymbol('')).toBeNull()
    expect(lessonChordToSymbol('H:min')).toBeNull()
    expect(lessonChordToSymbol('C:weird')).toBeNull()
  })
})

describe('splitLessonKey', () => {
  it('parses minor and major keys', () => {
    expect(splitLessonKey('A minor')).toEqual({ root: 'A', mode: 'minor' })
    expect(splitLessonKey('G major')).toEqual({ root: 'G', mode: 'major' })
  })

  it('defaults to major when mode is missing', () => {
    expect(splitLessonKey('C')).toEqual({ root: 'C', mode: 'major' })
  })
})

describe('deriveLessonBed', () => {
  it('uses section bounds and collapses consecutive duplicates', () => {
    const bed = deriveLessonBed(lesson, 1)
    expect(bed.progression).toEqual(['F', 'C', 'G7'])
    expect(bed.sectionLabel).toBe('Verse')
    expect(bed.musicalKey).toBe('A minor')
    expect(bed.bpm).toBe(72)
  })

  it('includes intro chords when the intro is selected', () => {
    const bed = deriveLessonBed(lesson, 0)
    expect(bed.progression).toEqual(['Am'])
  })

  it('falls back safely without sections or events', () => {
    const bed = deriveLessonBed({ key: null, tempo: null, song_title: null }, 0)
    expect(bed.progression).toEqual([])
    expect(bed.musicalKey).toBe('A major')
    expect(bed.bpm).toBeNull()
    expect(bed.songTitle).toBe('Current song')
  })
})
