import { afterEach, describe, expect, it, vi } from 'vitest'

import { effectiveRmsSignalGate } from '@/src/audio/noiseGate'
import {
  captureBeatIndexFromTick,
  dynamicGhostRmsThreshold,
  latencyCompensationSecFromDrift,
} from '@/src/session/noteAccuracyBeats'

describe('captureBeatIndexFromTick', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('uses transport position when tick exists and playing', () => {
    const anchor = 10
    const idx = captureBeatIndexFromTick({
      tick: { playing: true, positionSec: anchor + 2.5 },
      anchorPosSec: anchor,
      recordStartMs: 0,
      beatSec: 1,
    })
    expect(idx).toBe(2)
  })

  it('uses wall clock when tick is null (before first stem tick)', () => {
    vi.spyOn(Date, 'now').mockReturnValue(5000)
    const idx = captureBeatIndexFromTick({
      tick: null,
      anchorPosSec: 0,
      recordStartMs: 1000,
      beatSec: 1,
    })
    expect(idx).toBe(4)
  })

  it('uses wall clock when tick exists but paused', () => {
    vi.spyOn(Date, 'now').mockReturnValue(3000)
    const idx = captureBeatIndexFromTick({
      tick: { playing: false, positionSec: 99 },
      anchorPosSec: 0,
      recordStartMs: 500,
      beatSec: 0.5,
    })
    expect(idx).toBe(5)
  })
})

describe('latency compensation (P2)', () => {
  it('returns zero without drift', () => {
    expect(latencyCompensationSecFromDrift(null, 0.5)).toBe(0)
  })

  it('delays windows for a late player (negative drift)', () => {
    expect(latencyCompensationSecFromDrift(-120, 0.5)).toBeCloseTo(0.12, 5)
  })

  it('advances windows for an early player (positive drift)', () => {
    expect(latencyCompensationSecFromDrift(80, 0.5)).toBeCloseTo(-0.08, 5)
  })

  it('clamps compensation to 35% of a beat', () => {
    expect(latencyCompensationSecFromDrift(-5000, 0.5)).toBeCloseTo(0.175, 5)
  })

  it('shifts the capture beat index by the compensation', () => {
    const base = {
      tick: { playing: true, positionSec: 2 },
      anchorPosSec: 0,
      recordStartMs: 0,
      beatSec: 1,
    }
    expect(captureBeatIndexFromTick(base)).toBe(2)
    // 120 ms of compensation: 2.0 s - 0.12 s = 1.88 s -> still beat 1
    expect(captureBeatIndexFromTick({ ...base, latencyCompensationSec: 0.12 })).toBe(1)
  })
})

describe('effectiveRmsSignalGate + dynamic ghost (Commit 62)', () => {
  it('uses calibrated gate when higher than dynamic ghost threshold', () => {
    const ghost = dynamicGhostRmsThreshold(0.05)
    expect(effectiveRmsSignalGate(ghost, 0.08)).toBe(0.08)
  })
})
