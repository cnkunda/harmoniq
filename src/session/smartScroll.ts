// replaced by external media sync (PRIORITIES §45)
// Keep exported symbols as no-op compatibility shims for existing imports.

export const DEFAULT_SMART_SCROLL_DRIFT_SEC = 0.1

export function normalizeBarTimestamps(raw: readonly number[] | undefined | null): number[] {
  return raw ? [...raw] : []
}

export function barIndexForPlaybackSeconds(_barTimestamps: readonly number[], _playbackSeconds: number): number {
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

export function decideSmartScroll(input: SmartScrollDecisionInput): SmartScrollDecision {
  return {
    shouldScroll: false,
    barIndex: input.lastEmittedBarIndex ?? 0,
    nextSample: { wallTimeMs: Date.now(), playbackSeconds: input.playbackSeconds || 0 },
  }
}
