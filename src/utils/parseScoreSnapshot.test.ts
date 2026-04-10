import { describe, expect, it } from 'vitest'

import { parseScoreSnapshot } from '@/src/utils/parseScoreSnapshot'

describe('parseScoreSnapshot', () => {
  it('returns null for empty', () => {
    expect(parseScoreSnapshot(null)).toBeNull()
    expect(parseScoreSnapshot('')).toBeNull()
  })

  it('parses minimal score with empty waveforms', () => {
    const raw = JSON.stringify({
      pitch_accuracy: 0.8,
      phrasing_score: 0.7,
      rushing_score: 0.65,
      bend_pitch_error_cents: 12,
      node_scores: { pitch_accuracy: 0.8, phrasing: 0.7, timing: 0.65 },
    })
    const s = parseScoreSnapshot(raw)
    expect(s).not.toBeNull()
    expect(s!.pitch_accuracy).toBe(0.8)
    expect(s!.waveform_comparison.user_wav_base64).toBe('')
    expect(s!.waveform_comparison.reference_wav_base64).toBe('')
  })
})
