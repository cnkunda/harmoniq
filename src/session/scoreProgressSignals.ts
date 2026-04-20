import type { ScoreResult } from '@/src/types'

function clamp01(v: number): number {
  if (!Number.isFinite(v)) return 0
  if (v <= 0) return 0
  if (v >= 1) return 1
  return v
}

/** Top-level pitch accuracy from POST /score — drives SM-2 accuracy lane. */
export function sessionAccuracy01FromScoreResult(result: ScoreResult): number {
  return clamp01(result.pitch_accuracy)
}

/**
 * Session-level timing stability (0–1) for SM-2 composite.
 * Blends `rushing_score` with residual timing from diagnostics so the timing lane
 * is not a duplicate of the per-node scalar when residuals are present.
 */
export function timingStability01FromScoreResult(result: ScoreResult): number {
  const rush = clamp01(result.rushing_score)
  const d = result.diagnostics
  if (!d) return rush
  const p50 = Number.isFinite(d.timing_residual_p50_ms) ? Math.max(0, d.timing_residual_p50_ms) : null
  const p95 = Number.isFinite(d.timing_residual_p95_ms) ? Math.max(0, d.timing_residual_p95_ms) : null
  if (p50 == null && p95 == null) return rush
  const severity = (p50 ?? 0) + (p95 ?? 0) * 0.35
  const fromResidual = clamp01(1 - Math.min(1, severity / 150))
  return clamp01(rush * 0.5 + fromResidual * 0.5)
}
