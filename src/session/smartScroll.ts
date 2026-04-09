/**
 * SmartScroll (PRIORITIES §23): map audio timeline → bar index → AlphaTab `scrollToBar`.
 * Resync when bar changes or playback drifts > threshold vs wall-clock expectation.
 */

export const DEFAULT_SMART_SCROLL_DRIFT_SEC = 0.1

/** Sort ascending, drop non-finite, dedupe within tolerance. */
export function normalizeBarTimestamps(raw: readonly number[] | undefined | null): number[] {
  if (!raw?.length) return []
  const tol = 1e-3
  const sorted = raw
    .map((t) => Number(t))
    .filter((t) => Number.isFinite(t) && t >= 0)
    .sort((a, b) => a - b)
  const out: number[] = []
  for (const t of sorted) {
    if (!out.length || t - out[out.length - 1]! > tol) out.push(t)
  }
  return out
}

/**
 * Largest index `i` such that `timestamps[i] <= playbackSeconds`.
 * Clamps to valid range; empty timestamps → 0.
 */
export function barIndexForPlaybackSeconds(
  barTimestamps: readonly number[],
  playbackSeconds: number,
): number {
  if (barTimestamps.length === 0) return 0
  const t = Number.isFinite(playbackSeconds) ? Math.max(0, playbackSeconds) : 0
  let lo = 0
  let hi = barTimestamps.length - 1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    const v = barTimestamps[mid]!
    if (v <= t) lo = mid + 1
    else hi = mid - 1
  }
  return Math.max(0, Math.min(barTimestamps.length - 1, hi))
}

export type SmartScrollSample = {
  wallTimeMs: number
  playbackSeconds: number
}

export type SmartScrollDecisionInput = {
  barTimestamps: readonly number[]
  playbackSeconds: number
  playbackRate: number
  lastEmittedBarIndex: number | null
  lastSample: SmartScrollSample | null
  driftThresholdSec?: number
}

export type SmartScrollDecision = {
  shouldScroll: boolean
  barIndex: number
  nextSample: SmartScrollSample
}

/**
 * Emit scroll when the active bar index changes, or when playback has drifted from
 * wall-time expectation by more than `driftThresholdSec` (same-bar resync).
 */
export function decideSmartScroll(input: SmartScrollDecisionInput): SmartScrollDecision {
  const driftThresholdSec = input.driftThresholdSec ?? DEFAULT_SMART_SCROLL_DRIFT_SEC
  const ts = input.barTimestamps
  const nowMs = Date.now()
  const rate =
    Number.isFinite(input.playbackRate) && input.playbackRate > 0 ? input.playbackRate : 1
  const playback = Number.isFinite(input.playbackSeconds) ? input.playbackSeconds : 0
  const idealBar = barIndexForPlaybackSeconds(ts, playback)
  const nextSample: SmartScrollSample = { wallTimeMs: nowMs, playbackSeconds: playback }

  if (ts.length === 0) {
    return { shouldScroll: false, barIndex: 0, nextSample }
  }

  let shouldScroll = false
  if (input.lastEmittedBarIndex === null) {
    shouldScroll = true
  } else if (idealBar !== input.lastEmittedBarIndex) {
    shouldScroll = true
  } else if (input.lastSample != null) {
    const wallDeltaSec = (nowMs - input.lastSample.wallTimeMs) / 1000
    const expectedPlayback = input.lastSample.playbackSeconds + wallDeltaSec * rate
    if (Math.abs(playback - expectedPlayback) > driftThresholdSec) {
      shouldScroll = true
    }
  }

  return { shouldScroll, barIndex: idealBar, nextSample }
}
