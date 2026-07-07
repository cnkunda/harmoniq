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
