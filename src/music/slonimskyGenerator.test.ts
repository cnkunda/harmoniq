import { describe, it, expect } from 'vitest'

import {
  generateSlonimskyPattern,
  generateDailyWarmup,
  getSlonimskyPatternsByDifficulty,
  dailySeedFromDate,
} from '@/src/music/slonimskyGenerator'

const VALID_FAMILIES = ['interpolation', 'infrapolation', 'tritone_sequence', 'compound'] as const

function isValidVariant(v: string): boolean {
  return v === 'primary' || v === 'secondary'
}

function isValidFinger(f: unknown): boolean {
  return f === undefined || (typeof f === 'number' && [1, 2, 3, 4].includes(f))
}

describe('generateSlonimskyPattern', () => {
  for (const family of VALID_FAMILIES) {
    it(`returns a valid SlonimskyPattern for family "${family}"`, () => {
      const pattern = generateSlonimskyPattern(family, 42)
      expect(pattern).not.toBeNull()
      expect(pattern!.id).toBeTruthy()
      expect(pattern!.name).toBeTruthy()
      expect(pattern!.description).toBeTruthy()
      expect(pattern!.techniqueTags.length).toBeGreaterThan(0)
      expect(pattern!.family).toBe(family)
      expect(pattern!.defaultDurationSeconds).toBeGreaterThan(0)
      expect(pattern!.difficulty).toBeGreaterThanOrEqual(1)
      expect(pattern!.difficulty).toBeLessThanOrEqual(3)
      expect(typeof pattern!.isOpener).toBe('boolean')
    })

    it(`has valid fretboardCells for "${family}"`, () => {
      const pattern = generateSlonimskyPattern(family, 42)
      expect(pattern!.fretboardCells.length).toBeGreaterThan(0)
      for (const cell of pattern!.fretboardCells) {
        expect(cell.string).toBeGreaterThanOrEqual(1)
        expect(cell.string).toBeLessThanOrEqual(6)
        expect(cell.fret).toBeGreaterThanOrEqual(0)
        expect(cell.fret).toBeLessThanOrEqual(24)
        expect(isValidVariant(cell.variant)).toBe(true)
        expect(isValidFinger(cell.finger)).toBe(true)
      }
    })
  }

  it('returns null for empty/invalid family', () => {
    expect(generateSlonimskyPattern('bogus', 42)).toBeNull()
    expect(generateSlonimskyPattern('', 42)).toBeNull()
  })

  it('produces deterministic output for same seed', () => {
    const a = generateSlonimskyPattern('interpolation', 100)
    const b = generateSlonimskyPattern('interpolation', 100)
    expect(a).toEqual(b)
  })

  it('produces different output for different seeds', () => {
    const a = generateSlonimskyPattern('interpolation', 100)
    const b = generateSlonimskyPattern('interpolation', 200)
    // Very unlikely to be identical across seeds (16 patterns × varying positions)
    const same = JSON.stringify(a) === JSON.stringify(b)
    expect(same).toBe(false)
  })
})

describe('generateDailyWarmup', () => {
  it('returns a valid pattern with id', () => {
    const result = generateDailyWarmup(20260717)
    expect(result.id).toBeTruthy()
    expect(result.pattern).toBeTruthy()
    expect(result.pattern.fretboardCells.length).toBeGreaterThan(0)
  })

  it('is deterministic for the same seed', () => {
    const a = generateDailyWarmup(20260717)
    const b = generateDailyWarmup(20260717)
    expect(a).toEqual(b)
  })

  it('dailySeedFromDate produces correct integer', () => {
    const d = new Date(2026, 6, 17) // July 17, 2026
    expect(dailySeedFromDate(d)).toBe(20260717)
  })
})

describe('getSlonimskyPatternsByDifficulty', () => {
  it('returns correct count for difficulty 1', () => {
    const patterns = getSlonimskyPatternsByDifficulty(1)
    expect(patterns.length).toBeGreaterThanOrEqual(3)
    for (const p of patterns) {
      expect(p.difficulty).toBeLessThanOrEqual(1)
    }
  })

  it('returns correct count for difficulty 2', () => {
    const patterns = getSlonimskyPatternsByDifficulty(2)
    expect(patterns.length).toBeGreaterThan(0)
    for (const p of patterns) {
      expect(p.difficulty).toBeLessThanOrEqual(2)
    }
  })

  it('returns all patterns for difficulty 3', () => {
    const patterns = getSlonimskyPatternsByDifficulty(3)
    expect(patterns.length).toBeGreaterThanOrEqual(15)
    for (const p of patterns) {
      expect(p.difficulty).toBeLessThanOrEqual(3)
    }
  })

  it('returns more patterns for higher difficulty levels', () => {
    const l1 = getSlonimskyPatternsByDifficulty(1).length
    const l2 = getSlonimskyPatternsByDifficulty(2).length
    const l3 = getSlonimskyPatternsByDifficulty(3).length
    expect(l1).toBeLessThanOrEqual(l2)
    expect(l2).toBeLessThanOrEqual(l3)
  })
})
