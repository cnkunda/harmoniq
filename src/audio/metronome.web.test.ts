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

})
