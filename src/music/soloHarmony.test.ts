import { describe, expect, it } from 'vitest'

import {
  barScopeForTime,
  findHarmonizedNoteForSelection,
  formatHarmonyPercents,
  parseHarmonizedSolo,
  parsePerBarAnalysis,
} from './soloHarmony'
import type {
  BarScope,
  ChordToneAnalysis,
  HarmonizedSoloNote,
  HarmonizedSoloNotes,
} from '@/src/types/soloHarmony'

function analysis(overrides: Partial<ChordToneAnalysis> = {}): ChordToneAnalysis {
  return {
    scale_degree: 1,
    scale_degree_name: 'R',
    chord_tone_type: 'chord_tone',
    semitone_distance: 0,
    ...overrides,
  }
}

function note(overrides: Partial<HarmonizedSoloNote> = {}): HarmonizedSoloNote {
  return {
    start_time: 0,
    duration: 0.25,
    pitch: 64,
    velocity: 90,
    chord: 'C:maj',
    chord_analysis: analysis(),
    ...overrides,
  }
}

function harmonized(notes: HarmonizedSoloNote[]): HarmonizedSoloNotes {
  return {
    notes,
    note_count: notes.length,
    chord_tone_pct: 0,
    tension_note_pct: 0,
    chromatic_pct: 0,
  }
}

function bar(overrides: Partial<BarScope> = {}): BarScope {
  return {
    bar_index: 0,
    start_time: 0,
    end_time: 2,
    chord: 'C:maj',
    suggested_scales: ['C major pentatonic'],
    primary_position: 'position 1 (CAGED: E-form)',
    notes: [],
    ...overrides,
  }
}

describe('parseHarmonizedSolo', () => {
  it('round-trips a valid payload', () => {
    const parsed = parseHarmonizedSolo({
      notes: [
        {
          start_time: 0.5,
          duration: 0.25,
          pitch: 64,
          velocity: 90,
          chord: 'C:maj',
          chord_analysis: {
            scale_degree: 3,
            scale_degree_name: '3',
            chord_tone_type: 'chord_tone',
            semitone_distance: 4,
          },
        },
        { start_time: 1, duration: 0.5, pitch: 65, velocity: 80, chord: null, chord_analysis: null },
      ],
      note_count: 2,
      chord_tone_pct: 0.5,
      tension_note_pct: 0.25,
      chromatic_pct: 0.25,
    })
    expect(parsed).not.toBeNull()
    expect(parsed!.notes).toHaveLength(2)
    expect(parsed!.notes[0]!.chord_analysis).toEqual({
      scale_degree: 3,
      scale_degree_name: '3',
      chord_tone_type: 'chord_tone',
      semitone_distance: 4,
    })
    expect(parsed!.notes[1]).toEqual({
      start_time: 1,
      duration: 0.5,
      pitch: 65,
      velocity: 80,
      chord: null,
      chord_analysis: null,
    })
    expect(parsed!.chord_tone_pct).toBe(0.5)
    expect(parsed!.tension_note_pct).toBe(0.25)
    expect(parsed!.chromatic_pct).toBe(0.25)
  })

  it('returns null for non-objects, missing notes, or non-array notes', () => {
    expect(parseHarmonizedSolo(null)).toBeNull()
    expect(parseHarmonizedSolo(undefined)).toBeNull()
    expect(parseHarmonizedSolo(42)).toBeNull()
    expect(parseHarmonizedSolo('harmonized')).toBeNull()
    expect(parseHarmonizedSolo({})).toBeNull()
    expect(parseHarmonizedSolo({ notes: 'nope' })).toBeNull()
  })

  it('keeps an empty notes array as a valid object distinct from null', () => {
    const parsed = parseHarmonizedSolo({ notes: [] })
    expect(parsed).not.toBeNull()
    expect(parsed!.notes).toEqual([])
  })

  it('normalizes missing aggregates to 0 and note_count to notes length', () => {
    const parsed = parseHarmonizedSolo({ notes: [note()] })
    expect(parsed!.chord_tone_pct).toBe(0)
    expect(parsed!.tension_note_pct).toBe(0)
    expect(parsed!.chromatic_pct).toBe(0)
    expect(parsed!.note_count).toBe(1)
  })

  it('drops malformed note entries but keeps valid ones', () => {
    const parsed = parseHarmonizedSolo({
      notes: [null, 7, { start_time: 1 }, { start_time: 1, pitch: 'E' }, { start_time: 1, pitch: 64 }],
    })
    expect(parsed!.notes).toHaveLength(1)
    expect(parsed!.notes[0]!.pitch).toBe(64)
  })

  it('coerces a malformed chord_analysis to null without dropping the note', () => {
    const parsed = parseHarmonizedSolo({
      notes: [
        {
          start_time: 1,
          pitch: 64,
          chord_analysis: { chord_tone_type: 'bogus', scale_degree_name: 'R', semitone_distance: 0 },
        },
      ],
    })
    expect(parsed!.notes).toHaveLength(1)
    expect(parsed!.notes[0]!.chord_analysis).toBeNull()
  })

  it('clamps out-of-range percentages into 0-1', () => {
    const parsed = parseHarmonizedSolo({
      notes: [],
      chord_tone_pct: 1.4,
      tension_note_pct: -0.2,
      chromatic_pct: 0.5,
    })
    expect(parsed!.chord_tone_pct).toBe(1)
    expect(parsed!.tension_note_pct).toBe(0)
    expect(parsed!.chromatic_pct).toBe(0.5)
  })
})

