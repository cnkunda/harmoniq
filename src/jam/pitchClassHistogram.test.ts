import { describe, expect, it } from 'vitest'

import { bestScaleLabelFromBins, createPitchClassHistogram, getBestScale, getBestScales } from '@/src/jam/pitchClassHistogram'

describe('bestScaleLabelFromBins', () => {
  it('returns — for empty', () => {
    expect(bestScaleLabelFromBins(new Array(12).fill(0))).toBe('—')
    expect(bestScaleLabelFromBins([])).toBe('—')
  })

  it('prefers A Minor Pentatonic when A C D E G weighted', () => {
    const bins = [2, 0, 2, 0, 2, 0, 0, 2, 0, 9, 0, 0] // C D E G A
    const label = bestScaleLabelFromBins(bins)
    expect(label).toContain('Minor Pentatonic')
  })
})

describe('getBestScale', () => {
  it('matches G Major Pentatonic fixture (G A B D E)', () => {
    const bins = [0, 0, 5, 0, 5, 0, 0, 9, 0, 5, 0, 5] // D E G A B
    const m = getBestScale(bins)
    expect(m).not.toBeNull()
    expect(m!.label).toBe('G Major Pentatonic')
    expect(m!.rootMidi).toBe(7)
    expect(m!.pitchClasses).toEqual([7, 9, 11, 2, 4])
  })

  it('matches A Minor Pentatonic fixture', () => {
    const bins = [2, 0, 2, 0, 2, 0, 0, 2, 0, 9, 0, 0]
    const m = getBestScale(bins)
    expect(m).not.toBeNull()
    expect(m!.label).toBe('A Minor Pentatonic')
    expect(m!.intervals).toEqual([0, 3, 5, 7, 10])
  })

  it('returns null when no scale clears threshold', () => {
    const bins = new Array(12).fill(0)
    bins[6] = 1 /* F# only — not enough for any scale to clear threshold */
    expect(getBestScale(bins)).toBeNull()
  })
})

describe('getBestScales', () => {
  it('returns top 3 candidates for C major (ionian) pitch set', () => {
    const bins = new Array(12).fill(0)
    bins[0] = 9  // C (modal root)
    bins[2] = 3  // D
    bins[4] = 3  // E
    bins[5] = 3  // F
    bins[7] = 3  // G
    bins[9] = 3  // A
    bins[11] = 3 // B
    const results = getBestScales(bins, 3)
    expect(results.length).toBeGreaterThanOrEqual(1)
    expect(results.length).toBeLessThanOrEqual(3)
    expect(results[0]!.inferred_mode).toBe('ionian')
    expect(results[0]!.matchScore).toBeGreaterThanOrEqual(results[1]?.matchScore ?? 0)
  })

  it('returns empty for sparse input', () => {
    expect(getBestScales(new Array(12).fill(0), 3)).toEqual([])
    expect(getBestScales([], 3)).toEqual([])
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

  it('getBestScale reads live bins with clear G root', () => {
    const h = createPitchClassHistogram()
    // Feed more Gs to establish a clear root
    for (let i = 0; i < 60; i += 1) {
      h.add({ hz: 392, midi: 67, cents: 0, noteName: 'G4', rms: 0.02 })
    }
    for (let i = 0; i < 40; i += 1) {
      h.add({ hz: 440, midi: 69, cents: 0, noteName: 'A4', rms: 0.02 })
      h.add({ hz: 493.88, midi: 71, cents: 0, noteName: 'B4', rms: 0.02 })
      h.add({ hz: 587.33, midi: 74, cents: 0, noteName: 'D5', rms: 0.02 })
      h.add({ hz: 659.25, midi: 76, cents: 0, noteName: 'E5', rms: 0.02 })
    }
    const m = h.getBestScale()
    expect(m?.label).toBe('G Major Pentatonic')
    expect(m?.inferred_mode).toBe('major_pentatonic')
    expect(m?.matchScore).toBeGreaterThan(0.5)
  })

  it('getBestScales returns multiple candidates from live bins', () => {
    const h = createPitchClassHistogram()
    for (let i = 0; i < 60; i += 1) {
      h.add({ hz: 392, midi: 67, cents: 0, noteName: 'G4', rms: 0.02 })
    }
    for (let i = 0; i < 40; i += 1) {
      h.add({ hz: 440, midi: 69, cents: 0, noteName: 'A4', rms: 0.02 })
      h.add({ hz: 493.88, midi: 71, cents: 0, noteName: 'B4', rms: 0.02 })
      h.add({ hz: 587.33, midi: 74, cents: 0, noteName: 'D5', rms: 0.02 })
      h.add({ hz: 659.25, midi: 76, cents: 0, noteName: 'E5', rms: 0.02 })
    }
    const results = h.getBestScales(3)
    expect(results.length).toBeGreaterThanOrEqual(1)
    expect(results.length).toBeLessThanOrEqual(3)
    expect(results[0]!.inferred_mode).toBe('major_pentatonic')
  })
})
