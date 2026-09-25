/**
 * chords-db adapter — maps Harmoniq chord format to @tombatossals/chords-db positions
 * and provides fallback-aware lookup.
 */
import guitarDb from '@tombatossals/chords-db/lib/guitar.json'
import { parseChordSymbol } from '@/src/music/chordVoicing'

export interface ChordDbPosition {
  frets: number[]
  fingers: number[]
  baseFret: number
  barres: number[]
  capo: boolean
  midi: number[]
}

interface ChordDbEntry {
  key: string
  suffix: string
  positions: ChordDbPosition[]
}

interface GuitarDb {
  main: { strings: number; fretsOnChord: number }
  tunings: Record<string, string[]>
  keys: string[]
  suffixes: string[]
  chords: Record<string, ChordDbEntry[]>
}

const db = guitarDb as GuitarDb

const SHARP_KEY_MAP: Record<string, string> = {
  'C#': 'Csharp',
  'F#': 'Fsharp',
}

const ENHARMONIC_MAP: Record<string, string> = {
  'C#': 'Db',
  'Db': 'C#',
  'D#': 'Eb',
  'Eb': 'D#',
  'F#': 'Gb',
  'Gb': 'F#',
  'G#': 'Ab',
  'Ab': 'G#',
  'A#': 'Bb',
  'Bb': 'A#',
}

const QUALITY_MAP: Record<string, string> = {
  'maj': 'major',
  'min': 'minor',
  'dim': 'dim',
  'dim7': 'dim7',
  'aug': 'aug',
  'sus2': 'sus2',
  'sus4': 'sus4',
  '7sus4': '7sus4',
  'alt': 'alt',
  'alt7': 'alt',
  '7#5': 'aug7',
  'maj7#5': 'maj7#5',
  'maj7b5': 'maj7b5',
  'maj7sus2': 'maj7sus2',
  'maj7': 'maj7',
  'maj9': 'maj9',
  'maj11': 'maj11',
  'maj13': 'maj13',
  'min7': 'm7',
  'min9': 'm9',
  'min6': 'm6',
  'm7b5': 'm7b5',
  'mmaj7': 'mmaj7',
  'mmaj7b5': 'mmaj7b5',
  'mmaj9': 'mmaj9',
  'mmaj11': 'mmaj11',
  'm69': 'm69',
  'add9': 'add9',
  'madd9': 'madd9',
  'add11': 'add11',
  'sus2sus4': 'sus2sus4',
  '9#11': '9#11',
  '9b5': '9b5',
  'aug9': 'aug9',
  'aug7': 'aug7',
  '7b9': '7b9',
  '7#9': '7#9',
  '7b5': '7b5',
}

/**
 * Map a Harmoniq root note to the chords-db chords object key.
 */
function rootToDbKey(root: string): string {
  return SHARP_KEY_MAP[root] ?? root
}

/**
 * Map a Harmoniq quality string to a chords-db suffix.
 * Tries exact match first, then falls through to QUALITY_MAP.
 * If unknown, returns the quality as-is (it might work).
 */
function qualityToDbSuffix(quality: string): string {
  const mapped = QUALITY_MAP[quality]
  if (mapped) return mapped
  const suffixes = db.suffixes
  if (suffixes.includes(quality)) return quality
  return quality
}

/**
 * Look up chord entries for a given root and suffix in chords-db.
 * Returns null if not found.
 */
function lookupChordEntries(root: string, suffix: string): ChordDbEntry[] | null {
  const dbKey = rootToDbKey(root)
  const entries = db.chords[dbKey]
  if (!entries) return null
  const matching = entries.filter((e) => e.suffix === suffix)
  return matching.length > 0 ? matching : null
}

/**
 * Try finding chord positions, with enharmonic fallback.
 */
function tryQualities(root: string, qualities: string[]): ChordDbPosition[] | null {
  for (const q of qualities) {
    const entries = lookupChordEntries(root, q)
    if (entries) {
      const allPositions = entries.flatMap((e) => e.positions)
      if (allPositions.length > 0) return allPositions
    }
  }
  return null
}

/**
 * Convert a Harmoniq chord symbol (e.g. "C:maj", "F#:min7") to
 * chord positions from the chords-db database.
 *
 * Returns an array of positions, or null if no positions are found
 * (caller should fall back to algorithmic generation).
 */
export function getChordPositions(chordSymbol: string): ChordDbPosition[] | null {
  if (!chordSymbol || chordSymbol === 'N') return null

  const parsed = parseChordSymbol(chordSymbol)
  if (!parsed) return null

  const { root, quality } = parsed
  const dbSuffix = qualityToDbSuffix(quality)

  // Try exact root + suffix
  const positions = tryQualities(root, [dbSuffix])
  if (positions) return positions

  // Try enharmonic root + suffix
  const enhRoot = ENHARMONIC_MAP[root]
  if (enhRoot) {
    const enhPositions = tryQualities(enhRoot, [dbSuffix])
    if (enhPositions) return enhPositions
  }

  // Try the original quality in case it's one of chords-db's native suffixes
  const nativePositions = tryQualities(root, [quality])
  if (nativePositions) return nativePositions

  return null
}

/**
 * Returns the number of available voicings for a chord symbol.
 */
export function getChordPositionCount(chordSymbol: string): number {
  const positions = getChordPositions(chordSymbol)
  return positions ? positions.length : 0
}

/**
 * Returns a single position by index, or null if unavailable.
 */
export function getChordPositionAtIndex(
  chordSymbol: string,
  index: number,
): ChordDbPosition | null {
  const positions = getChordPositions(chordSymbol)
  if (!positions || index < 0 || index >= positions.length) return null
  return positions[index]
}

/**
 * Returns the default (typically lowest fret) position for a beginner-friendly diagram.
 */
export function getDefaultChordPosition(chordSymbol: string): ChordDbPosition | null {
  const positions = getChordPositions(chordSymbol)
  if (!positions || positions.length === 0) return null
  const sorted = [...positions].sort((a, b) => a.baseFret - b.baseFret)
  return sorted[0]!
}

/**
 * Check if a chord symbol has positions in the database.
 */
export function isChordInDb(chordSymbol: string): boolean {
  return getChordPositionCount(chordSymbol) > 0
}
