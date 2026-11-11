import { describe, expect, it } from 'vitest'

import { MAX_PROGRESSION_CHORDS, normalizeChordSymbol, parseProgressionInput } from '@/src/jam/progression'

describe('parseProgressionInput', () => {
  it('parses space-separated chords', () => {
    expect(parseProgressionInput('Am F C G')).toEqual(['Am', 'F', 'C', 'G'])
  })

  it('accepts commas, pipes, and slashes as separators', () => {
    expect(parseProgressionInput('Am, F | C / G')).toEqual(['Am', 'F', 'C', 'G'])
  })

  it('drops invalid tokens', () => {
    expect(parseProgressionInput('Am hello F# 13 Cmaj7')).toEqual(['Am', 'F#', 'Cmaj7'])
  })

  it('normalizes root case and quality case', () => {
    expect(parseProgressionInput('am7 D7 cmaj7')).toEqual(['Am7', 'D7', 'Cmaj7'])
  })

  it('caps the number of chords', () => {
    const input = Array.from({ length: 30 }, () => 'C').join(' ')
    expect(parseProgressionInput(input)).toHaveLength(MAX_PROGRESSION_CHORDS)
  })

  it('returns empty for empty input', () => {
    expect(parseProgressionInput('   ')).toEqual([])
  })

  it('exports the normalizer for stable display', () => {
    expect(normalizeChordSymbol('bb7')).toBe('Bb7')
  })
})
