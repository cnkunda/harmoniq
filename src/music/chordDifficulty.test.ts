import { describe, expect, it } from 'vitest'

import { chordDifficulty } from '@/src/music/chordDifficulty'

describe('chordDifficulty', () => {
  it('marks open triads as easy', () => {
    expect(chordDifficulty('C')).toBe('easy')
    expect(chordDifficulty('Am')).toBe('easy')
    expect(chordDifficulty('G5')).toBe('easy')
  })

  it('marks common sevenths and suspensions as medium', () => {
    expect(chordDifficulty('G7')).toBe('medium')
    expect(chordDifficulty('Cmaj7')).toBe('medium')
    expect(chordDifficulty('Dsus4')).toBe('medium')
    expect(chordDifficulty('Bdim7')).toBe('medium')
  })

  it('marks extensions, alterations, and slash chords as hard', () => {
    expect(chordDifficulty('E9')).toBe('hard')
    expect(chordDifficulty('C7b5')).toBe('hard')
    expect(chordDifficulty('Dm7/G')).toBe('hard')
    expect(chordDifficulty('Cadd9')).toBe('hard')
  })

  it('falls back safely for non-standard symbols', () => {
    expect(chordDifficulty('')).toBe('medium')
    expect(chordDifficulty('N')).toBe('medium')
  })
})
