/**
 * MIREX 25-class chord vocabulary — mirrors backend/app/chord_vocab.py.
 *
 * 12 major + 12 minor + 1 No-Chord = 25 classes.
 */

const ROOT_NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const

/** Full MIREX 25-class vocabulary in order. */
export const MIREX_VOCAB: readonly string[] = [
  ...ROOT_NOTES.map((r) => `${r}:maj`),
  ...ROOT_NOTES.map((r) => `${r}:min`),
  'N',
] as const

/** Number of classes (25). */
export const NUM_CLASSES_MIREX = 25

/** Chord label → class index lookup. */
export const MIREX_TO_IDX: Record<string, number> = Object.fromEntries(
  MIREX_VOCAB.map((label, i) => [label, i]),
)

/** Class index → chord label lookup. */
export const IDX_TO_CHORD: readonly string[] = MIREX_VOCAB

/** Map a predicted class index to its chord label. */
export function idxToChord(idx: number): string {
  if (idx < 0 || idx >= NUM_CLASSES_MIREX) return 'N'
  return IDX_TO_CHORD[idx] ?? 'N'
}

/** Strip quality suffix and return just the root note (e.g. "C:maj" → "C"). */
export function chordRoot(chord: string): string {
  const colon = chord.indexOf(':')
  return colon > 0 ? chord.slice(0, colon) : chord
}

/** Return the quality portion of a chord label (e.g. "C:maj" → "maj"). */
export function chordQuality(chord: string): string {
  const colon = chord.indexOf(':')
  return colon > 0 ? chord.slice(colon + 1) : ''
}

/** Whether a chord label represents "no chord". */
export function isNoChord(chord: string): boolean {
  return chord === 'N' || chord === 'N:N'
}
