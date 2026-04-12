import { describe, expect, it } from 'vitest'

import {
  barIndexAtOrBeforeTime,
  barRangeToSeconds,
  clampBarLoopRange,
  pickLowestNumericBarIndex,
} from './barLoopBounds'

describe('barIndexAtOrBeforeTime', () => {
  const ts = [0, 2, 4, 6, 8]

  it('returns 0 before first bar', () => {
    expect(barIndexAtOrBeforeTime(ts, -1)).toBe(0)
    expect(barIndexAtOrBeforeTime(ts, 0)).toBe(0)
  })

  it('binary-searchs interior and end', () => {
    expect(barIndexAtOrBeforeTime(ts, 0.1)).toBe(0)
    expect(barIndexAtOrBeforeTime(ts, 2)).toBe(1)
    expect(barIndexAtOrBeforeTime(ts, 3.5)).toBe(1)
    expect(barIndexAtOrBeforeTime(ts, 8)).toBe(4)
    expect(barIndexAtOrBeforeTime(ts, 99)).toBe(4)
  })
})

describe('barRangeToSeconds', () => {
  it('uses exact next bar as end boundary', () => {
    const ts = [0, 2, 4, 6]
    const r = barRangeToSeconds(ts, 1, 3, 0.5)
    expect(r).toEqual({ startSec: 2, endSec: 6 })
  })

  it('extrapolates past last bar', () => {
    const ts = [0, 2, 4, 6]
    const r = barRangeToSeconds(ts, 2, 5, 0.5)
    expect(r).not.toBeNull()
    expect(r!.startSec).toBe(4)
    expect(r!.endSec).toBeGreaterThan(4)
  })
})

describe('clampBarLoopRange', () => {
  it('enforces at least one bar span', () => {
    expect(clampBarLoopRange(2, 2, 8)).toEqual({ startBarIndex: 2, endBarIndexExclusive: 3 })
  })
})

describe('pickLowestNumericBarIndex', () => {
  it('selects lowest-confidence bar in fixture', () => {
    const idx = pickLowestNumericBarIndex([0.9, 0.2, 0.8])
    expect(idx).toBe(1)
  })

  it('returns null for empty or non-numeric', () => {
    expect(pickLowestNumericBarIndex([])).toBeNull()
    expect(pickLowestNumericBarIndex(['x', null])).toBeNull()
  })
})
