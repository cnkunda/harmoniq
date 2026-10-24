/** Commit 166: coarse chord-shape difficulty for the Learner tier's color coding. */
export type ChordDifficulty = 'easy' | 'medium' | 'hard'

const EASY_SUFFIXES = new Set(['', 'm', 'min', 'maj', 'major', 'minor', '5'])

const MEDIUM_SUFFIXES = new Set([
  '7',
  'm7',
  'min7',
  'maj7',
  'major7',
  '6',
  'm6',
  'min6',
  'sus2',
  'sus4',
  'sus',
  'dim',
  'dim7',
  'aug',
  'o',
  '+',
  'add9',
])

const HARD_MARKERS = ['9', '11', '13', 'alt', 'b5', '#5', 'b9', '#9', '#11', 'b13', 'omit', 'add']

/**
 * Classify a chord symbol for learner-facing color coding.
 * Slash chords and altered/extended voicings are treated as harder shapes.
 */
export function chordDifficulty(chord: string): ChordDifficulty {
  const raw = chord.trim()
  if (!raw) return 'medium'

  const match = raw.match(/^([A-Ga-g][#b]?)(.*)$/)
  if (!match) return 'medium'
  const suffix = match[2].toLowerCase()

  if (raw.includes('/')) return 'hard'
  if (HARD_MARKERS.some((marker) => suffix.includes(marker))) return 'hard'
  if (EASY_SUFFIXES.has(suffix)) return 'easy'
  if (MEDIUM_SUFFIXES.has(suffix)) return 'medium'
  return 'medium'
}
