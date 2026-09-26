import { matchScaleToPitchClasses, SCALE_DB } from '@/src/music/scales'
import type { PitchReading } from '@/src/pitch/pitchTypes'

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const

function sumBins(bins: ArrayLike<number>): number {
  let s = 0
  for (let i = 0; i < bins.length; i += 1) s += Number(bins[i])
  return s
}

export type BestScaleMatch = {
  label: string
  /** Pitch class 0–11 (tonal center for harness `highlightScaleDegrees`). */
  rootMidi: number
  /** Semitone offsets from root; pass through to AlphaTab tint command. */
  intervals: readonly number[]
  /** Pitch classes in the scale (0–11). */
  pitchClasses: readonly number[]
  /** Normalized overlap score (0–1 scale). */
  matchScore: number
  /** SCALE_DB key for the matched mode, e.g. 'ionian', 'aeolian', 'major_pentatonic'. */
  inferred_mode?: string | null
}

const MATCH_THRESHOLD = 0.28

function modalPitchClass(bins: ArrayLike<number>): number {
  let maxI = 0
  let maxV = -1
  for (let i = 0; i < 12; i += 1) {
    const v = Number(bins[i])
    if (v > maxV) { maxV = v; maxI = i }
  }
  return maxI
}

function observedPCsFromBins(bins: ArrayLike<number>): number[] {
  const pcs: number[] = []
  for (let i = 0; i < 12; i += 1) {
    if (Number(bins[i]) > 0) pcs.push(i)
  }
  return pcs
}

function scaleLabelFromKey(scaleKey: string, rootPitchClass: number): string {
  const entry = SCALE_DB[scaleKey]
  if (!entry) return `${NOTE_NAMES[rootPitchClass]} ${scaleKey}`
  const rootName = NOTE_NAMES[rootPitchClass % 12]
  const displayName = entry.aliases[0] ?? entry.name
  return `${rootName} ${displayName}`
}

function buildMatchFromResult(
  result: { name: string; score: number },
  rootPitchClass: number,
): BestScaleMatch | null {
  const entry = SCALE_DB[result.name]
  if (!entry) return null
  const transposedPCs = entry.intervals.map((i) => (rootPitchClass + i) % 12)
  return {
    label: scaleLabelFromKey(result.name, rootPitchClass),
    rootMidi: rootPitchClass,
    intervals: entry.intervals as readonly number[],
    pitchClasses: transposedPCs as readonly number[],
    matchScore: result.score,
    inferred_mode: result.name,
  }
}

/**
 * Deterministic best scale match for the current histogram using the full SCALE_DB.
 * Returns `null` when energy is too low or no scale clears the confidence threshold.
 */
export function getBestScale(bins: ArrayLike<number>): BestScaleMatch | null {
  const results = getBestScales(bins, 1)
  return results.length > 0 ? results[0]! : null
}

/**
 * Returns top N candidate scale matches from the full SCALE_DB.
 * Uses root alignment via the modal pitch class from the histogram bins.
 * Falls back to exhaustive root search when no result clears the threshold.
 */
export function getBestScales(bins: ArrayLike<number>, count: number = 3): BestScaleMatch[] {
  if (bins.length !== 12) return []
  const total = sumBins(bins)
  if (total <= 0) return []
  const observedPCs = observedPCsFromBins(bins)
  // A scale match needs at least two distinct pitch classes — a single note matches too many scales to be meaningful.
  if (observedPCs.length < 2) return []

  const tryRoot = (root: number): BestScaleMatch[] => {
    const results = matchScaleToPitchClasses(observedPCs, root)
    const out: BestScaleMatch[] = []
    for (const r of results) {
      if (r.score < MATCH_THRESHOLD) break
      const match = buildMatchFromResult(r, root)
      if (match) out.push(match)
      if (out.length >= count) break
    }
    return out
  }

  // Try modal root first (common case)
  const modalRoot = modalPitchClass(bins)
  const modalResults = tryRoot(modalRoot)
  if (modalResults.length > 0 && modalResults[0]!.matchScore >= MATCH_THRESHOLD) {
    return modalResults
  }

  // Fallback: try all 12 roots and pick the combination with the best top score
  let bestResults: BestScaleMatch[] = []
  let bestTopScore = 0
  for (let root = 0; root < 12; root += 1) {
    const r = tryRoot(root)
    if (r.length > 0 && r[0]!.matchScore > bestTopScore) {
      bestTopScore = r[0]!.matchScore
      bestResults = r
    }
  }
  return bestResults
}

/**
 * Best-matching scale label, or dominant pitch-class name if no scale clears threshold.
 */
export function bestScaleLabelFromBins(bins: ArrayLike<number>): string {
  const match = getBestScale(bins)
  if (match) return match.label
  if (bins.length !== 12) return '—'
  const total = sumBins(bins)
  if (total <= 0) return '—'
  const maxI = modalPitchClass(bins)
  if (Number(bins[maxI]) <= 0) return '—'
  return `${NOTE_NAMES[maxI]} (exploring)`
}

export type PitchClassHistogram = {
  /** Count a stable pitch reading (ignores silence / invalid). */
  add(reading: PitchReading | null | undefined): void
  getBins(): number[]
  getBestLabel(): string
  getBestScale(): BestScaleMatch | null
  /** Commit B3: Top N candidate scale matches from the full scale library. */
  getBestScales(count?: number): BestScaleMatch[]
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
      const hz = reading?.hz
      if (!reading || hz == null || !Number.isFinite(hz) || hz <= 0) return
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

    getBestScales(count?: number) {
      return getBestScales(bins, count)
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
