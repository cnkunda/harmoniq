import { parseKey } from '@/src/music/capoSuggestion'

/**
 * Roman numeral analysis labels for chord functions in major keys
 */
const MAJOR_FUNCTION_LABELS: Record<string, string> = {
  'I': 'Tonic — Home base',
  'ii': 'Supertonic — Pre-dominant',
  'iii': 'Mediant — Departure',
  'IV': 'Subdominant — Departure',
  'V': 'Dominant — Tension',
  'vi': 'Submediant — Return',
  'vii°': 'Leading tone — Tension',
}

/**
 * Roman numeral analysis labels for chord functions in minor keys
 */
const MINOR_FUNCTION_LABELS: Record<string, string> = {
  'i': 'Tonic — Home base',
  'ii°': 'Supertonic — Tension',
  'III': 'Mediant — Departure',
  'iv': 'Subdominant — Departure',
  'v': 'Dominant — Tension',
  'VI': 'Submediant — Return',
  'VII': 'Leading tone — Tension',
}

/**
 * Parse a chord symbol (e.g., "C:maj", "D:min", "N") to extract root note
 */
function parseChordRoot(chordSymbol: string): string | null {
  if (!chordSymbol || chordSymbol === 'N') return null
  // Extract root note (letter before colon or first 1-2 characters)
  const match = chordSymbol.match(/^([A-G][#b]?)/)
  return match ? match[1] : null
}

/**
 * Calculate the interval from the key root to the chord root in semitones
 */
function intervalFromKeyRoot(keyRootSemitone: number, chordRoot: string): number {
  const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
  const chordIndex = NOTE_NAMES.findIndex(n => n === chordRoot)
  if (chordIndex === -1) return -1
  return (chordIndex - keyRootSemitone + 12) % 12
}

/**
 * Get chord function label (Roman numeral + plain English description)
 * 
 * @param keyLabel - Musical key (e.g., "C major", "A minor")
 * @param chordSymbol - Chord symbol from chord timeline (e.g., "C:maj", "D:min", "N")
 * @returns Object with roman numeral and plain English label, or null if unable to determine
 */
export function getChordFunction(keyLabel: string, chordSymbol: string): {
  roman: string
  label: string
} | null {
  if (!chordSymbol || chordSymbol === 'N') {
    return null
  }

  const parsedKey = parseKey(keyLabel)
  if (!parsedKey) {
    return null
  }

  const chordRoot = parseChordRoot(chordSymbol)
  if (!chordRoot) {
    return null
  }

  const interval = intervalFromKeyRoot(parsedKey.semitone, chordRoot)
  if (interval === -1) {
    return null
  }

  // Map interval to Roman numeral based on key mode
  const isMajor = parsedKey.mode === 'major'
  const functionLabels = isMajor ? MAJOR_FUNCTION_LABELS : MINOR_FUNCTION_LABELS

  // Major key intervals: I=0, ii=2, iii=4, IV=5, V=7, vi=9, vii°=11
  // Minor key intervals: i=0, ii°=2, III=3, iv=5, v=7, VI=8, VII=10
  let roman: string
  if (isMajor) {
    const intervalToRoman: Record<number, string> = {
      0: 'I',
      2: 'ii',
      4: 'iii',
      5: 'IV',
      7: 'V',
      9: 'vi',
      11: 'vii°',
    }
    roman = intervalToRoman[interval] || '?'
  } else {
    const intervalToRoman: Record<number, string> = {
      0: 'i',
      2: 'ii°',
      3: 'III',
      5: 'iv',
      7: 'v',
      8: 'VI',
      10: 'VII',
    }
    roman = intervalToRoman[interval] || '?'
  }

  const label = functionLabels[roman] || 'Extended harmony'

  return { roman, label }
}
