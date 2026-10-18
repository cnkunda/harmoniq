import { describe, expect, it } from 'vitest'

import { buildNoteSelectionDetail } from './noteSelectionDetail'
import type { ChordToneAnalysis, HarmonizedSoloNote } from '@/src/types/soloHarmony'

const TENSION_B3: ChordToneAnalysis = {
  scale_degree: 3,
  scale_degree_name: 'b3',
  chord_tone_type: 'tension',
  semitone_distance: 3,
}

const CHORD_TONE_ROOT: ChordToneAnalysis = {
  scale_degree: 1,
  scale_degree_name: 'R',
  chord_tone_type: 'chord_tone',
  semitone_distance: 0,
}

function harmony(analysis: ChordToneAnalysis | null): { note: HarmonizedSoloNote } {
  return {
    note: {
      start_time: 1,
      duration: 0.5,
      pitch: 67,
      velocity: 90,
      chord: 'G:maj',
      chord_analysis: analysis,
    },
  }
}

const G4 = { string: 1, fret: 3, midi: 67 }
const A4 = { string: 1, fret: 5, midi: 69 }
const ASHARP4 = { string: 1, fret: 6, midi: 70 }

describe('buildNoteSelectionDetail with harmonized data', () => {
  it('takes chord-tone status and degree from the backend analysis', () => {
    const detail = buildNoteSelectionDetail('G major', G4, 'G:maj', 0.9, harmony(TENSION_B3))
    expect(detail).not.toBeNull()
    expect(detail!.chordToneStatus).toBe('tension')
    expect(detail!.harmonicDegree).toBe('b3')
  })

  it('reports chord tones with their degree name', () => {
    const detail = buildNoteSelectionDetail('G major', G4, 'G:maj', null, harmony(CHORD_TONE_ROOT))
    expect(detail!.chordToneStatus).toBe('chord_tone')
    expect(detail!.harmonicDegree).toBe('R')
  })

  it("passes the backend's 'pedal' role through", () => {
    const pedal: ChordToneAnalysis = { ...CHORD_TONE_ROOT, chord_tone_type: 'pedal' }
    const detail = buildNoteSelectionDetail('G major', G4, null, null, harmony(pedal))
    expect(detail!.chordToneStatus).toBe('pedal')
    expect(detail!.harmonicDegree).toBe('R')
  })

  it('falls back to client-side classification when the note has no analysis', () => {
    const detail = buildNoteSelectionDetail('G major', G4, 'G:maj', null, harmony(null))
    expect(detail!.chordToneStatus).toBe('chord_tone')
    expect(detail!.harmonicDegree).toBeNull()
  })
})

describe('buildNoteSelectionDetail without harmonized data', () => {
  it('classifies a chord member as a chord tone', () => {
    const detail = buildNoteSelectionDetail('G major', G4, 'G:maj', null)
    expect(detail!.chordToneStatus).toBe('chord_tone')
    expect(detail!.harmonicDegree).toBeNull()
  })

  it('classifies a scale member as a tension', () => {
    const detail = buildNoteSelectionDetail('G major', A4, 'G:maj', null)
    expect(detail!.chordToneStatus).toBe('tension')
  })

  it('classifies an outside note as chromatic', () => {
    const detail = buildNoteSelectionDetail('G major', ASHARP4, 'G:maj', null)
    expect(detail!.chordToneStatus).toBe('chromatic')
  })

  it('omits the status for no-chord and missing chords', () => {
    expect(buildNoteSelectionDetail('G major', G4, 'N', null)!.chordToneStatus).toBeNull()
    expect(buildNoteSelectionDetail('G major', G4, null, null)!.chordToneStatus).toBeNull()
    expect(buildNoteSelectionDetail('G major', G4, null, null, null)!.chordToneStatus).toBeNull()
  })

  it('returns null without a selection', () => {
    expect(buildNoteSelectionDetail('G major', null, 'G:maj', null)).toBeNull()
  })
})
