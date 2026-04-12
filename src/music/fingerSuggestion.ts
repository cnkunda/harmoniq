export type FingerSuggestionInput = {
  /** Fret number; 0 = open / nut. */
  fret: number
  /** Diagram row 0–5 (high E = 0). Optional; only affects copy nuance. */
  stringIndex?: number
}

export type FingerSuggestions = {
  primary: string
  /** Other same-pitch positions (heuristic: within 6 frets of primary); deduped lines. */
  alternates: string[]
}

/**
 * Primary line plus alternate fingerings for the same MIDI on other strings/frets.
 * `samePitchCells` should include every valid (row, fret) for the pitch (see `allCellsForMidi`).
 * Full hand-position model can replace internals later without changing Study call sites.
 */
export function suggestFingerings(
  primaryCell: { row: number; fret: number },
  samePitchCells: Array<{ row: number; fret: number }>,
): FingerSuggestions {
  const primary = fingerSuggestion({ fret: primaryCell.fret, stringIndex: primaryCell.row })
  const seen = new Set<string>([primary])
  const alternates: string[] = []
  for (const c of samePitchCells) {
    if (c.row === primaryCell.row && c.fret === primaryCell.fret) continue
    if (Math.abs(c.fret - primaryCell.fret) > 6) continue
    const line = fingerSuggestion({ fret: c.fret, stringIndex: c.row })
    if (seen.has(line)) continue
    seen.add(line)
    alternates.push(line)
    if (alternates.length >= 3) break
  }
  return { primary, alternates }
}

/**
 * Single-note fingering hint for pedagogy UI. Does not model hand frame or shifts across strings.
 * TODO: position-aware fingering using surrounding tab beats and capo.
 */
export function fingerSuggestion(input: FingerSuggestionInput): string {
  const fret = Math.round(input.fret)
  if (!Number.isFinite(fret)) return 'Fret the note cleanly; check tab string and fret.'
  if (fret < 0) return 'Invalid fret — re-check the score.'

  if (fret === 0) return 'Open string (no left-hand finger).'

  if (fret >= 1 && fret <= 4) {
    const byFret = ['Index finger (1)', 'Middle finger (2)', 'Ring finger (3)', 'Pinky (4)'] as const
    return byFret[fret - 1]!
  }

  if (fret <= 7) return 'Use a compact frame: anchor with the index and stretch or shift as needed.'

  if (fret <= 12) return 'Mid-neck: shift the whole hand; avoid twisting the wrist.'

  return 'High fret: slide into position or compress the hand; pinky or shifted index often works.'
}
