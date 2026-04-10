import { describe, expect, it } from 'vitest'

import { bestScaleLabelFromBins, createPitchClassHistogram } from '@/src/jam/pitchClassHistogram'

describe('bestScaleLabelFromBins', () => {
  it('returns — for empty', () => {
    expect(bestScaleLabelFromBins(new Array(12).fill(0))).toBe('—')
    expect(bestScaleLabelFromBins([])).toBe('—')
  })

  it('prefers A minor pent when A C D E G weighted', () => {
    const bins = [2, 0, 2, 0, 2, 0, 0, 2, 0, 9, 0, 0] // C D E G A
    const label = bestScaleLabelFromBins(bins)
    expect(label).toContain('A minor pent')
  })
})

describe('createPitchClassHistogram', () => {
  it('does not emit map under 10s', () => {
    const h = createPitchClassHistogram()
    for (let i = 0; i < 50; i += 1) h.add({ hz: 440, midi: 69, cents: 0, noteName: 'A4' })
    expect(h.toScalePositionMap(9)).toEqual({})
  })

  it('emits non-empty map when duration and hits thresholds met', () => {
    const h = createPitchClassHistogram()
    for (let i = 0; i < 30; i += 1) h.add({ hz: 440, midi: 69, cents: 0, noteName: 'A4' })
    const m = h.toScalePositionMap(10.5)
    expect(Object.keys(m).length).toBeGreaterThan(0)
    expect(m.pc_A).toBeCloseTo(1, 5)
  })
})
