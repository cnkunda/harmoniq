import { describe, it, expect } from 'vitest'
import { findProgressions, COMMON_PROGRESSIONS } from './progressionAnalysis'

describe('findProgressions', () => {
  it('finds ii-V-I starting at bar 0 in a 5-bar progression', () => {
    const result = findProgressions(['ii', 'V', 'I', 'IV', 'V'])
    const match = result.find(m => m.pattern.name === 'ii-V-I')
    expect(match).toBeDefined()
    expect(match!.startBar).toBe(0)
    expect(match!.endBar).toBe(2)
    expect(match!.matchedNumerals).toEqual(['ii', 'V', 'I'])
  })

  it('finds I-V-vi-IV starting at bar 0 in a 6-bar progression', () => {
    const result = findProgressions(['I', 'V', 'vi', 'IV', 'I', 'V'])
    const match = result.find(m => m.pattern.name === 'I-V-vi-IV')
    expect(match).toBeDefined()
    expect(match!.startBar).toBe(0)
    expect(match!.endBar).toBe(3)
  })

  it('finds I-IV-V at bars 0-2 in a 4-bar progression', () => {
    const result = findProgressions(['I', 'IV', 'V', 'I'])
    const match = result.find(m => m.pattern.name === 'I-IV-V')
    expect(match).toBeDefined()
    expect(match!.startBar).toBe(0)
    expect(match!.endBar).toBe(2)
  })

  it('returns empty array for empty input', () => {
    const result = findProgressions([])
    expect(result).toEqual([])
  })

  it('returns no matches for non-matching roman numerals', () => {
    const result = findProgressions(['I', 'I', 'I', 'I'])
    expect(result).toEqual([])
  })

  it('returns empty array when fewer bars than pattern length', () => {
    const result = findProgressions(['ii', 'V'])
    expect(result).toEqual([])
  })

  it('matches V7 against V in the pattern', () => {
    const result = findProgressions(['ii', 'V7', 'I'])
    const match = result.find(m => m.pattern.name === 'ii-V-I')
    expect(match).toBeDefined()
  })

  it('matches case-insensitively', () => {
    const result = findProgressions(['ii', 'v', 'i'])
    const match = result.find(m => m.pattern.name === 'ii-V-I')
    expect(match).toBeDefined()
  })

  it('finds multiple non-overlapping matches', () => {
    const result = findProgressions(['ii', 'V', 'I', 'ii', 'V', 'I'])
    const iiVIMatches = result.filter(m => m.pattern.name === 'ii-V-I')
    expect(iiVIMatches).toHaveLength(2)
    expect(iiVIMatches[0].startBar).toBe(0)
    expect(iiVIMatches[1].startBar).toBe(3)
  })

  it('matches patterns with custom patterns argument', () => {
    const customPatterns = [{
      name: 'custom',
      description: 'Test pattern',
      romanPattern: ['I', 'IV'],
      minLength: 2,
      style: 'test',
    }]
    const result = findProgressions(['I', 'IV', 'V', 'I'], customPatterns)
    expect(result).toHaveLength(1)
    expect(result[0].pattern.name).toBe('custom')
    expect(result[0].startBar).toBe(0)
    expect(result[0].endBar).toBe(1)
  })

  it('matches ii°-V-i in minor key', () => {
    const result = findProgressions(['ii°', 'V', 'i', 'iv', 'V', 'i'])
    const match = result.find(m => m.pattern.name === 'ii°-V-i')
    expect(match).toBeDefined()
    expect(match!.startBar).toBe(0)
    expect(match!.endBar).toBe(2)
  })

  it('matches iii-vi-ii-V jazz turnaround', () => {
    const result = findProgressions(['iii', 'vi', 'ii', 'V', 'I'])
    const match = result.find(m => m.pattern.name === 'iii-vi-ii-V')
    expect(match).toBeDefined()
    expect(match!.startBar).toBe(0)
    expect(match!.endBar).toBe(3)
  })

  it('does not treat ii° as matching ii-V-I', () => {
    const result = findProgressions(['ii°', 'V', 'i'])
    expect(result.some(m => m.pattern.name === 'ii-V-I')).toBe(false)
  })

  it('also finds overlapping vi-IV-I-V when I-V-vi-IV is also present', () => {
    const result = findProgressions(['I', 'V', 'vi', 'IV', 'I', 'V'])
    const viIVIVMatch = result.find(m => m.pattern.name === 'vi-IV-I-V')
    expect(viIVIVMatch).toBeDefined()
    expect(viIVIVMatch!.startBar).toBe(2)
    expect(viIVIVMatch!.endBar).toBe(5)
  })
})
