/**
 * SmartScroll Bridge — efficient bar seeking using binary search on bar_timestamps.
 * Commit 85: Cross-platform sync between host playback and AlphaTab WebView.
 */

import { barIndexAtOrBeforeTime } from './barLoopBounds'

/**
 * SmartScroll seek result: target bar index and exact timestamp for precise sync.
 */
export type SmartScrollSeekResult = {
  barIndex: number
  barTimestampSec: number
  /** Estimated seek time in ms (for diagnostics). */
  estimatedSeekMs: number
}

/**
 * Perform efficient binary search on bar_timestamps to find the bar for a given playback position.
 * O(log n) complexity, suitable for real-time sync during playback.
 *
 * @param barTimestampsSec - Monotonic array of bar start times in seconds
 * @param positionSec - Current playback position in seconds
 * @returns Bar index and timestamp for the seek target
 */
const getPerformanceNow = (): number => {
  if (typeof performance !== 'undefined' && performance.now) {
    return performance.now()
  }
  return Date.now()
}

export function seekToBarByTimestamp(
  barTimestampsSec: readonly number[],
  positionSec: number,
): SmartScrollSeekResult {
  const t0 = getPerformanceNow()

  if (barTimestampsSec.length === 0) {
    return { barIndex: 0, barTimestampSec: 0, estimatedSeekMs: 0 }
  }

  const clampedPos = Math.max(0, Number.isFinite(positionSec) ? positionSec : 0)
  const barIndex = barIndexAtOrBeforeTime(barTimestampsSec, clampedPos)
  const barTimestampSec = barTimestampsSec[barIndex] ?? 0

  const elapsed = getPerformanceNow() - t0
  return {
    barIndex,
    barTimestampSec,
    estimatedSeekMs: elapsed,
  }
}

/**
 * Drift correction: adjust target position to account for accumulated sync drift.
 * Used during extended playback sessions to prevent drift from compounding.
 *
 * @param currentPositionSec - Current audio position in seconds
 * @param lastSyncPositionSec - Last synced position in seconds
 * @param driftMs - Measured drift in milliseconds (positive = audio ahead, negative = audio behind)
 * @returns Corrected position in seconds
 */
export function correctDrift(
  currentPositionSec: number,
  lastSyncPositionSec: number,
  driftMs: number,
): number {
  // Only apply correction if drift exceeds threshold (avoid jitter)
  // 50ms threshold balances responsiveness with stability
  const DRIFT_THRESHOLD_MS = 50
  if (Math.abs(driftMs) < DRIFT_THRESHOLD_MS) {
    return currentPositionSec
  }

  // Apply gentle correction (10% of drift per sync) to avoid jarring jumps
  // Gradual correction prevents audible jumps in playback position
  const correctionFactor = 0.1
  const correctionSec = (driftMs / 1000) * correctionFactor
  return currentPositionSec - correctionSec
}

/**
 * SmartScroll state for tracking sync across playback sessions.
 */
export type SmartScrollState = {
  lastSyncPositionSec: number
  accumulatedDriftMs: number
  syncCount: number
}

/**
 * Create initial SmartScroll state.
 */
export function createSmartScrollState(): SmartScrollState {
  return {
    lastSyncPositionSec: 0,
    accumulatedDriftMs: 0,
    syncCount: 0,
  }
}

/**
 * Update SmartScroll state after a sync operation.
 *
 * @param state - Current state
 * @param currentPositionSec - Current audio position in seconds
 * @param targetBarTimestampSec - Target bar timestamp in seconds
 * @param actualSeekMs - Actual time taken for seek (measured)
 * @returns Updated state
 */
export function updateSmartScrollState(
  state: SmartScrollState,
  currentPositionSec: number,
  targetBarTimestampSec: number,
  actualSeekMs: number,
): SmartScrollState {
  const expectedPositionSec = state.lastSyncPositionSec + (currentPositionSec - state.lastSyncPositionSec)
  const driftMs = (currentPositionSec - targetBarTimestampSec) * 1000

  // Smooth drift accumulation (exponential moving average)
  // 0.2 smoothing factor gives 20% weight to new measurements, 80% to history
  // This filters out transient noise while adapting to real drift
  const DRIFT_SMOOTHING = 0.2
  const smoothedDrift = state.accumulatedDriftMs * (1 - DRIFT_SMOOTHING) + driftMs * DRIFT_SMOOTHING

  return {
    lastSyncPositionSec: currentPositionSec,
    accumulatedDriftMs: smoothedDrift,
    syncCount: state.syncCount + 1,
  }
}
