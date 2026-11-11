import { describe, expect, it } from 'vitest'

import { techniqueLabel, techniquesForSelection } from '@/src/music/techniques'

const notes = [
  { string: 1, fret: 0, midi: 64, technique: [] },
  { string: 2, fret: 8, midi: 67, technique: ['bend'] },
  { string: 3, fret: 9, midi: 64, technique: ['vibrato', 'grace_note'] },
]

describe('techniquesForSelection', () => {
  it('prefers an exact string/fret match', () => {
    expect(techniquesForSelection(notes, { string: 3, fret: 9, midi: 64 })).toEqual([
      'vibrato',
      'grace_note',
    ])
  })

  it('falls back to pitch when string/fret is missing', () => {
    expect(techniquesForSelection(notes, { midi: 67 })).toEqual(['bend'])
  })

  it('returns null when the matched note has no technique', () => {
    expect(techniquesForSelection(notes, { string: 1, fret: 0, midi: 64 })).toBeNull()
  })

  it('returns null for empty inputs', () => {
    expect(techniquesForSelection(null, { midi: 64 })).toBeNull()
    expect(techniquesForSelection(notes, null)).toBeNull()
    expect(techniquesForSelection([], { midi: 64 })).toBeNull()
  })
})

describe('techniqueLabel', () => {
  it('formats known and unknown tags', () => {
    expect(techniqueLabel('grace_note')).toBe('Grace note')
    expect(techniqueLabel('hammer_on')).toBe('Hammer-on')
    expect(techniqueLabel('custom_tag')).toBe('custom tag')
  })
})
