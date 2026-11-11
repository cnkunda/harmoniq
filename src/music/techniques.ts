/** Technique lookup for fretboard highlight (F5). */

export type TechniqueNote = {
  string?: number | null
  fret?: number | null
  midi?: number | null
  technique?: string[] | null
}

export type TechniqueSelection = { string?: number; fret?: number; midi?: number }

/**
 * Find technique tags for a selected/active note. Prefers an exact
 * string+fret match (the authoritative tab position), then pitch.
 */
export function techniquesForSelection(
  notes: ReadonlyArray<TechniqueNote> | null | undefined,
  selection: TechniqueSelection | null | undefined,
): string[] | null {
  if (!notes?.length || !selection) return null
  const withTechnique = notes.filter((note) => (note.technique?.length ?? 0) > 0)
  if (withTechnique.length === 0) return null

  if (selection.string != null && selection.fret != null) {
    const exact = notes.find(
      (note) => note.string === selection.string && note.fret === selection.fret,
    )
    if (exact) return exact.technique?.length ? exact.technique : null
  }
  if (selection.midi != null) {
    const byPitch = withTechnique.find(
      (note) => note.midi != null && Math.round(note.midi) === Math.round(selection.midi as number),
    )
    if (byPitch?.technique?.length) return byPitch.technique
  }
  return null
}

const TECHNIQUE_LABELS: Record<string, string> = {
  bend: 'Bend',
  vibrato: 'Vibrato',
  grace_note: 'Grace note',
  slide: 'Slide',
  hammer_on: 'Hammer-on',
  pull_off: 'Pull-off',
}

export function techniqueLabel(technique: string): string {
  return TECHNIQUE_LABELS[technique] ?? technique.replace(/_/g, ' ')
}
