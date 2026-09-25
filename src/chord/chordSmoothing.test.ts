import { describe, it, expect } from 'vitest'

import { ChordSmoother } from '@/src/chord/chordSmoothing'

const N = 25

/** Build a probability vector peaked at `idx` with the given peak value. */
function probs(idx: number, peak: number): Float32Array {
  const v = new Float32Array(N)
  const rest = (1 - peak) / (N - 1)
  v.fill(rest)
  v[idx] = peak
  return v
}

describe('ChordSmoother', () => {
  it('commits a chord only after it is stable for stabilityCount updates', () => {
    const s = new ChordSmoother({ numClasses: N, stabilityCount: 2, confidenceThreshold: 0.5, emaAlpha: 1 })

    const r1 = s.update(probs(3, 0.9))
    expect(r1.index).toBe(-1) // first sighting: candidate, not committed
    expect(r1.changed).toBe(false)

    const r2 = s.update(probs(3, 0.9))
    expect(r2.index).toBe(3) // second consecutive sighting: committed
    expect(r2.changed).toBe(true)
  })

  it('does not switch on a single divergent frame (hysteresis)', () => {
    const s = new ChordSmoother({ numClasses: N, stabilityCount: 2, confidenceThreshold: 0.5, emaAlpha: 1 })
    s.update(probs(3, 0.9))
    s.update(probs(3, 0.9)) // committed = 3

    const r = s.update(probs(7, 0.9)) // one frame of a different chord
    expect(r.index).toBe(3) // still holding previous chord
    expect(r.changed).toBe(false)
  })

  it('switches after the new chord becomes stable', () => {
    const s = new ChordSmoother({ numClasses: N, stabilityCount: 2, confidenceThreshold: 0.5, emaAlpha: 1 })
    s.update(probs(3, 0.9))
    s.update(probs(3, 0.9)) // committed = 3

    s.update(probs(7, 0.9)) // candidate 7 (1)
    const r = s.update(probs(7, 0.9)) // candidate 7 (2) → commit
    expect(r.index).toBe(7)
    expect(r.changed).toBe(true)
  })

  it('stays uncertain (-1) when confidence is below threshold', () => {
    const s = new ChordSmoother({ numClasses: N, stabilityCount: 2, confidenceThreshold: 0.5, emaAlpha: 1 })
    const r1 = s.update(probs(3, 0.3))
    const r2 = s.update(probs(3, 0.3))
    expect(r1.index).toBe(-1)
    expect(r2.index).toBe(-1)
  })

  it('EMA suppresses a one-frame spike from flipping the committed chord', () => {
    const s = new ChordSmoother({ numClasses: N, stabilityCount: 2, confidenceThreshold: 0.5, emaAlpha: 0.4 })
    // Establish chord 3 with several strong frames.
    for (let i = 0; i < 6; i++) s.update(probs(3, 0.95))
    expect(s.update(probs(3, 0.95)).index).toBe(3)

    // A couple of noisy frames for 7 should not immediately overturn the EMA.
    s.update(probs(7, 0.95))
    const r = s.update(probs(7, 0.95))
    // With EMA the smoothed leader may still be 3 for these two frames.
    expect(r.index).toBe(3)
  })

  it('commits immediately when stabilityCount is 1', () => {
    const s = new ChordSmoother({ numClasses: N, stabilityCount: 1, confidenceThreshold: 0.5, emaAlpha: 1 })
    const r = s.update(probs(9, 0.8))
    expect(r.index).toBe(9)
    expect(r.changed).toBe(true)
  })

  it('reset clears committed state', () => {
    const s = new ChordSmoother({ numClasses: N, stabilityCount: 1, confidenceThreshold: 0.5, emaAlpha: 1 })
    s.update(probs(9, 0.8))
    s.reset()
    const r = s.update(probs(2, 0.3)) // below threshold after reset
    expect(r.index).toBe(-1)
  })
})
