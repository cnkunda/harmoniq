import { describe, expect, it } from 'vitest'

import { countInBeatPeriodMs, isCountInDownbeat } from '@/src/audio/countInShared'

describe('count-in math', () => {
  it('converts BPM to a beat period', () => {
    expect(countInBeatPeriodMs(120)).toBe(500)
    expect(countInBeatPeriodMs(60)).toBe(1000)
  })

  it('falls back safely for invalid tempo', () => {
    expect(countInBeatPeriodMs(0)).toBe(625)
    expect(countInBeatPeriodMs(Number.NaN)).toBe(625)
  })

  it('marks the first beat of each bar as a downbeat', () => {
    expect([1, 2, 3, 4, 5, 6, 7, 8].map((b) => isCountInDownbeat(b, 4))).toEqual([
      true,
      false,
      false,
      false,
      true,
      false,
      false,
      false,
    ])
    expect(isCountInDownbeat(3, 3)).toBe(false)
    expect(isCountInDownbeat(4, 3)).toBe(true)
    expect(isCountInDownbeat(4, 0)).toBe(true) // clamped to a bar of 1
  })
})
