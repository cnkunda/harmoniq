import { describe, it, expect } from 'vitest'
import { getChordFunction } from './chordFunction'

describe('getChordFunction', () => {
  describe('Major keys', () => {
    it('returns tonic function for I chord in C major', () => {
      const result = getChordFunction('C major', 'C:maj')
      expect(result).toEqual({
        roman: 'I',
        label: 'Tonic — Home base',
      })
    })

    it('returns subdominant function for IV chord in C major', () => {
      const result = getChordFunction('C major', 'F:maj')
      expect(result).toEqual({
        roman: 'IV',
        label: 'Subdominant — Departure',
      })
    })

    it('returns dominant function for V chord in C major', () => {
      const result = getChordFunction('C major', 'G:maj')
      expect(result).toEqual({
        roman: 'V',
        label: 'Dominant — Tension',
      })
    })

    it('returns supertonic function for ii chord in C major', () => {
      const result = getChordFunction('C major', 'D:min')
      expect(result).toEqual({
        roman: 'ii',
        label: 'Supertonic — Pre-dominant',
      })
    })

    it('returns mediant function for iii chord in C major', () => {
      const result = getChordFunction('C major', 'E:min')
      expect(result).toEqual({
        roman: 'iii',
        label: 'Mediant — Departure',
      })
    })

    it('returns submediant function for vi chord in C major', () => {
      const result = getChordFunction('C major', 'A:min')
      expect(result).toEqual({
        roman: 'vi',
        label: 'Submediant — Return',
      })
    })

    it('returns leading tone function for vii° chord in C major', () => {
      const result = getChordFunction('C major', 'B:dim')
      expect(result).toEqual({
        roman: 'vii°',
        label: 'Leading tone — Tension',
      })
    })

    it('works with sharp keys (G major)', () => {
      const result = getChordFunction('G major', 'G:maj')
      expect(result).toEqual({
        roman: 'I',
        label: 'Tonic — Home base',
      })
    })

    it('works with flat keys (F major)', () => {
      const result = getChordFunction('F major', 'F:maj')
      expect(result).toEqual({
        roman: 'I',
        label: 'Tonic — Home base',
      })
    })
  })

  describe('Minor keys', () => {
    it('returns tonic function for i chord in A minor', () => {
      const result = getChordFunction('A minor', 'A:min')
      expect(result).toEqual({
        roman: 'i',
        label: 'Tonic — Home base',
      })
    })

    it('returns subdominant function for iv chord in A minor', () => {
      const result = getChordFunction('A minor', 'D:min')
      expect(result).toEqual({
        roman: 'iv',
        label: 'Subdominant — Departure',
      })
    })

    it('returns dominant function for v chord in A minor', () => {
      const result = getChordFunction('A minor', 'E:min')
      expect(result).toEqual({
        roman: 'v',
        label: 'Dominant — Tension',
      })
    })

    it('returns supertonic diminished function for ii° chord in A minor', () => {
      const result = getChordFunction('A minor', 'B:dim')
      expect(result).toEqual({
        roman: 'ii°',
        label: 'Supertonic — Tension',
      })
    })

    it('returns mediant function for III chord in A minor', () => {
      const result = getChordFunction('A minor', 'C:maj')
      expect(result).toEqual({
        roman: 'III',
        label: 'Mediant — Departure',
      })
    })

    it('returns submediant function for VI chord in A minor', () => {
      const result = getChordFunction('A minor', 'F:maj')
      expect(result).toEqual({
        roman: 'VI',
        label: 'Submediant — Return',
      })
    })

    it('returns leading tone function for VII chord in A minor', () => {
      const result = getChordFunction('A minor', 'G:maj')
      expect(result).toEqual({
        roman: 'VII',
        label: 'Leading tone — Tension',
      })
    })
  })

  describe('Edge cases', () => {
    it('returns null for no chord symbol', () => {
      const result = getChordFunction('C major', '')
      expect(result).toBeNull()
    })

    it('returns null for N (no chord) symbol', () => {
      const result = getChordFunction('C major', 'N')
      expect(result).toBeNull()
    })

    it('returns null for invalid key', () => {
      const result = getChordFunction('invalid key', 'C:maj')
      expect(result).toBeNull()
    })

    it('returns null for invalid chord symbol', () => {
      const result = getChordFunction('C major', 'X:maj')
      expect(result).toBeNull()
    })
  })
})