describe('parsePerBarAnalysis', () => {
  it('parses valid bars and defaults malformed fields', () => {
    const parsed = parsePerBarAnalysis([
      {
        bar_index: 0,
        start_time: 0,
        end_time: 2,
        chord: 'C:maj',
        suggested_scales: ['C major pentatonic', 7],
        primary_position: 'position 1 (CAGED: E-form)',
        notes: [0, 1, -3, 1.5],
      },
    ])
    expect(parsed).not.toBeNull()
    expect(parsed![0]!.suggested_scales).toEqual(['C major pentatonic'])
    expect(parsed![0]!.notes).toEqual([0, 1])
    expect(parsed![0]!.chord).toBe('C:maj')
  })

  it('returns null for non-arrays', () => {
    expect(parsePerBarAnalysis(null)).toBeNull()
    expect(parsePerBarAnalysis(undefined)).toBeNull()
    expect(parsePerBarAnalysis({})).toBeNull()
    expect(parsePerBarAnalysis('bars')).toBeNull()
  })

  it('drops malformed bar entries and falls back to the array index for bar_index', () => {
    const parsed = parsePerBarAnalysis([{ start_time: 0, end_time: 2 }, null, { end_time: 4 }])
    expect(parsed).toHaveLength(1)
    expect(parsed![0]!.bar_index).toBe(0)
    expect(parsed![0]!.suggested_scales).toEqual([])
    expect(parsed![0]!.primary_position).toBeNull()
  })
})

describe('barScopeForTime', () => {
  it('matches by time range even when bar_index misaligns with bar_timestamps', () => {
    const bars = [
      bar({ bar_index: 0, start_time: 0.6, end_time: 2.6 }),
      bar({ bar_index: 1, start_time: 2.6, end_time: 4.6 }),
    ]
    expect(barScopeForTime(bars, 0.3)).toBeNull()
    expect(barScopeForTime(bars, 0.6)?.bar_index).toBe(0)
    expect(barScopeForTime(bars, 2.6)?.bar_index).toBe(1)
    expect(barScopeForTime(bars, 4.6)).toBeNull()
  })

  it('returns null for no match, empty, missing, or non-finite inputs', () => {
    expect(barScopeForTime([bar({ start_time: 0, end_time: 2 })], 5)).toBeNull()
    expect(barScopeForTime([], 1)).toBeNull()
    expect(barScopeForTime(null, 1)).toBeNull()
    expect(barScopeForTime(undefined, 1)).toBeNull()
    expect(barScopeForTime([bar()], Number.NaN)).toBeNull()
  })
})

describe('findHarmonizedNoteForSelection', () => {
  it('returns the bar-scoped note via the bar note indices', () => {
    const notes = [note({ start_time: 5, pitch: 67 }), note({ start_time: 1, pitch: 67 })]
    const bars = [
      bar({ start_time: 0, end_time: 2, notes: [1] }),
      bar({ bar_index: 1, start_time: 2, end_time: 4, notes: [0] }),
    ]
    const found = findHarmonizedNoteForSelection(harmonized(notes), bars, { midi: 67, timeSec: 1 })
    expect(found?.start_time).toBe(1)
  })

  it('tie-breaks repeated pitches in the same bar to the earliest start_time', () => {
    const notes = [note({ start_time: 1.4, pitch: 67 }), note({ start_time: 0.5, pitch: 67 })]
    const bars = [bar({ start_time: 0, end_time: 2, notes: [0, 1] })]
    const found = findHarmonizedNoteForSelection(harmonized(notes), bars, { midi: 67, timeSec: 1 })
    expect(found?.start_time).toBe(0.5)
  })

  it('falls back to a unique pitch match when no bar resolves', () => {
    const notes = [note({ start_time: 3, pitch: 62 })]
    const found = findHarmonizedNoteForSelection(harmonized(notes), [], { midi: 62 })
    expect(found?.pitch).toBe(62)
  })

  it('falls back to the nearest onset for repeated pitches when time is known', () => {
    const notes = [note({ start_time: 1, pitch: 62 }), note({ start_time: 7, pitch: 62 })]
    const found = findHarmonizedNoteForSelection(harmonized(notes), null, { midi: 62, timeSec: 6 })
    expect(found?.start_time).toBe(7)
  })

  it('refuses ambiguous repeated pitches without a time', () => {
    const notes = [note({ pitch: 62 }), note({ start_time: 2, pitch: 62 })]
    expect(findHarmonizedNoteForSelection(harmonized(notes), null, { midi: 62 })).toBeNull()
  })

  it('returns null without a midi or without data', () => {
    expect(findHarmonizedNoteForSelection(harmonized([note()]), null, {})).toBeNull()
    expect(findHarmonizedNoteForSelection(null, null, { midi: 64 })).toBeNull()
    expect(findHarmonizedNoteForSelection(undefined, null, { midi: 64 })).toBeNull()
    expect(findHarmonizedNoteForSelection(harmonized([]), null, { midi: 64 })).toBeNull()
  })

  it('skips out-of-range bar note indices', () => {
    const notes = [note({ start_time: 1, pitch: 67 })]
    const bars = [bar({ start_time: 0, end_time: 2, notes: [9] })]
    const found = findHarmonizedNoteForSelection(harmonized(notes), bars, { midi: 67, timeSec: 1 })
    expect(found?.start_time).toBe(1)
  })
})

describe('formatHarmonyPercents', () => {
  it('rounds fractions to whole percents', () => {
    const result = formatHarmonyPercents({
      notes: [],
      note_count: 0,
      chord_tone_pct: 0.375,
      tension_note_pct: 0.453,
      chromatic_pct: 0.172,
    })
    expect(result).toEqual({ chordTone: 38, tension: 45, chromatic: 17 })
  })

  it('handles all-zero aggregates', () => {
    expect(formatHarmonyPercents(harmonized([]))).toEqual({
      chordTone: 0,
      tension: 0,
      chromatic: 0,
    })
  })
})
