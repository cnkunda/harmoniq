/**
 * AlphaTab runtime diagnostics (Commit 61). Opt-in in dev; production stays inert when disabled.
 *
 * **Sync:** The standalone harness (`assets/alphatab-harness/index.html`) and any DOM-side
 * checks duplicate these numbers for `breachFlags`. When you change a threshold here, update
 * those call sites — see `assets/alphatab-harness/README.md` §Threshold sync.
 */

/** Aggregate harness/DOM metrics over this window (Implementation Notes). */
export const RUNTIME_DIAG_WINDOW_MS = 5000

/** Aligns with docs/MANUAL_QA.md — Phase 5 drift threshold vs Listen sync; note-event rate ~33 Hz. */
export const RUNTIME_DIAG_THRESHOLDS = {
  /** Same order of magnitude as Listen ±80 ms gate (MANUAL_QA Phase 5). */
  driftMsFail: 80,
  /** Bridge caps ~31 ms min interval → ~32 Hz; FAIL above this sustained. */
  noteEventHzFail: 36,
  /** Very high renderFinished rate suggests layout thrash (triage only). */
  renderFpsFail: 90,
  /** RN WebView bridge ping (diagnostic); tune if false positives on slow devices. */
  bridgeLatencyMsFail: 50,
} as const

export function isAlphaTabRuntimeDiagEnabled(): boolean {
  if (typeof __DEV__ !== 'undefined' && !__DEV__) return false
  try {
    const v =
      typeof process !== 'undefined' && process.env && process.env.EXPO_PUBLIC_ALPHATAB_RUNTIME_DIAG
    if (v === '0' || v === 'false') return false
  } catch {
    /* ignore */
  }
  return true
}
