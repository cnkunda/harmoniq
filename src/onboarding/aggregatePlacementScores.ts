import { PLACEMENT_SKILL_NODES } from '@/src/onboarding/placementPhrases'
import type { ScoreResult } from '@/src/types'

/** Average each skill node across successful placement scores. */
export function aggregatePlacementNodeScores(results: ScoreResult[]): Record<string, number> {
  const out: Record<string, number> = {}
  for (const id of PLACEMENT_SKILL_NODES) {
    const vals = results
      .map((r) => r.node_scores[id as string])
      .filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
    if (vals.length === 0) out[id] = 0.2
    else out[id] = vals.reduce((a, b) => a + b, 0) / vals.length
  }
  return out
}

export function aggregatePlacementCoachMetrics(results: ScoreResult[]): {
  pitch_avg: number
  phrasing_avg: number
  timing_avg: number
  bend_error_cents_avg: number
} {
  const n = results.length
  if (n === 0) {
    return { pitch_avg: 0.5, phrasing_avg: 0.5, timing_avg: 0.5, bend_error_cents_avg: 40 }
  }
  const pitch_avg = results.reduce((s, r) => s + r.pitch_accuracy, 0) / n
  const phrasing_avg = results.reduce((s, r) => s + r.phrasing_score, 0) / n
  const timing_avg = results.reduce((s, r) => s + r.rushing_score, 0) / n
  const bend_error_cents_avg = results.reduce((s, r) => s + r.bend_pitch_error_cents, 0) / n
  return { pitch_avg, phrasing_avg, timing_avg, bend_error_cents_avg }
}
