import type { PitchReading } from '@/src/pitch/pitchTypes'

type PentatonicTemplate = {
  readonly label: string
  /** Pitch classes 0=C … 11=B present in this scale. */
  readonly pcs: readonly number[]
  /** Root pitch class for `highlightScaleDegrees` (same as tonal center). */
  readonly rootMidi: number
  /** Semitone offsets from root (includes 0). */
  readonly intervals: readonly number[]
}

/** Named pentatonic templates as pitch-class sets (0=C … 11=B). */
const PENTATONIC_TEMPLATES: readonly PentatonicTemplate[] = [
  { label: 'A minor pentatonic', pcs: [9, 0, 2, 4, 7], rootMidi: 9, intervals: [0, 3, 5, 7, 10] },
  { label: 'A blues', pcs: [9, 0, 2, 3, 4, 7], rootMidi: 9, intervals: [0, 3, 5, 6, 7, 10] },
  /** Same pitch-class set as E minor pentatonic — listed first so relative-major label wins ties (commit 54). */
  { label: 'G major pentatonic', pcs: [7, 9, 11, 2, 4], rootMidi: 7, intervals: [0, 2, 4, 7, 9] },
  { label: 'E minor pentatonic', pcs: [4, 7, 9, 11, 2], rootMidi: 4, intervals: [0, 3, 5, 7, 10] },
  { label: 'C major pentatonic', pcs: [0, 2, 4, 7, 9], rootMidi: 0, intervals: [0, 2, 4, 7, 9] },
  { label: 'D minor pentatonic', pcs: [2, 5, 7, 9, 11], rootMidi: 2, intervals: [0, 3, 5, 7, 10] },
]

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const

function sumBins(bins: ArrayLike<number>): number {
  let s = 0
  for (let i = 0; i < bins.length; i += 1) s += Number(bins[i])
  return s
}

/** Score how well normalized bins match a pitch-class set (higher = better). */
function templateScore(normalized: number[], pcs: readonly number[]): number {
  let t = 0
  for (const p of pcs) t += normalized[p] ?? 0
  return t
}

export type BestScaleMatch = {
  label: string
  /** Pitch class 0–11 (tonal center for harness `highlightScaleDegrees`). */
  rootMidi: number
  /** Semitone offsets from root; pass through to AlphaTab tint command. */
  intervals: readonly number[]
  /** Pitch classes in the scale (0–11). */
  pitchClasses: readonly number[]
  /** Normalized template overlap score (0–1 scale). */
  matchScore: number
}

const MATCH_THRESHOLD = 0.28

/**
 * Deterministic best pentatonic / blues match for the current histogram.
 * Returns `null` when energy is too low or no template clears the confidence threshold.
 */
export function getBestScale(bins: ArrayLike<number>): BestScaleMatch | null {
  if (bins.length !== 12) return null
  const total = sumBins(bins)
  if (total <= 0) return null
  const norm = Array.from({ length: 12 }, (_, i) => Number(bins[i]) / total)
  let best: { t: PentatonicTemplate; score: number } | null = null
  for (const t of PENTATONIC_TEMPLATES) {
    const sc = templateScore(norm, t.pcs)
    if (!best || sc > best.score) best = { t, score: sc }
  }
  if (!best || best.score < MATCH_THRESHOLD) return null
  return {
    label: best.t.label,
    rootMidi: best.t.rootMidi,
    intervals: best.t.intervals,
    pitchClasses: best.t.pcs,
    matchScore: best.score,
  }
}

/**
 * Best-matching pentatonic label, or dominant pitch-class name if no template clears threshold.
 */
export function bestScaleLabelFromBins(bins: ArrayLike<number>): string {
  const match = getBestScale(bins)
  if (match) return match.label
  if (bins.length !== 12) return '—'
  const total = sumBins(bins)
  if (total <= 0) return '—'
  let maxI = 0
  let maxV = -1
  for (let i = 0; i < 12; i += 1) {
    const v = Number(bins[i])
    if (v > maxV) {
      maxV = v
      maxI = i
    }
  }
  if (maxV <= 0) return '—'
  return `${NOTE_NAMES[maxI]} (exploring)`
}

export type PitchClassHistogram = {
  /** Count a stable pitch reading (ignores silence / invalid). */
  add(reading: PitchReading | null | undefined): void
  getBins(): number[]
  getBestLabel(): string
  getBestScale(): BestScaleMatch | null
  /** Pitch-class hits used for gating `toScalePositionMap`. */
  getTotalHits(): number
  /**
   * Normalized `pc_*` weights for persistence / server when jam was long enough and had enough pitch energy.
   */
  toScalePositionMap(durationSeconds: number): Record<string, number>
}

const MIN_DURATION_FOR_MAP_SEC = 10
const MIN_PITCH_HITS_FOR_MAP = 24

export function createPitchClassHistogram(): PitchClassHistogram {
  const bins = new Float64Array(12)
  let totalHits = 0

  return {
    add(reading) {
      if (!reading || !Number.isFinite(reading.hz) || reading.hz <= 0) return
      if (!Number.isFinite(reading.midi)) return
      const pc = ((Math.round(reading.midi) % 12) + 12) % 12
      bins[pc] += 1
      totalHits += 1
    },

    getBins() {
      return Array.from(bins)
    },

    getBestLabel() {
      return bestScaleLabelFromBins(bins)
    },

    getBestScale() {
      return getBestScale(bins)
    },

    getTotalHits() {
      return totalHits
    },

    toScalePositionMap(durationSeconds: number): Record<string, number> {
      if (durationSeconds < MIN_DURATION_FOR_MAP_SEC || totalHits < MIN_PITCH_HITS_FOR_MAP) {
        return {}
      }
      const total = sumBins(bins)
      if (total <= 0) return {}
      const map: Record<string, number> = {}
      for (let i = 0; i < 12; i += 1) {
        if (bins[i] > 0) {
          map[`pc_${NOTE_NAMES[i]}`] = bins[i] / total
        }
      }
      return map
    },
  }
}
