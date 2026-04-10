import type { PitchReading } from '@/src/pitch/pitchTypes'

/** Named pentatonic templates as pitch-class sets (0=C … 11=B). */
const PENTATONIC_TEMPLATES: ReadonlyArray<{ readonly label: string; readonly pcs: readonly number[] }> = [
  { label: 'A minor pent.', pcs: [9, 0, 2, 4, 7] },
  { label: 'E minor pent.', pcs: [4, 7, 9, 11, 2] },
  { label: 'G major pent.', pcs: [7, 9, 11, 2, 4] },
  { label: 'C major pent.', pcs: [0, 2, 4, 7, 9] },
  { label: 'D minor pent.', pcs: [2, 5, 7, 9, 11] },
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

/**
 * Best-matching pentatonic label, or dominant pitch-class name if no template clears threshold.
 */
export function bestScaleLabelFromBins(bins: ArrayLike<number>): string {
  if (bins.length !== 12) return '—'
  const total = sumBins(bins)
  if (total <= 0) return '—'
  const norm = Array.from({ length: 12 }, (_, i) => Number(bins[i]) / total)
  let bestLabel = '—'
  let best = 0
  for (const { label, pcs } of PENTATONIC_TEMPLATES) {
    const sc = templateScore(norm, pcs)
    if (sc > best) {
      best = sc
      bestLabel = label
    }
  }
  if (best < 0.28) {
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
  return bestLabel
}

export type PitchClassHistogram = {
  /** Count a stable pitch reading (ignores silence / invalid). */
  add(reading: PitchReading | null | undefined): void
  getBins(): number[]
  getBestLabel(): string
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
