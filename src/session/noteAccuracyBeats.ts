/** Per-beat pitch windows derived from lesson tempo (commit 49). */

import {
  GHOST_DB_BELOW_PEAK,
  GHOST_RMS_MIN_FLOOR,
  GHOST_RMS_WINDOW_MS,
  HIT_INNER_MAX_CENTS,
  HIT_VS_ADAPTED_RATIO,
  VIBRATO_DEPTH_CENTS_PEAK_TO_PEAK,
  VIBRATO_MIN_DURATION_MS,
  VIBRATO_RATE_MAX_HZ,
  VIBRATO_RATE_MIN_HZ,
} from '@/src/utils/practiceConfig'

export type AccuracyLabel = 'hit' | 'close' | 'miss'

export type NoteResultLabel = AccuracyLabel | 'vibrato' | 'ignored'

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

export function hitInnerThresholdCents(adaptedCentsTolerance: number): number {
  return Math.min(HIT_INNER_MAX_CENTS, adaptedCentsTolerance * HIT_VS_ADAPTED_RATIO)
}

/**
 * Pitch class: inner “hit” tier uses min(15¢, adapted×0.55); “close” up to adapted tolerance.
 */
export function classifyMedianCents(medianAbs: number | null, adaptedCentsTolerance: number): AccuracyLabel {
  if (medianAbs == null || !Number.isFinite(medianAbs)) return 'miss'
  const inner = hitInnerThresholdCents(adaptedCentsTolerance)
  if (medianAbs <= inner) return 'hit'
  if (medianAbs <= adaptedCentsTolerance) return 'close'
  return 'miss'
}

export type CentsContourPoint = { t: number; cents: number }

/** Regular pitch oscillation in the vocal/guitar vibrato band (calibrate for bend vibrato). */
export function detectVibratoFromCentsContour(samples: CentsContourPoint[]): boolean {
  if (samples.length < 4) return false
  const t0 = samples[0]!.t
  const tEnd = samples[samples.length - 1]!.t
  if (tEnd - t0 < VIBRATO_MIN_DURATION_MS) return false

  const mean = samples.reduce((s, p) => s + p.cents, 0) / samples.length
  const det = samples.map((p) => p.cents - mean)
  const minC = Math.min(...det)
  const maxC = Math.max(...det)
  if (maxC - minC < VIBRATO_DEPTH_CENTS_PEAK_TO_PEAK) return false

  const peaks: number[] = []
  for (let i = 1; i < det.length - 1; i += 1) {
    const v = det[i]!
    if (v > det[i - 1]! && v > det[i + 1]! && v > 4) peaks.push(samples[i]!.t)
  }
  if (peaks.length < 2) return false
  const span = peaks[peaks.length - 1]! - peaks[0]!
  if (span <= 0) return false
  const avgPeriodMs = span / (peaks.length - 1)
  const rateHz = 1000 / avgPeriodMs
  return rateHz >= VIBRATO_RATE_MIN_HZ && rateHz <= VIBRATO_RATE_MAX_HZ
}

/**
 * After ghost gating: vibrato replaces hit/close when in tolerance and oscillation matches.
 */
export function resolvePitchResult(args: {
  medianAbs: number | null
  adaptedCentsTolerance: number
  centsContour: CentsContourPoint[]
}): NoteResultLabel {
  const { medianAbs, adaptedCentsTolerance, centsContour } = args
  if (medianAbs != null && medianAbs > adaptedCentsTolerance) return 'miss'
  if (medianAbs == null || !Number.isFinite(medianAbs)) return 'miss'

  const base = classifyMedianCents(medianAbs, adaptedCentsTolerance)
  if (base === 'miss') return 'miss'
  if (detectVibratoFromCentsContour(centsContour)) return 'vibrato'
  return base
}

export type RmsHistorySample = { t: number; rms: number }

/** Recent peak RMS in the sliding window (for dynamic ghost threshold). */
export function peakRmsInWindow(history: RmsHistorySample[], nowMs: number): number {
  const cutoff = nowMs - GHOST_RMS_WINDOW_MS
  let peak = 0
  for (const s of history) {
    if (s.t >= cutoff && s.rms > peak) peak = s.rms
  }
  return peak
}

/** RMS gate: window must reach this level vs recent peak or be treated as ghost/silence. */
export function dynamicGhostRmsThreshold(peakRmsRecent: number): number {
  const fromPeak = peakRmsRecent > 0 ? peakRmsRecent * Math.pow(10, -GHOST_DB_BELOW_PEAK / 20) : 0
  return Math.max(GHOST_RMS_MIN_FLOOR, fromPeak)
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
