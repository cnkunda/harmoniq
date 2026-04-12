import { describe, expect, it } from 'vitest'

import { allCellsForMidi, inferMidiFromNoteSelection, resolveFretCell } from './fretboardCell'

describe('resolveFretCell — high fret with tab string', () => {
  it('preserves fret 15 on string 1 (high E); does not clamp to 12', () => {
    const cell = resolveFretCell({ string: 1, fret: 15 })
    expect(cell).toEqual({ row: 0, fret: 15 })
  })

  it('infers correct MIDI from string 1 + fret 15', () => {
    const midi = inferMidiFromNoteSelection({ string: 1, fret: 15 })
    expect(midi).toBe(79)
  })
})

describe('MIDI-only disambiguation', () => {
  it('picks lowest fret; tie-break thinner string (row 0 first)', () => {
    /** G4 MIDI 67: high E @3, B @8, G @12, … — minimum fret is 3 on string 1. */
    const cell = resolveFretCell({ midi: 67 })
    expect(cell).toEqual({ row: 0, fret: 3 })
    const all = allCellsForMidi(67)
    expect(all[0]).toEqual({ row: 0, fret: 3 })
    expect(all.length).toBeGreaterThan(1)
  })

  it('fixture: two valid positions same pitch — ordering is deterministic', () => {
    const cells = allCellsForMidi(67)
    const byFret = [...cells].sort((a, b) => a.fret - b.fret || a.row - b.row)
    expect(cells).toEqual(byFret)
    expect(cells[0]!.fret).toBeLessThan(cells[1]!.fret)
  })
})

describe('inferMidiFromNoteSelection — tab over engine MIDI', () => {
  it('uses notated string+fret when engine MIDI disagrees (e.g. transposition)', () => {
    /** String 1 fret 0 = E4 = 64; wrong MIDI 65 should not win. */
    const midi = inferMidiFromNoteSelection({ string: 1, fret: 0, midi: 65 })
    expect(midi).toBe(64)
  })
})
