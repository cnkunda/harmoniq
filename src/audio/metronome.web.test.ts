import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createWebBeatMetronome } from './metronome.web'

describe('createWebBeatMetronome', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('schedules oscillator starts ~one quarter apart at 120 BPM (rate 1)', () => {
    const oscStarts: number[] = []
    let ctxTime = 1000

    const mockCtx = {
      get currentTime() {
        return ctxTime
      },
      destination: {},
      createGain: () => ({
        gain: {
          setValueAtTime: vi.fn(),
          exponentialRampToValueAtTime: vi.fn(),
        },
        connect: vi.fn(),
      }),
      createOscillator: () => ({
        type: 'square',
        frequency: { setValueAtTime: vi.fn() },
        connect: vi.fn(),
        start: (t: number) => {
          oscStarts.push(t)
        },
        stop: vi.fn(),
      }),
    } as unknown as AudioContext

    const m = createWebBeatMetronome(mockCtx)
    let pos = 0
    m.start({
      beatGrid: [0, 0.5],
      tempoBpm: 120,
      getPlaybackRate: () => 1,
      getSongPositionSeconds: () => pos,
      isPlaying: () => true,
      subdivision: 1,
    })

    for (let i = 0; i < 80; i += 1) {
      vi.advanceTimersByTime(25)
      ctxTime += 0.025
      pos += 0.025
    }

    m.stop()
    oscStarts.sort((a, b) => a - b)
    expect(oscStarts.length).toBeGreaterThanOrEqual(2)
    const gaps: number[] = []
    for (let i = 1; i < oscStarts.length; i += 1) gaps.push(oscStarts[i]! - oscStarts[i - 1]!)
    const maxGap = Math.max(...gaps)
    const minGap = Math.min(...gaps)
    const target = 0.5
    expect(maxGap - target).toBeLessThan(0.01)
    expect(target - minGap).toBeLessThan(0.01)
  })

  /** MANUAL_QA — Metronome automation (120 BPM steady spacing). */
  it('keeps ~0.5s AudioContext spacing over many beats at 120 BPM (rate 1)', () => {
    const oscStarts: number[] = []
    let ctxTime = 1000

    const mockCtx = {
      get currentTime() {
        return ctxTime
      },
      destination: {},
      createGain: () => ({
        gain: {
          setValueAtTime: vi.fn(),
          exponentialRampToValueAtTime: vi.fn(),
        },
        connect: vi.fn(),
      }),
      createOscillator: () => ({
        type: 'square',
        frequency: { setValueAtTime: vi.fn() },
        connect: vi.fn(),
        start: (t: number) => {
          oscStarts.push(t)
        },
        stop: vi.fn(),
      }),
    } as unknown as AudioContext

    const m = createWebBeatMetronome(mockCtx)
    let pos = 0
    m.start({
      beatGrid: [0, 0.5],
      tempoBpm: 120,
      getPlaybackRate: () => 1,
      getSongPositionSeconds: () => pos,
      isPlaying: () => true,
      subdivision: 1,
    })

    const steps = Math.ceil(32 / 0.025)
    for (let i = 0; i < steps; i += 1) {
      vi.advanceTimersByTime(25)
      ctxTime += 0.025
      pos += 0.025
    }

    m.stop()
    oscStarts.sort((a, b) => a - b)
    expect(oscStarts.length).toBeGreaterThanOrEqual(55)
    const gaps: number[] = []
    for (let i = 1; i < oscStarts.length; i += 1) gaps.push(oscStarts[i]! - oscStarts[i - 1]!)
    const tol = 0.04
    for (const g of gaps.slice(5, -5)) {
      expect(Math.abs(g - 0.5)).toBeLessThan(tol)
    }
  })

  /** MANUAL_QA — beat flash when clicks schedule. */
  it('invokes onBeatFlash when scheduling clicks', () => {
    const onBeatFlash = vi.fn()
    let ctxTime = 500
    const mockCtx = {
      get currentTime() {
        return ctxTime
      },
      destination: {},
      createGain: () => ({
        gain: {
          setValueAtTime: vi.fn(),
          exponentialRampToValueAtTime: vi.fn(),
        },
        connect: vi.fn(),
      }),
      createOscillator: () => ({
        type: 'square',
        frequency: { setValueAtTime: vi.fn() },
        connect: vi.fn(),
        start: vi.fn(),
        stop: vi.fn(),
      }),
    } as unknown as AudioContext

    const m = createWebBeatMetronome(mockCtx)
    let pos = 0
    m.start({
      beatGrid: [0, 0.5],
      tempoBpm: 120,
      getPlaybackRate: () => 1,
      getSongPositionSeconds: () => pos,
      isPlaying: () => true,
      subdivision: 1,
      onBeatFlash,
    })

    for (let i = 0; i < 120; i += 1) {
      vi.advanceTimersByTime(25)
      ctxTime += 0.025
      pos += 0.025
    }
    m.stop()
    expect(onBeatFlash.mock.calls.length).toBeGreaterThanOrEqual(3)
  })

  /** MANUAL_QA — backward song jump clears dedupe so lap 2 can reschedule. */
  it('clears dedupe set after backward transport jump and schedules again', () => {
    const oscStarts: number[] = []
    let ctxTime = 1000
    const mockCtx = {
      get currentTime() {
        return ctxTime
      },
      destination: {},
      createGain: () => ({
        gain: {
          setValueAtTime: vi.fn(),
          exponentialRampToValueAtTime: vi.fn(),
        },
        connect: vi.fn(),
      }),
      createOscillator: () => ({
        type: 'square',
        frequency: { setValueAtTime: vi.fn() },
        connect: vi.fn(),
        start: (t: number) => {
          oscStarts.push(t)
        },
        stop: vi.fn(),
      }),
    } as unknown as AudioContext

    const m = createWebBeatMetronome(mockCtx)
    let pos = 0
    m.start({
      beatGrid: [0, 0.5],
      tempoBpm: 120,
      getPlaybackRate: () => 1,
      getSongPositionSeconds: () => pos,
      isPlaying: () => true,
      subdivision: 1,
    })

    for (let i = 0; i < 200; i += 1) {
      vi.advanceTimersByTime(25)
      ctxTime += 0.025
      pos += 0.025
    }
    const nBeforeJump = oscStarts.length
    pos = 0.02
    for (let i = 0; i < 200; i += 1) {
      vi.advanceTimersByTime(25)
      ctxTime += 0.025
      pos += 0.025
    }
    m.stop()
    expect(oscStarts.length).toBeGreaterThan(nBeforeJump + 8)
  })

  /** MANUAL_QA — slower playback rate stretches wall-clock click spacing. */
  it('stretches AudioContext click spacing at playback rate 0.65 vs 1', () => {
    const meanGapForRate = (rate: number) => {
      const oscStarts: number[] = []
      let ctxTime = 1000
      const mockCtx = {
        get currentTime() {
          return ctxTime
        },
        destination: {},
        createGain: () => ({
          gain: {
            setValueAtTime: vi.fn(),
            exponentialRampToValueAtTime: vi.fn(),
          },
          connect: vi.fn(),
        }),
        createOscillator: () => ({
          type: 'square',
          frequency: { setValueAtTime: vi.fn() },
          connect: vi.fn(),
          start: (t: number) => {
            oscStarts.push(t)
          },
          stop: vi.fn(),
        }),
      } as unknown as AudioContext

      const m = createWebBeatMetronome(mockCtx)
      let pos = 0
      const wallDt = 0.025
      m.start({
        beatGrid: [0, 0.5],
        tempoBpm: 120,
        getPlaybackRate: () => rate,
        getSongPositionSeconds: () => pos,
        isPlaying: () => true,
        subdivision: 1,
      })
      for (let i = 0; i < 200; i += 1) {
        vi.advanceTimersByTime(25)
        ctxTime += wallDt
        pos += wallDt * rate
      }
      m.stop()
      return meanConsecutiveGapFromStamps(oscStarts)
    }

    const g1 = meanGapForRate(1)
    const g065 = meanGapForRate(0.65)
    expect(g1).toBeGreaterThan(0.45)
    expect(g1).toBeLessThan(0.55)
    expect(g065 / g1).toBeCloseTo(1 / 0.65, 1)
  })
})

function meanConsecutiveGapFromStamps(stamps: number[]): number {
  const sorted = [...stamps].sort((a, b) => a - b)
  if (sorted.length < 3) return 0
  const gaps: number[] = []
  for (let i = 1; i < sorted.length; i += 1) gaps.push(sorted[i]! - sorted[i - 1]!)
  const mid = gaps.slice(2, -2)
  return mid.reduce((a, b) => a + b, 0) / mid.length
}
