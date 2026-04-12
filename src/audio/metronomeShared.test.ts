import { describe, expect, it } from 'vitest'

import {
  beatPeriodSeconds,
  collectClickTimesInRange,
  gridAnchorSeconds,
  medianBeatIntervalSeconds,
} from './metronomeShared'

describe('metronomeShared', () => {
  it('beatPeriodSeconds uses grid spacing when possible', () => {
    expect(beatPeriodSeconds([0, 0.5], 999)).toBeCloseTo(0.5, 5)
  })

  it('medianBeatIntervalSeconds ignores outlier first interval', () => {
    const med = medianBeatIntervalSeconds([0, 0.2, 0.7, 1.2, 1.7])
    expect(med).toBeCloseTo(0.5, 5)
  })

  it('beatPeriodSeconds falls back to tempo', () => {
    expect(beatPeriodSeconds([], 120)).toBeCloseTo(0.5, 5)
  })

  it('gridAnchorSeconds reads first sorted beat', () => {
    expect(gridAnchorSeconds([1, 0.2, 0.5])).toBeCloseTo(0.2, 5)
  })

  it('subdivision 4 yields more clicks than 1 in the same window', () => {
    const grid = [0, 0.5]
    const tempo = 120
    const q = collectClickTimesInRange(grid, tempo, 0, 1.0, 1)
    const s = collectClickTimesInRange(grid, tempo, 0, 1.0, 4)
    expect(s.length).toBeGreaterThan(q.length)
  })

  it('marks quarter boundaries as downbeat every four quarters from anchor', () => {
    const c = collectClickTimesInRange([0, 0.5], 120, 0, 2.5, 1)
    const down = c.filter((x) => x.isDownbeat).map((x) => x.songTime)
    expect(down.some((t) => Math.abs(t - 0) < 1e-3)).toBe(true)
    expect(down.some((t) => Math.abs(t - 2.0) < 1e-3)).toBe(true)
  })

  it('dense beat_grid places quarter clicks on detected beats (subdivision 1)', () => {
    const grid = [0, 0.52, 1.01, 1.49, 2.0]
    const c = collectClickTimesInRange(grid, 120, 0, 2.05, 1)
    const quarters = c.map((x) => x.songTime)
    expect(quarters.some((t) => Math.abs(t - 0) < 0.02)).toBe(true)
    expect(quarters.some((t) => Math.abs(t - 0.52) < 0.02)).toBe(true)
    expect(quarters.some((t) => Math.abs(t - 1.01) < 0.02)).toBe(true)
  })

  it('uses bar_timestamps for downbeats when provided', () => {
    const grid = [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
    const bars = [0, 2.0]
    const c = collectClickTimesInRange(grid, 120, 0, 2.2, 1, { barTimestamps: bars })
    const down = c.filter((x) => x.isDownbeat).map((x) => x.songTime)
    expect(down.some((t) => Math.abs(t - 0) < 0.06)).toBe(true)
    expect(down.some((t) => Math.abs(t - 2.0) < 0.06)).toBe(true)
    expect(down.some((t) => Math.abs(t - 0.5) < 0.02)).toBe(false)
  })
})
