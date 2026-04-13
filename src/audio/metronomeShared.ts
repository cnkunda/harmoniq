/** Shared beat math for web + native metronomes (PRIORITIES §50). */

export type MetronomeSubdivision = 1 | 2 | 4

const MIN_DELTA = 0.04
const MAX_DELTA = 2.3

function sortedBeatTimes(grid: number[]): number[] {
  return [...grid].filter((t) => Number.isFinite(t)).sort((a, b) => a - b)
}

/** Median consecutive beat spacing (filters outliers vs first-pair-only period). */
export function medianBeatIntervalSeconds(sortedAsc: number[]): number | null {
  if (sortedAsc.length < 2) return null
  const deltas: number[] = []
  for (let i = 0; i < sortedAsc.length - 1; i++) {
    const d = sortedAsc[i + 1]! - sortedAsc[i]!
    if (d >= MIN_DELTA && d <= MAX_DELTA) deltas.push(d)
  }
  if (deltas.length === 0) return null
  deltas.sort((a, b) => a - b)
  const mid = Math.floor(deltas.length / 2)
  return deltas.length % 2 === 1 ? deltas[mid]! : (deltas[mid - 1]! + deltas[mid]!) / 2
}

export function beatPeriodSeconds(grid: number[], tempoBpm: number): number {
  const sorted = sortedBeatTimes(grid)
  const med = medianBeatIntervalSeconds(sorted)
  if (med != null) return Math.max(MIN_DELTA, med)
  if (sorted.length >= 2) return Math.max(MIN_DELTA, sorted[1]! - sorted[0]!)
  if (tempoBpm > 0) return 60 / tempoBpm
  return 0.5
}

export function gridAnchorSeconds(grid: number[]): number {
  const sorted = sortedBeatTimes(grid)
  return sorted.length > 0 ? sorted[0]! : 0
}

/** Phase anchor for sparse / synthetic grids: align to first bar when beats are missing or few. */
export function syntheticPhaseAnchorSeconds(grid: number[], barTimestamps: number[] | undefined): number {
  const sorted = sortedBeatTimes(grid)
  const ga = gridAnchorSeconds(grid)
  const b0 =
    barTimestamps && barTimestamps.length > 0 && Number.isFinite(barTimestamps[0]!) ? barTimestamps[0]! : null
  if (b0 == null) return ga
  if (sorted.length === 0) return Math.max(0, b0)
  if (sorted.length < 4) return Math.min(b0, ga)
  return ga
}

export type ScheduledClick = { songTime: number; isDownbeat: boolean }

export type CollectClickOptions = {
  /** When set, hi clicks align to bar lines from analysis (else every 4th quarter from anchor). */
  barTimestamps?: number[]
}

function clampIntervalSeconds(raw: number, fallback: number): number {
  if (!Number.isFinite(raw) || raw < MIN_DELTA) return Math.max(MIN_DELTA, fallback)
  if (raw > MAX_DELTA) return Math.max(MIN_DELTA, Math.min(MAX_DELTA, fallback))
  return raw
}

function downbeatThresholdSeconds(periodHint: number): number {
  return Math.min(0.14, Math.max(0.045, periodHint * 0.32))
}

function isNearBarLine(t: number, bars: number[], thr: number): boolean {
  for (let i = 0; i < bars.length; i++) {
    if (Math.abs(t - bars[i]!) < thr) return true
  }
  return false
}

function dedupeClicks(clicks: ScheduledClick[]): ScheduledClick[] {
  clicks.sort((a, b) => a.songTime - b.songTime)
  const out: ScheduledClick[] = []
  for (const c of clicks) {
    const last = out[out.length - 1]
    if (last && Math.abs(c.songTime - last.songTime) < 0.012) {
      last.isDownbeat = last.isDownbeat || c.isDownbeat
      continue
    }
    out.push({ songTime: c.songTime, isDownbeat: c.isDownbeat })
  }
  return out
}

