import { describe, expect, it } from 'vitest'

import { aggregatePlacementCoachMetrics, aggregatePlacementNodeScores } from '@/src/onboarding/aggregatePlacementScores'
import type { ScoreResult } from '@/src/types'

function mockResult(over: Partial<ScoreResult>): ScoreResult {
  return {
    pitch_accuracy: 0.5,
    phrasing_score: 0.5,
    bend_pitch_error_cents: 30,
    rushing_score: 0.5,
    note_duration_deltas: [],
    node_scores: {
      pitch_accuracy: 0.5,
      phrasing: 0.5,
      timing: 0.5,
      bend_accuracy: 0.5,
      vibrato_control: 0.5,
    },
    waveform_comparison: { user_wav_base64: '', reference_wav_base64: '' },
    ...over,
  }
}

describe('aggregatePlacementNodeScores', () => {
  it('combines winsorized mean and confidence-weighted mean per node', () => {
    const r = aggregatePlacementNodeScores([
      mockResult({ node_scores: { pitch_accuracy: 0.8, phrasing: 0.2, timing: 0.9, bend_accuracy: 0.7, vibrato_control: 0.6 } }),
      mockResult({ node_scores: { pitch_accuracy: 0.4, phrasing: 0.4, timing: 0.5, bend_accuracy: 0.5, vibrato_control: 0.5 } }),
      mockResult({ node_scores: { pitch_accuracy: 0.6, phrasing: 0.6, timing: 0.7, bend_accuracy: 0.55, vibrato_control: 0.55 } }),
    ])
    expect(r.pitch_accuracy).toBeCloseTo(0.6, 5)
    expect(r.phrasing).toBeCloseTo(0.4, 5)
  })

  it('reduces impact of one catastrophic pitch_accuracy outlier vs naive mean', () => {
    const hi = {
      pitch_accuracy: 0.9,
      phrasing: 0.55,
      timing: 0.55,
      bend_accuracy: 0.5,
      vibrato_control: 0.5,
    }
    const outlier = { ...hi, pitch_accuracy: 0.05 }
    const r = aggregatePlacementNodeScores([
      mockResult({ node_scores: outlier }),
      mockResult({ node_scores: hi }),
      mockResult({ node_scores: { ...hi, pitch_accuracy: 0.88 } }),
    ])
    const naiveMean = (0.05 + 0.9 + 0.88) / 3
    expect(r.pitch_accuracy).toBeGreaterThan(naiveMean + 0.08)
  })
})

describe('aggregatePlacementCoachMetrics', () => {
  it('confidence-weights top-level metrics', () => {
    const m = aggregatePlacementCoachMetrics([
      mockResult({ pitch_accuracy: 1, phrasing_score: 0, rushing_score: 0.5, bend_pitch_error_cents: 10 }),
      mockResult({ pitch_accuracy: 0, phrasing_score: 1, rushing_score: 0.5, bend_pitch_error_cents: 30 }),
    ])
    expect(m.pitch_avg).toBe(0.5)
    expect(m.phrasing_avg).toBe(0.5)
    expect(m.timing_avg).toBe(0.5)
    expect(m.bend_error_cents_avg).toBe(20)
    expect(['low', 'medium', 'high']).toContain(m.placement_confidence)
    expect(Array.isArray(m.reliability_flags)).toBe(true)
  })
})
