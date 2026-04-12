const NOTE_TO_SEMITONE: Record<string, number> = {
  C: 0,
  'C#': 1,
  Db: 1,
  D: 2,
  'D#': 3,
  Eb: 3,
  E: 4,
  F: 5,
  'F#': 6,
  Gb: 6,
  G: 7,
  'G#': 8,
  Ab: 8,
  A: 9,
  'A#': 10,
  Bb: 10,
  B: 11,
}

/** Shared by Study scale-degree and capo copy. */
export function parseKey(input: string | null | undefined): { tonic: string; semitone: number; mode: 'major' | 'minor' } | null {
  const raw = input?.trim()
  if (!raw) return null
  const m = raw.match(/^([A-G](?:#|b)?)(?:\s+)?(major|minor)?/i)
  if (!m) return null
  const tonic = m[1][0].toUpperCase() + m[1].slice(1)
  const modeRaw = (m[2] ?? 'major').toLowerCase()
  const semitone = NOTE_TO_SEMITONE[tonic]
  if (semitone == null) return null
  return {
    tonic,
    semitone,
    mode: modeRaw === 'minor' ? 'minor' : 'major',
  }
}

function parsePositionFret(position: string | null | undefined): number | null {
  if (!position) return null
  const m = position.match(/(\d{1,2})(?:st|nd|rd|th)?\s*fret/i) ?? position.match(/(?:^|@)\s*(\d{1,2})\b/)
  if (!m) return null
  const fret = Number.parseInt(m[1], 10)
  if (!Number.isFinite(fret)) return null
  return Math.max(0, fret)
}

/**
 * Lightweight heuristic for Study UI copy until richer harmony/position analysis exists.
 */
export function capoSuggestion(key: string | null | undefined, position: string | null | undefined): string {
  const parsed = parseKey(key)
  const fret = parsePositionFret(position)
  if (!parsed) return 'Capo suggestion: no strong signal yet — try open position first.'

  const modeText = parsed.mode === 'minor' ? 'minor' : 'major'

  if (fret != null) {
    if (fret <= 2) return `Capo suggestion: no capo (already in a low ${modeText} position).`
    if (fret <= 5) return `Capo suggestion: try capo ${Math.max(1, fret - 2)} for easier voicing from this shape.`
    return `Capo suggestion: try capo ${Math.max(2, fret - 4)} to bring the ${parsed.tonic} ${modeText} shape lower.`
  }

  const defaultByTonic = parsed.mode === 'minor' ? [0, 1, 1, 3, 0, 1, 2, 0, 1, 0, 1, 2] : [0, 1, 2, 1, 0, 1, 2, 0, 1, 2, 1, 0]
  const capo = defaultByTonic[parsed.semitone] ?? 0
  return capo === 0
    ? `Capo suggestion: no capo for ${parsed.tonic} ${modeText} (test both open and E-shape).`
    : `Capo suggestion: try capo ${capo} for ${parsed.tonic} ${modeText}.`
}
