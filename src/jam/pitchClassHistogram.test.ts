import { describe, expect, it } from 'vitest'

import { bestScaleLabelFromBins, createPitchClassHistogram, getBestScale } from '@/src/jam/pitchClassHistogram'

describe('bestScaleLabelFromBins', () => {
  it('returns — for empty', () => {
    expect(bestScaleLabelFromBins(new Array(12).fill(0))).toBe('—')
    expect(bestScaleLabelFromBins([])).toBe('—')
  })

  it('prefers A minor pentatonic when A C D E G weighted', () => {
    const bins = [2, 0, 2, 0, 2, 0, 0, 2, 0, 9, 0, 0] // C D E G A
    const label = bestScaleLabelFromBins(bins)
    expect(label).toContain('A minor pentatonic')
  })
})

describe('getBestScale', () => {
  it('matches G major pentatonic fixture (G A B D E)', () => {
    const bins = [0, 0, 5, 0, 5, 0, 0, 9, 0, 5, 0, 5] // D E G A B
    const m = getBestScale(bins)
    expect(m).not.toBeNull()
    expect(m!.label).toBe('G major pentatonic')
    expect(m!.rootMidi).toBe(7)
    expect(m!.pitchClasses).toEqual([7, 9, 11, 2, 4])
  })

  it('matches A minor pentatonic fixture', () => {
    const bins = [2, 0, 2, 0, 2, 0, 0, 2, 0, 9, 0, 0]
    const m = getBestScale(bins)
    expect(m).not.toBeNull()
    expect(m!.label).toBe('A minor pentatonic')
    expect(m!.intervals).toEqual([0, 3, 5, 7, 10])
  })

  it('returns null when no template clears threshold', () => {
    const bins = new Array(12).fill(0)
    bins[6] = 1 /* F# only — not in any built-in pentatonic template */
    expect(getBestScale(bins)).toBeNull()
  })
})

describe('createPitchClassHistogram', () => {
  it('does not emit map under 10s', () => {
    const h = createPitchClassHistogram()
    for (let i = 0; i < 50; i += 1) h.add({ hz: 440, midi: 69, cents: 0, noteName: 'A4', rms: 0.02 })
    expect(h.toScalePositionMap(9)).toEqual({})
  })

  it('emits non-empty map when duration and hits thresholds met', () => {
    const h = createPitchClassHistogram()
    for (let i = 0; i < 30; i += 1) h.add({ hz: 440, midi: 69, cents: 0, noteName: 'A4', rms: 0.02 })
    const m = h.toScalePositionMap(10.5)
    expect(Object.keys(m).length).toBeGreaterThan(0)
    expect(m.pc_A).toBeCloseTo(1, 5)
  })

  it('getBestScale reads live bins', () => {
    const h = createPitchClassHistogram()
    for (let i = 0; i < 40; i += 1) {
      h.add({ hz: 392, midi: 67, cents: 0, noteName: 'G4', rms: 0.02 })
      h.add({ hz: 440, midi: 69, cents: 0, noteName: 'A4', rms: 0.02 })
      h.add({ hz: 493.88, midi: 71, cents: 0, noteName: 'B4', rms: 0.02 })
      h.add({ hz: 587.33, midi: 74, cents: 0, noteName: 'D5', rms: 0.02 })
      h.add({ hz: 659.25, midi: 76, cents: 0, noteName: 'E5', rms: 0.02 })
    }
    const m = h.getBestScale()
    expect(m?.label).toBe('G major pentatonic')
  })
})
