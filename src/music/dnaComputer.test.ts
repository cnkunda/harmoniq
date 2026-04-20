import { describe, expect, it } from 'vitest'

import { computePlayerDNA, DNA_MIN_SESSIONS } from '@/src/music/dnaComputer'

describe('computePlayerDNA', () => {
  it('maps known MIDI targets to pitch-class bias (C, E, G)', () => {
    const dna = computePlayerDNA({
      sessions: [
        {
          date: '2026-01-02T12:00:00.000Z',
          review_snapshot: JSON.stringify({
            pitch_accuracy: 0.85,
            phrasing_score: 0.8,
            rushing_score: 0.55,
            harmoniq_dna_capture: {
              note_target_midis: [60, 64, 67],
              note_results: ['hit', 'hit', 'hit'],
              note_target_cells: [
                { row: 2, fret: 3 },
                { row: 2, fret: 7 },
                { row: 1, fret: 5 },
              ],
              bpm_drift_ms: 4,
              bpm_drift_sample_count: 3,
            },
          }),
          nodes_targeted: ['timing', 'pitch_accuracy'],
        },
      ],
      jams: [],
      licks: [],
    })
    expect(dna.pitch_class_bias[0]).toBeCloseTo(1, 5)
    expect(dna.pitch_class_bias[4]).toBeCloseTo(1, 5)
    expect(dna.pitch_class_bias[7]).toBeCloseTo(1, 5)
    expect(dna.position_bias.some((x) => x > 0)).toBe(true)
    expect(dna.technique_frequency.timing).toBe(1)
    expect(dna.technique_frequency.pitch_accuracy).toBe(1)
    expect(dna.eligibleSessionCount).toBe(1)
    expect(dna.firstRecordedDate).toBe('2026-01-02T12:00:00.000Z')
  })

  it('merges jam pitch-class weights', () => {
    const dna = computePlayerDNA({
      sessions: [],
      jams: [
        {
          date: '2026-01-03T00:00:00.000Z',
          pitch_class_weight_map: { pc_G: 0.6, pc_B: 0.4 },
          position_weight_map: {},
          recurring_gestures: ['bend release'],
        },
      ],
      licks: [],
    })
    expect(dna.pitch_class_bias[7]).toBeGreaterThan(0)
    expect(dna.pitch_class_bias[11]).toBeGreaterThan(0)
    expect(dna.technique_frequency['jam:bend release']).toBe(1)
    expect(dna.eligibleSessionCount).toBe(1)
  })

  it('counts sessions + jams toward eligibility total', () => {
    const dna = computePlayerDNA({
      sessions: [
        { date: '2026-01-01', review_snapshot: null, nodes_targeted: [] },
        { date: '2026-01-02', review_snapshot: null, nodes_targeted: [] },
      ],
      jams: [{ date: '2026-01-03', pitch_class_weight_map: {}, position_weight_map: {}, recurring_gestures: [] }],
      licks: [],
    })
    expect(dna.eligibleSessionCount).toBe(3)
    expect(DNA_MIN_SESSIONS).toBe(3)
  })
})
