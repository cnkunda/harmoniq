import { describe, expect, it } from 'vitest'

import { fingerSuggestion, suggestFingerings } from './fingerSuggestion'

describe('fingerSuggestion', () => {
  it('open string', () => {
    expect(fingerSuggestion({ fret: 0 })).toContain('Open string')
  })

  it('frets 1–4 map to fingers', () => {
    expect(fingerSuggestion({ fret: 1 })).toContain('Index')
    expect(fingerSuggestion({ fret: 2 })).toContain('Middle')
    expect(fingerSuggestion({ fret: 3 })).toContain('Ring')
    expect(fingerSuggestion({ fret: 4 })).toContain('Pinky')
  })

  it('high-fret octave / shift guidance', () => {
    const out = fingerSuggestion({ fret: 17, stringIndex: 2 })
    expect(out.length).toBeGreaterThan(10)
    expect(out.toLowerCase()).toMatch(/high|fret|shift|hand/i)
  })
})

describe('suggestFingerings', () => {
  it('returns alternates when another same-pitch cell is within the neck window', () => {
    const primary = { row: 0, fret: 3 }
    const samePitch = [
      primary,
      { row: 1, fret: 8 },
      { row: 2, fret: 12 },
    ]
    const out = suggestFingerings(primary, samePitch)
    expect(out.primary.length).toBeGreaterThan(5)
    expect(out.alternates.length).toBeGreaterThanOrEqual(1)
  })
})
