/** Per-beat pitch windows derived from lesson tempo (commit 49). */

export type AccuracyLabel = 'hit' | 'close' | 'miss'

/** Quarter-note beat length in seconds, clamped for stability. */
export function beatDurationSecFromTempo(tempoBpm: number | null | undefined): number {
  const raw = typeof tempoBpm === 'number' && Number.isFinite(tempoBpm) ? tempoBpm : 96
  const clamped = Math.min(220, Math.max(48, raw))
  return 60 / clamped
}

/** Ring buffer of signed cents vs target; bounded for hot pitch callback path. */
export class CentSampleRing {
  private readonly cap: number
  private values: number[] = []

  constructor(cap = 200) {
    this.cap = Math.max(16, cap)
  }

  push(cents: number): void {
    if (!Number.isFinite(cents)) return
    this.values.push(cents)
    if (this.values.length > this.cap) {
      this.values.splice(0, this.values.length - this.cap)
    }
  }

  clear(): void {
    this.values = []
  }

  hasSamples(): boolean {
    return this.values.length > 0
  }

  /** Median of absolute cents in the current window. */
  medianAbs(): number | null {
    if (this.values.length === 0) return null
    const sorted = [...this.values].map((x) => Math.abs(x)).sort((a, b) => a - b)
    const mid = Math.floor(sorted.length / 2)
    return sorted.length % 2 === 1 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2
  }
}

/** Match Play step ladder thresholds: sage ≤15c, amber ≤50c. */
export function classifyMedianCents(medianAbs: number | null): AccuracyLabel {
  if (medianAbs == null || !Number.isFinite(medianAbs)) return 'miss'
  if (medianAbs <= 15) return 'hit'
  if (medianAbs <= 50) return 'close'
  return 'miss'
}

export function beatIndexFromClocks(args: {
  playing: boolean
  positionSec: number
  anchorPosSec: number
  recordStartMs: number
  beatSec: number
}): number {
  const { playing, positionSec, anchorPosSec, recordStartMs, beatSec } = args
  if (beatSec <= 0) return 0
  if (playing) {
    const delta = Math.max(0, positionSec - anchorPosSec)
    return Math.floor(delta / beatSec)
  }
  const elapsedSec = (Date.now() - recordStartMs) / 1000
  return Math.floor(Math.max(0, elapsedSec) / beatSec)
}
