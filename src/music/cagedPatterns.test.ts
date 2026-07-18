import { describe, it, expect } from 'vitest'
import { getCagedPattern, getCagedPatternForScale } from './cagedPatterns'
import type { CagedForm } from './cagedPatterns'

describe('CAGED patterns — structural integrity', () => {
  const forms: CagedForm[] = ['E', 'A', 'D', 'C', 'G']

  it('each form returns non-empty cells', () => {
    for (const form of forms) {
      const cells = getCagedPattern(form)
      expect(cells.length).toBeGreaterThan(0)
    }
  })

  it('each cell has valid string (1-6) and fret (0-12)', () => {
    for (const form of forms) {
      for (const cell of getCagedPattern(form)) {
        expect(cell.string).toBeGreaterThanOrEqual(1)
        expect(cell.string).toBeLessThanOrEqual(6)
        expect(cell.fret).toBeGreaterThanOrEqual(0)
        expect(cell.fret).toBeLessThanOrEqual(12)
      }
    }
  })

  it('interval 0 (root) is present in every form', () => {
    for (const form of forms) {
      const cells = getCagedPattern(form)
      expect(cells.some((c) => c.interval % 12 === 0)).toBe(true)
    }
  })
})

describe('getCagedPatternForScale', () => {
  it('filters E form to C major (Ionian) scale tones', () => {
    const cells = getCagedPatternForScale('E', 0, [0, 2, 4, 5, 7, 9, 11])
    expect(cells.length).toBeGreaterThan(0)
    expect(cells.length).toBeLessThanOrEqual(6)
    for (const cell of cells) {
      expect([0, 2, 4, 5, 7, 9, 11]).toContain(cell.interval % 12)
    }
  })

  it('returns empty for E form with no matching intervals', () => {
    const cells = getCagedPatternForScale('E', 0, [1, 3, 6, 8, 10])
    expect(cells.length).toBe(0)
  })

  it('correctly positions A form for D root', () => {
    const cells = getCagedPatternForScale('A', 2, [0, 2, 4, 5, 7, 9, 11])
    expect(cells.length).toBeGreaterThan(0)
    for (const cell of cells) {
      expect([0, 2, 4, 5, 7, 9, 11]).toContain(cell.interval % 12)
    }
  })

  it('returns the same intervals for E form regardless of root', () => {
    const cellsC = getCagedPatternForScale('E', 0, [0, 2, 4, 5, 7, 9, 11])
    const cellsG = getCagedPatternForScale('E', 7, [0, 2, 4, 5, 7, 9, 11])
    const intervalsC = cellsC.map((c) => c.interval % 12).sort((a, b) => a - b)
    const intervalsG = cellsG.map((c) => c.interval % 12).sort((a, b) => a - b)
    expect(intervalsC).toEqual(intervalsG)
  })
})
