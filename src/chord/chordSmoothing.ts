/**
 * Temporal smoothing for live chord detection.
 *
 * The CRNN emits a class distribution every inference cycle (~0.5–1 s). Raw
 * argmax output flickers between neighbouring chords and reacts to a single
 * noisy frame. `ChordSmoother` stabilizes the stream with two mechanisms:
 *
 *   1. EMA over the probability vector — reduces frame-to-frame jitter.
 *   2. Hysteresis — a new chord is only committed after it stays the smoothed
 *      argmax for `stabilityCount` consecutive updates and clears
 *      `confidenceThreshold`. Otherwise the previously committed chord holds.
 *
 * The class is pure/stateful (no React, no I/O) so it is straightforward to
 * unit-test with crafted probability sequences.
 */

export interface ChordSmootherOptions {
  /** Number of output classes (25 for the MIREX vocab). */
  numClasses: number
  /** EMA factor for the probability vector (0–1, higher = more responsive). */
  emaAlpha?: number
  /** Minimum smoothed probability required to commit a chord. */
  confidenceThreshold?: number
  /** Consecutive agreeing updates required before switching the committed chord. */
  stabilityCount?: number
}

export interface SmoothResult {
  /** Committed class index, or -1 when nothing is confidently detected yet. */
  index: number
  /** Smoothed probability of the committed class (0 when index is -1). */
  confidence: number
  /** Whether the committed index changed on this update. */
  changed: boolean
}

const DEFAULTS = {
  emaAlpha: 0.4,
  confidenceThreshold: 0.5,
  stabilityCount: 2,
}

export class ChordSmoother {
  private readonly numClasses: number
  private readonly emaAlpha: number
  private readonly confidenceThreshold: number
  private readonly stabilityCount: number

  private ema: Float32Array | null = null
  private committed = -1
  private candidate = -1
  private candidateStreak = 0

  constructor(options: ChordSmootherOptions) {
    this.numClasses = options.numClasses
    this.emaAlpha = options.emaAlpha ?? DEFAULTS.emaAlpha
    this.confidenceThreshold = options.confidenceThreshold ?? DEFAULTS.confidenceThreshold
    this.stabilityCount = Math.max(1, options.stabilityCount ?? DEFAULTS.stabilityCount)
  }

  /** Feed a new probability vector; returns the stabilized decision. */
  update(probs: Float32Array | number[]): SmoothResult {
    const n = Math.min(this.numClasses, probs.length)

    // 1) EMA the probability vector.
    if (!this.ema) {
      this.ema = new Float32Array(this.numClasses)
      for (let i = 0; i < n; i++) this.ema[i] = probs[i] ?? 0
    } else {
      const a = this.emaAlpha
      for (let i = 0; i < n; i++) {
        this.ema[i] = a * (probs[i] ?? 0) + (1 - a) * this.ema[i]!
      }
    }

    // 2) Argmax of the smoothed vector.
    let topIdx = 0
    let topProb = this.ema[0] ?? 0
    for (let i = 1; i < this.numClasses; i++) {
      const p = this.ema[i] ?? 0
      if (p > topProb) {
        topProb = p
        topIdx = i
      }
    }

    // Target is "uncertain" (-1) when the leader is below the confidence gate.
    const target = topProb >= this.confidenceThreshold ? topIdx : -1

    // 3) Hysteresis.
    let changed = false
    if (target === this.committed) {
      this.candidate = target
      this.candidateStreak = 0
    } else if (target === this.candidate) {
      this.candidateStreak++
      if (this.candidateStreak >= this.stabilityCount) {
        this.committed = target
        this.candidateStreak = 0
        changed = true
      }
    } else {
      this.candidate = target
      this.candidateStreak = 1
      // A single update can never switch unless stabilityCount === 1.
      if (this.stabilityCount === 1) {
        this.committed = target
        changed = true
      }
    }

    const confidence = this.committed >= 0 ? (this.ema[this.committed] ?? 0) : 0
    return { index: this.committed, confidence, changed }
  }

  reset(): void {
    this.ema = null
    this.committed = -1
    this.candidate = -1
    this.candidateStreak = 0
  }
}
