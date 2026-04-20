import { describe, expect, it } from 'vitest'

import { sessionAccuracy01FromScoreResult, timingStability01FromScoreResult } from '@/src/session/scoreProgressSignals'
import type { ScoreResult } from '@/src/types'

function baseResult(over: Partial<ScoreResult>): ScoreResult {
  return {
    pitch_accuracy: 0.7,
    phrasing_score: 0.6,
    bend_pitch_error_cents: 20,
    rushing_score: 0.75,
    note_duration_deltas: [],
    node_scores: {
      pitch_accuracy: 0.7,
      phrasing: 0.6,
      timing: 0.75,
      bend_accuracy: 0.5,
      vibrato_control: 0.5,
    },
    waveform_comparison: { user_wav_base64: '', reference_wav_base64: '' },
    ...over,
  }
}

describe('sessionAccuracy01FromScoreResult', () => {
  it('returns clamped pitch_accuracy', () => {
    expect(sessionAccuracy01FromScoreResult(baseResult({ pitch_accuracy: 0.85 }))).toBe(0.85)
  })
})

describe('timingStability01FromScoreResult', () => {
  it('falls back to rushing_score without diagnostics', () => {
    expect(timingStability01FromScoreResult(baseResult({ rushing_score: 0.8 }))).toBe(0.8)
  })

  it('incorporates timing residuals when diagnostics exist', () => {
    const withDiag = baseResult({
      rushing_score: 0.9,
      diagnostics: {
        signal_quality: 0.8,
        voiced_ratio: 0.7,
        harmonic_ratio: 0.5,
        timing_residual_p50_ms: 40,
        timing_residual_p95_ms: 80,
        reliability_flags: [],
      },
    })
    const t = timingStability01FromScoreResult(withDiag)
    expect(t).toBeGreaterThan(0)
    expect(t).toBeLessThanOrEqual(1)
    const rushOnly = timingStability01FromScoreResult(baseResult({ rushing_score: 0.9 }))
    expect(Math.abs(t - rushOnly)).toBeGreaterThan(0.02)
  })
})
