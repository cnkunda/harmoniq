/**
 * Pure helpers for bar-aligned loop windows from monotonic `bar_timestamps` (seconds).
 */

export function barIndexAtOrBeforeTime(barTimestampsSec: readonly number[], tSec: number): number {
  if (barTimestampsSec.length === 0) return 0
  const t = Number.isFinite(tSec) ? Math.max(0, tSec) : 0
  let lo = 0
  let hi = barTimestampsSec.length - 1
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2)
    if (barTimestampsSec[mid]! <= t) lo = mid
    else hi = mid - 1
  }
  return lo
}

/**
 * Inclusive start bar index and exclusive end bar index.
 * Ensures at least one bar span when possible.
 */
export function clampBarLoopRange(
  startBarIndex: number,
  endBarIndexExclusive: number,
  barCount: number,
): { startBarIndex: number; endBarIndexExclusive: number } {
  if (barCount < 2) {
    return { startBarIndex: 0, endBarIndexExclusive: Math.max(1, barCount) }
  }
  let start = Math.floor(startBarIndex)
  let endEx = Math.floor(endBarIndexExclusive)
  start = Math.max(0, Math.min(start, barCount - 2))
  endEx = Math.max(start + 1, Math.min(endEx, barCount))
  return { startBarIndex: start, endBarIndexExclusive: endEx }
}

/**
 * Exact loop window in seconds: [startSec, endSec) where endSec is the next bar boundary
 * or extrapolated when the range touches the last bar.
 */
export function barRangeToSeconds(
  barTimestampsSec: readonly number[],
  startBarIndex: number,
  endBarIndexExclusive: number,
  beatSec: number,
): { startSec: number; endSec: number } | null {
  if (barTimestampsSec.length === 0) return null
  const { startBarIndex: s, endBarIndexExclusive: e } = clampBarLoopRange(
    startBarIndex,
    endBarIndexExclusive,
    barTimestampsSec.length,
  )
  const startSec = barTimestampsSec[s]!
  let endSec: number
  if (e < barTimestampsSec.length) {
    endSec = barTimestampsSec[e]!
  } else {
    const lastStart = barTimestampsSec[barTimestampsSec.length - 1]!
    const span = Math.max(0.4, beatSec * 4)
    endSec = lastStart + span
  }
  if (!(endSec > startSec + 0.05)) return null
  return { startSec, endSec }
}

/** Pick index of the smallest finite numeric entry (lower = worse confidence). */
export function pickLowestNumericBarIndex(values: readonly unknown[]): number | null {
  let bestI: number | null = null
  let bestV = Infinity
  for (let i = 0; i < values.length; i += 1) {
    const v = values[i]
    const n = typeof v === 'number' && Number.isFinite(v) ? v : null
    if (n == null) continue
    if (n < bestV) {
      bestV = n
      bestI = i
    }
  }
  return bestI
}
