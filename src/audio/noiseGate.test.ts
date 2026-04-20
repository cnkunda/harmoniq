import { describe, expect, it } from 'vitest'

import {
  ambientRmsAverage,
  effectiveRmsSignalGate,
  linearRatioFromDb,
  noiseGateThresholdFromAmbientSamples,
  NOISE_GATE_HEADROOM_DB,
} from '@/src/audio/noiseGate'

describe('noiseGate', () => {
  it('ambient average', () => {
    expect(ambientRmsAverage([0.1, 0.3])).toBe(0.2)
    expect(ambientRmsAverage([])).toBe(0)
  })

  it('applies 6 dB headroom to ambient RMS', () => {
    const samples = [0.01, 0.01, 0.01]
    const avg = 0.01
    expect(noiseGateThresholdFromAmbientSamples(samples)).toBeCloseTo(avg * linearRatioFromDb(NOISE_GATE_HEADROOM_DB), 6)
  })

  it('effectiveRmsSignalGate picks the stricter floor', () => {
    expect(effectiveRmsSignalGate(0.004, 0.02)).toBe(0.02)
    expect(effectiveRmsSignalGate(0.08, 0.02)).toBe(0.08)
    expect(effectiveRmsSignalGate(0.05, null)).toBe(0.05)
    expect(effectiveRmsSignalGate(0.05, undefined)).toBe(0.05)
  })
})
