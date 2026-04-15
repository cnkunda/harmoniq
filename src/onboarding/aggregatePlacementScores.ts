import { PLACEMENT_SKILL_NODES } from '@/src/onboarding/placementPhrases'
import type { ScoreResult } from '@/src/types'

function clamp01(v: number): number {
  if (!Number.isFinite(v)) return 0
  if (v <= 0) return 0
  if (v >= 1) return 1
  return v
}

function winsorizedAverage(values: number[], trimCount = 1): number {
  if (values.length === 0) return 0
  if (values.length < 3 || trimCount <= 0) {
    return values.reduce((a, b) => a + b, 0) / values.length
  }
  const sorted = [...values].sort((a, b) => a - b)
  const min = sorted[Math.min(trimCount, sorted.length - 1)]
  const max = sorted[Math.max(0, sorted.length - 1 - trimCount)]
  const normalized = sorted.map((v) => Math.min(max, Math.max(min, v)))
  return normalized.reduce((a, b) => a + b, 0) / normalized.length
}

function confidenceWeight(result: ScoreResult): number {
  const confidence = result.reliability?.confidence ?? 'medium'
  const signal = clamp01(result.reliability?.signal_quality ?? result.diagnostics?.signal_quality ?? 0.6)
  const confWeight = confidence === 'high' ? 1 : confidence === 'medium' ? 0.78 : 0.55
  return Math.max(0.25, confWeight * (0.45 + signal * 0.55))
}

function weightedAverage(values: number[], weights: number[]): number {
  if (values.length === 0 || weights.length !== values.length) return 0
  let weightSum = 0
  let valueSum = 0
  for (let i = 0; i < values.length; i += 1) {
    const w = Number.isFinite(weights[i]) ? Math.max(0, weights[i]) : 0
    weightSum += w
    valueSum += values[i] * w
  }
  if (weightSum <= 0) return values.reduce((a, b) => a + b, 0) / values.length
  return valueSum / weightSum
}

/** Robust node baseline: winsorized average + confidence weighting. */
export function aggregatePlacementNodeScores(results: ScoreResult[]): Record<string, number> {
  const out: Record<string, number> = {}
  for (const id of PLACEMENT_SKILL_NODES) {
    const vals = results.map((r) => r.node_scores[id as string]).filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
    if (vals.length === 0) {
      out[id] = 0.2
      continue
    }
    const ws = results
      .map((r) => r.node_scores[id as string])
      .map((v, i) => (typeof v === 'number' && Number.isFinite(v) ? confidenceWeight(results[i]) : null))
      .filter((v): v is number => typeof v === 'number')
    const robust = winsorizedAverage(vals, 1)
    const weighted = weightedAverage(vals, ws)
    out[id] = clamp01(robust * 0.5 + weighted * 0.5)
  }
  return out
}

export function aggregatePlacementCoachMetrics(results: ScoreResult[]): {
  pitch_avg: number
  phrasing_avg: number
  timing_avg: number
  bend_error_cents_avg: number
  placement_confidence: 'low' | 'medium' | 'high'
  reliability_flags: string[]
} {
  const n = results.length
  if (n === 0) {
    return {
      pitch_avg: 0.5,
      phrasing_avg: 0.5,
      timing_avg: 0.5,
      bend_error_cents_avg: 40,
      placement_confidence: 'low',
      reliability_flags: ['placement_no_data'],
    }
  }
  const weights = results.map(confidenceWeight)
  const pitch_avg = weightedAverage(results.map((r) => clamp01(r.pitch_accuracy)), weights)
  const phrasing_avg = weightedAverage(results.map((r) => clamp01(r.phrasing_score)), weights)
  const timing_avg = weightedAverage(results.map((r) => clamp01(r.rushing_score)), weights)
  const bend_error_cents_avg = weightedAverage(
    results.map((r) => (Number.isFinite(r.bend_pitch_error_cents) ? Math.max(0, r.bend_pitch_error_cents) : 40)),
    weights,
  )
  const flags = new Set<string>()
  for (const r of results) {
    for (const f of r.reliability?.reliability_flags ?? r.diagnostics?.reliability_flags ?? []) flags.add(f)
  }
  const meanWeight = weights.reduce((a, b) => a + b, 0) / weights.length
  const placement_confidence = meanWeight >= 0.8 ? 'high' : meanWeight >= 0.6 ? 'medium' : 'low'
  return { pitch_avg, phrasing_avg, timing_avg, bend_error_cents_avg, placement_confidence, reliability_flags: Array.from(flags) }
}
