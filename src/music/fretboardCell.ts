/** High E (top of diagram) → low E. Matches typical 1-based tab numbering (1 = high E). */
export const OPEN_MIDI_BY_ROW = [64, 59, 55, 50, 45, 40] as const

/** Display shows nut + 12 frets; MIDI resolution searches further for high notes. */
export const NUM_FRETS = 12
export const MIDI_SEARCH_MAX_FRET = 24

function normalizeStringIndex(tabString: number | undefined): number | null {
  if (tabString == null || !Number.isFinite(tabString)) return null
  const s = Math.round(tabString)
  if (s >= 1 && s <= 6) return s - 1
  if (s >= 0 && s <= 5) return s
  return null
}

/**
 * MIDI-only disambiguation (standard tuning, six strings):
 * 1. Collect every (string row, fret) where openMidi[row] + fret === target MIDI.
 * 2. Prefer the smallest fret (lower positions / open-friendly).
 * 3. Tie-break: smallest row index (string 1 = high E first).
 *
 * Replaces the old `fret * 8 + row` cost, which was undocumented and could diverge from (2)+(3).
 */
export function allCellsForMidi(midi: number): Array<{ row: number; fret: number }> {
  const target = Math.round(midi)
  const out: Array<{ row: number; fret: number }> = []
  for (let row = 0; row < 6; row += 1) {
    for (let fret = 0; fret <= MIDI_SEARCH_MAX_FRET; fret += 1) {
      if (OPEN_MIDI_BY_ROW[row]! + fret === target) {
        out.push({ row, fret })
      }
    }
  }
  out.sort((a, b) => a.fret - b.fret || a.row - b.row)
  return out
}

function pickMidiOnlyCell(midi: number): { row: number; fret: number } | null {
  const sorted = allCellsForMidi(midi)
  return sorted[0] ?? null
}

export function resolveFretCell(note: {
  string?: number
  fret?: number
  midi?: number
}): { row: number; fret: number } | null {
  const rowFromTab = normalizeStringIndex(note.string)
  if (note.fret != null && Number.isFinite(note.fret)) {
    /** Keep true fret for finger copy; diagram clamps display to column 12 when > NUM_FRETS. */
    const fret = Math.max(0, Math.min(MIDI_SEARCH_MAX_FRET, Math.round(note.fret)))
    if (rowFromTab != null) return { row: rowFromTab, fret }
  }
  if (note.midi != null && Number.isFinite(note.midi)) {
    return pickMidiOnlyCell(Math.round(note.midi))
  }
  if (rowFromTab != null && note.fret == null) return null
  return null
}

/**
 * Pitch for Study coach / scale degree: when the engine sends string+fret, derive MIDI from the
 * notated tab first so transposition or engine MIDI quirks do not override the written position.
 */
export function inferMidiFromNoteSelection(note: {
  string?: number
  fret?: number
  midi?: number
}): number | null {
  const rowFromTab = normalizeStringIndex(note.string)
  if (rowFromTab != null && note.fret != null && Number.isFinite(note.fret)) {
    const fret = Math.max(0, Math.min(MIDI_SEARCH_MAX_FRET, Math.round(note.fret)))
    return OPEN_MIDI_BY_ROW[rowFromTab]! + fret
  }
  if (note.midi != null && Number.isFinite(note.midi)) return Math.round(note.midi)
  const cell = resolveFretCell(note)
  if (!cell) return null
  return OPEN_MIDI_BY_ROW[cell.row]! + cell.fret
}
