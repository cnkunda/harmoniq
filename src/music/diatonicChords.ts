import { CHROMATIC_NOTE_NAMES } from '@/src/music/noteNames'
import { parseChordSymbol, noteToPitchClass } from '@/src/music/chordVoicing'

// ---- Diatonic chord definitions (ported from backend chord_transitions.py) ----

interface DiatonicEntry {
  semitone: number
  quality: string
  roman: string
}

const MAJOR_DIATONIC: DiatonicEntry[] = [
  { semitone: 0, quality: 'maj', roman: 'I' },
  { semitone: 2, quality: 'min', roman: 'ii' },
  { semitone: 4, quality: 'min', roman: 'iii' },
  { semitone: 5, quality: 'maj', roman: 'IV' },
  { semitone: 7, quality: 'maj', roman: 'V' },
  { semitone: 7, quality: '7', roman: 'V7' },
  { semitone: 9, quality: 'min', roman: 'vi' },
  { semitone: 11, quality: 'dim', roman: 'vii°' },
]

const MINOR_DIATONIC: DiatonicEntry[] = [
  { semitone: 0, quality: 'min', roman: 'i' },
  { semitone: 2, quality: 'dim', roman: 'ii°' },
  { semitone: 3, quality: 'maj', roman: 'III' },
  { semitone: 5, quality: 'min', roman: 'iv' },
  { semitone: 7, quality: 'min', roman: 'v' },
  { semitone: 7, quality: '7', roman: 'v7' },
  { semitone: 8, quality: 'maj', roman: 'VI' },
  { semitone: 10, quality: 'maj', roman: 'VII' },
]

// ---- Quality display helpers ----

const QUALITY_TO_SUFFIX: Record<string, string> = {
  maj: '',
  min: 'm',
  dim: 'dim',
  aug: 'aug',
  '7': '7',
  maj7: 'maj7',
  min7: 'm7',
  '7sus4': '7sus4',
  sus4: 'sus4',
  sus2: 'sus2',
  '6': '6',
  min6: 'm6',
  '9': '9',
  maj9: 'maj9',
  min9: 'm9',
  dim7: 'dim7',
}

function chordSymbolFromRootQuality(root: string, quality: string): string {
  return `${root}:${quality}`
}

function chordDisplayFromRootQuality(root: string, quality: string): string {
  return `${root}${QUALITY_TO_SUFFIX[quality] ?? quality}`
}

// ---- Main API ----

export interface DiatonicChord {
  symbol: string     // e.g., "C:maj"
  display: string    // e.g., "C"
  roman: string      // e.g., "I"
  semitone: number   // semitone from key root
  quality: string    // e.g., "maj"
}

/**
 * Parse a key string like "C major" or "A minor" into root + mode.
 */
export function parseKey(key: string): { root: string; mode: 'major' | 'minor' } | null {
  const match = key.match(/^([A-G][#b]?)\s+(major|minor|maj|min)$/i)
  if (!match) return null
  const root = match[1]
  const mode = match[2].toLowerCase().startsWith('min') ? 'minor' : 'major'
  return { root, mode }
}

/**
 * Get diatonic chords for a given key, organized by Roman numeral.
 * Returns the "core" diatonic set (triads + V7).
 */
export function getDiatonicChords(key: string): DiatonicChord[] {
  const parsed = parseKey(key)
  if (!parsed) return []

  const rootPc = noteToPitchClass(parsed.root)
  if (rootPc === undefined) return []

  const table = parsed.mode === 'major' ? MAJOR_DIATONIC : MINOR_DIATONIC
  const seen = new Set<string>()
  const result: DiatonicChord[] = []

  for (const entry of table) {
    const pc = (rootPc + entry.semitone) % 12
    const root = CHROMATIC_NOTE_NAMES[pc]
    const dedupKey = `${root}:${entry.quality}`
    if (seen.has(dedupKey)) continue
    seen.add(dedupKey)

    result.push({
      symbol: chordSymbolFromRootQuality(root, entry.quality),
      display: chordDisplayFromRootQuality(root, entry.quality),
      roman: entry.roman,
      semitone: entry.semitone,
      quality: entry.quality,
    })
  }

  return result
}

/**
 * Get all chromatic chords (all 12 roots × common qualities) as a flat list.
 * Used as fallback when diatonic chords are not enough.
 */
export function getChromaticChords(): Array<{ symbol: string; display: string }> {
  const qualities = ['maj', 'min', '7', 'maj7', 'min7', 'dim', 'aug', 'sus4']
  const result: Array<{ symbol: string; display: string }> = []
  for (const root of CHROMATIC_NOTE_NAMES) {
    for (const q of qualities) {
      result.push({
        symbol: chordSymbolFromRootQuality(root, q),
        display: chordDisplayFromRootQuality(root, q),
      })
    }
  }
  return result
}

/**
 * Check if a chord symbol is valid (parseable by parseChordSymbol).
 */
export function isValidChord(symbol: string): boolean {
  if (!symbol || symbol === 'N') return false
  return parseChordSymbol(symbol) !== null
}
