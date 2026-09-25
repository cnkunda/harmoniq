import { describe, it, expect } from 'vitest'
import {
  Interval,
  intervalSemitones,
  intervalName,
  intervalAbbr,
  semitonesToInterval,
} from './intervals'

describe('Interval enum values', () => {
  it('has correct semitone values', () => {
    expect(Interval.Unison).toBe(0)
    expect(Interval.m2).toBe(1)
    expect(Interval.M2).toBe(2)
    expect(Interval.m3).toBe(3)
    expect(Interval.M3).toBe(4)
    expect(Interval.P4).toBe(5)
    expect(Interval.Tritone).toBe(6)
    expect(Interval.P5).toBe(7)
    expect(Interval.m6).toBe(8)
    expect(Interval.M6).toBe(9)
    expect(Interval.m7).toBe(10)
    expect(Interval.M7).toBe(11)
    expect(Interval.Octave).toBe(12)
  })
})

describe('intervalSemitones', () => {
  it('returns the numeric value of the interval', () => {
    expect(intervalSemitones(Interval.Unison)).toBe(0)
    expect(intervalSemitones(Interval.P5)).toBe(7)
    expect(intervalSemitones(Interval.Octave)).toBe(12)
  })
})

describe('intervalName', () => {
  it('returns correct names for all intervals', () => {
    expect(intervalName(Interval.Unison)).toBe('unison')
    expect(intervalName(Interval.m2)).toBe('minor 2nd')
    expect(intervalName(Interval.M2)).toBe('major 2nd')
    expect(intervalName(Interval.m3)).toBe('minor 3rd')
    expect(intervalName(Interval.M3)).toBe('major 3rd')
    expect(intervalName(Interval.P4)).toBe('perfect 4th')
    expect(intervalName(Interval.Tritone)).toBe('tritone')
    expect(intervalName(Interval.P5)).toBe('perfect 5th')
    expect(intervalName(Interval.m6)).toBe('minor 6th')
    expect(intervalName(Interval.M6)).toBe('major 6th')
    expect(intervalName(Interval.m7)).toBe('minor 7th')
    expect(intervalName(Interval.M7)).toBe('major 7th')
    expect(intervalName(Interval.Octave)).toBe('octave')
  })
})

describe('intervalAbbr', () => {
  it('returns correct abbreviations for all intervals', () => {
    expect(intervalAbbr(Interval.Unison)).toBe('P1')
    expect(intervalAbbr(Interval.m2)).toBe('m2')
    expect(intervalAbbr(Interval.M2)).toBe('M2')
    expect(intervalAbbr(Interval.m3)).toBe('m3')
    expect(intervalAbbr(Interval.M3)).toBe('M3')
    expect(intervalAbbr(Interval.P4)).toBe('P4')
    expect(intervalAbbr(Interval.Tritone)).toBe('TT')
    expect(intervalAbbr(Interval.P5)).toBe('P5')
    expect(intervalAbbr(Interval.m6)).toBe('m6')
    expect(intervalAbbr(Interval.M6)).toBe('M6')
    expect(intervalAbbr(Interval.m7)).toBe('m7')
    expect(intervalAbbr(Interval.M7)).toBe('M7')
    expect(intervalAbbr(Interval.Octave)).toBe('P8')
  })
})

describe('semitonesToInterval', () => {
  it('maps valid semitone counts to intervals', () => {
    expect(semitonesToInterval(0)).toBe(Interval.Unison)
    expect(semitonesToInterval(1)).toBe(Interval.m2)
    expect(semitonesToInterval(2)).toBe(Interval.M2)
    expect(semitonesToInterval(3)).toBe(Interval.m3)
    expect(semitonesToInterval(4)).toBe(Interval.M3)
    expect(semitonesToInterval(5)).toBe(Interval.P4)
    expect(semitonesToInterval(6)).toBe(Interval.Tritone)
    expect(semitonesToInterval(7)).toBe(Interval.P5)
    expect(semitonesToInterval(8)).toBe(Interval.m6)
    expect(semitonesToInterval(9)).toBe(Interval.M6)
    expect(semitonesToInterval(10)).toBe(Interval.m7)
    expect(semitonesToInterval(11)).toBe(Interval.M7)
    expect(semitonesToInterval(12)).toBe(Interval.Octave)
  })

  it('returns null for out-of-range values', () => {
    expect(semitonesToInterval(-1)).toBeNull()
    expect(semitonesToInterval(13)).toBeNull()
    expect(semitonesToInterval(1.5)).toBeNull()
  })
})
