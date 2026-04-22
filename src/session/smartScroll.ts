export const DEFAULT_SMART_SCROLL_DRIFT_SEC = 0.1

/** Predictive scroll offset: scroll 50ms before audio reaches timestamp to eliminate visual lag. */
export const PREDICTIVE_SCROLL_MS = 50

export function normalizeBarTimestamps(raw: readonly number[] | undefined | null): number[] {
  return raw ? [...raw] : []
}

export function barIndexForPlaybackSeconds(
  barTimestamps: readonly number[],
  playbackSeconds: number,
  lookAheadMs: number = 0,
): number {
  if (!barTimestamps.length) return 0
  const t = Number.isFinite(playbackSeconds) ? playbackSeconds + lookAheadMs / 1000 : 0
  for (let i = barTimestamps.length - 1; i >= 0; i -= 1) {
    if (t >= barTimestamps[i]!) return i
  }
  return 0
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

/** Used by tests / tooling; session UI polls via `useSessionSmartScroll` instead. */
export function decideSmartScroll(input: SmartScrollDecisionInput): SmartScrollDecision {
  const bar = barIndexForPlaybackSeconds(input.barTimestamps, input.playbackSeconds)
  const shouldScroll = input.barTimestamps.length > 0 && bar !== input.lastEmittedBarIndex
  return {
    shouldScroll,
    barIndex: bar,
    nextSample: { wallTimeMs: Date.now(), playbackSeconds: input.playbackSeconds || 0 },
  }
}