/** Schedule on detected beat intervals so clicks track librosa beat times (stem timeline). */
function collectFromDetectedBeatGrid(
  sorted: number[],
  tempoBpm: number,
  fromSong: number,
  toSong: number,
  subdivision: MetronomeSubdivision,
  barTimestamps: number[] | undefined,
): ScheduledClick[] {
  const tempoPeriod = tempoBpm > 0 ? 60 / tempoBpm : 0.5
  const medianD = medianBeatIntervalSeconds(sorted) ?? tempoPeriod
  const out: ScheduledClick[] = []

  for (let i = 0; i < sorted.length; i++) {
    const b0 = sorted[i]!
    const rawD =
      i + 1 < sorted.length ? sorted[i + 1]! - b0 : medianD
    const d = clampIntervalSeconds(rawD, medianD)
    if (i + 1 < sorted.length && sorted[i + 1]! - b0 < 0.035) continue

    const thr = downbeatThresholdSeconds(d)
    for (let j = 0; j < subdivision; j++) {
      const t = b0 + (d * j) / subdivision
      if (t < fromSong - 1e-4) continue
      if (t > toSong + 1e-4) break
      const onQuarter = j === 0
      let isDownbeat = false
      if (onQuarter) {
        if (barTimestamps && barTimestamps.length > 0) {
          isDownbeat = isNearBarLine(t, barTimestamps, thr)
        } else {
          isDownbeat = i % 4 === 0
        }
      }
      out.push({ songTime: t, isDownbeat })
    }
  }

  let nextStart = sorted[sorted.length - 1]! + medianD
  let idx = sorted.length
  const dTail = Math.max(MIN_DELTA, medianD)
  while (nextStart <= toSong + 1e-4) {
    const thr = downbeatThresholdSeconds(dTail)
    for (let j = 0; j < subdivision; j++) {
      const t = nextStart + (dTail * j) / subdivision
      if (t < fromSong - 1e-4) continue
      if (t > toSong + 1e-4) return dedupeClicks(out)
      const onQuarter = j === 0
      let isDownbeat = false
      if (onQuarter) {
        if (barTimestamps && barTimestamps.length > 0) {
          isDownbeat = isNearBarLine(t, barTimestamps, thr)
        } else {
          isDownbeat = idx % 4 === 0
        }
      }
      out.push({ songTime: t, isDownbeat })
    }
    nextStart += dTail
    idx += 1
  }

  return dedupeClicks(out)
}

/** Regular grid (sparse beat_grid or short clips). */
function collectSyntheticGrid(
  grid: number[],
  tempoBpm: number,
  fromSong: number,
  toSong: number,
  subdivision: MetronomeSubdivision,
  barTimestamps: number[] | undefined,
  anchor: number,
): ScheduledClick[] {
  const period = beatPeriodSeconds(grid, tempoBpm)
  const step = period / subdivision
  if (toSong < fromSong || step <= 0) return []

  const thr = downbeatThresholdSeconds(period)
  let k = Math.ceil((fromSong - anchor) / step - 1e-6)
  let t = anchor + k * step
  const out: ScheduledClick[] = []
  const eps = Math.min(1e-3, step * 0.08)

  while (t <= toSong + 1e-6) {
    if (t >= fromSong - 1e-6) {
      const q = Math.round((t - anchor) / period)
      const onQuarter = Math.abs(t - (anchor + q * period)) < eps
      let isDownbeat = false
      if (onQuarter) {
        if (barTimestamps && barTimestamps.length > 0) {
          isDownbeat = isNearBarLine(t, barTimestamps, thr)
        } else {
          isDownbeat = q % 4 === 0
        }
      }
      out.push({ songTime: t, isDownbeat })
    }
    k += 1
    t = anchor + k * step
  }
  return out
}

/**
 * Click times in [fromSong, toSong] (song seconds), aligned to lesson `beat_grid` when dense enough.
 * Uses `bar_timestamps` for downbeat (hi) emphasis when provided.
 */
export function collectClickTimesInRange(
  grid: number[],
  tempoBpm: number,
  fromSong: number,
  toSong: number,
  subdivision: MetronomeSubdivision,
  opts?: CollectClickOptions,
): ScheduledClick[] {
  const sorted = sortedBeatTimes(grid)
  const bars = opts?.barTimestamps
  if (sorted.length >= 4) {
    return collectFromDetectedBeatGrid(sorted, tempoBpm, fromSong, toSong, subdivision, bars)
  }
  const anchor = syntheticPhaseAnchorSeconds(grid, bars)
  return collectSyntheticGrid(grid, tempoBpm, fromSong, toSong, subdivision, bars, anchor)
}
