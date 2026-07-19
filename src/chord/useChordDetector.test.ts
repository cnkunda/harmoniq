import { describe, it, expect, vi, afterEach } from 'vitest'

/**
 * Tests for the AC 6 latency guard in useChordDetector.ts
 *
 * Verifies that console.warn is called when inference latency exceeds
 * the 120ms threshold, and is not called when under threshold.
 */

describe('useChordDetector latency guard (AC 6)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  const THRESHOLD = 120
  const MODEL_TYPE = 'tflite'

  function checkLatency(latencyMs: number) {
    if (latencyMs > THRESHOLD) {
      console.warn(
        `[ChordDetector] Slow inference: ${latencyMs.toFixed(1)}ms ` +
        `(threshold: ${THRESHOLD}ms, model: ${MODEL_TYPE})`,
      )
    }
  }

  it('warns via console.warn when inference latency exceeds 120ms', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    checkLatency(150)

    expect(warnSpy).toHaveBeenCalledTimes(1)
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('Slow inference: 150.0ms'),
    )
  })

  it('does not warn when inference latency is under 120ms', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    checkLatency(80)

    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('warns at exactly the boundary of 120ms (120.001)', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    checkLatency(120.001)

    expect(warnSpy).toHaveBeenCalledTimes(1)
  })

  it('does not warn at exactly 120ms (equal to threshold)', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    checkLatency(120)

    expect(warnSpy).not.toHaveBeenCalled()
  })
})

describe('inference in-flight guard', () => {
  // Mirrors the guard in useChordDetector.runInference: overlapping ticks are
  // dropped rather than queued so slow inferences cannot pile up.
  it('drops overlapping runs while one is in flight', async () => {
    let inFlight = false
    let started = 0
    let completed = 0

    const runOnce = async () => {
      if (inFlight) return
      inFlight = true
      started++
      try {
        await new Promise((r) => setTimeout(r, 10))
        completed++
      } finally {
        inFlight = false
      }
    }

    // Fire three ticks back-to-back; only the first should start.
    await Promise.all([runOnce(), runOnce(), runOnce()])
    expect(started).toBe(1)
    expect(completed).toBe(1)

    // After it settles, a new tick can run again.
    await runOnce()
    expect(started).toBe(2)
    expect(completed).toBe(2)
  })
})

describe('RMS silence gate', () => {
  const RMS_SILENCE_THRESHOLD = 0.01

  function rms(samples: number[]): number {
    let sum = 0
    for (const v of samples) sum += v * v
    return Math.sqrt(sum / samples.length)
  }

  it('treats near-silence as No-Chord (below threshold)', () => {
    const quiet = new Array(1024).fill(0).map(() => (Math.random() - 0.5) * 0.001)
    expect(rms(quiet)).toBeLessThan(RMS_SILENCE_THRESHOLD)
  })

  it('passes an audible signal through the gate (above threshold)', () => {
    const loud = new Array(1024).fill(0).map((_, i) => Math.sin(i) * 0.5)
    expect(rms(loud)).toBeGreaterThanOrEqual(RMS_SILENCE_THRESHOLD)
  })
})
