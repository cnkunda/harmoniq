/**
 * Chord voicing mapper - Convert chord symbols to guitar fretboard positions
 * Supports full voicings (authentic guitar shapes) and compact voicings (triads)
 */

import { allCellsForMidi, OPEN_MIDI_BY_ROW } from './fretboardCell'

/** Interval semitones from root for common chord qualities */
const CHORD_QUALITY_INTERVALS: Record<string, number[]> = {
  maj: [0, 4, 7], // Root, major 3rd, perfect 5th
  min: [0, 3, 7], // Root, minor 3rd, perfect 5th
  dim: [0, 3, 6], // Root, minor 3rd, diminished 5th
  aug: [0, 4, 8], // Root, major 3rd, augmented 5th
  '7': [0, 4, 7, 10], // Dominant 7th
  maj7: [0, 4, 7, 11], // Major 7th
  min7: [0, 3, 7, 10], // Minor 7th
  '7sus4': [0, 5, 7, 10], // Dominant 7th suspended 4th
  sus4: [0, 5, 7], // Suspended 4th
  sus2: [0, 2, 7], // Suspended 2nd
  '6': [0, 4, 7, 9], // Major 6th
  min6: [0, 3, 7, 9], // Minor 6th
  '9': [0, 4, 7, 10, 14], // Dominant 9th (rootless voicings often used)
  maj9: [0, 4, 7, 11, 14], // Major 9th
  min9: [0, 3, 7, 10, 14], // Minor 9th
}

/** Common guitar chord voicing templates (string set + fret pattern) */
const FULL_VOICING_TEMPLATES: Array<{
  name: string
  strings: number[] // 1-6 (1 = high E)
  pattern: number[] // Frets relative to root position, -1 = muted
  bassString: number
  intervalMap: number[] // Musical intervals for each string in the pattern
}> = [
  // E-shape barre (root on string 6) - major: R, 5, R, M3, 5, R
  { name: 'E-shape', strings: [1, 2, 3, 4, 5, 6], pattern: [0, 0, 1, 2, 2, 0], bassString: 6, intervalMap: [4, 7, 0, 4, 7, 0] },
  // A-shape barre (root on string 5) - major: R, 5, R, M3, 5
  { name: 'A-shape', strings: [1, 2, 3, 4, 5], pattern: [0, 0, 0, 2, 0], bassString: 5, intervalMap: [4, 7, 0, 4, 7] },
  // C-shape (root on string 5) - major: 5, R, M3, 5, R
  { name: 'C-shape', strings: [1, 2, 3, 4, 5], pattern: [0, 1, 0, 2, 3], bassString: 5, intervalMap: [7, 0, 4, 7, 0] },
  // D-shape (root on string 4, higher voicing) - major: M3, R, 5, R
  { name: 'D-shape', strings: [1, 2, 3, 4], pattern: [2, 3, 2, 0], bassString: 4, intervalMap: [4, 0, 7, 0] },
  // G-shape (root on string 6) - major: M3, R, 5, R, 5, R
  { name: 'G-shape', strings: [1, 2, 3, 4, 5, 6], pattern: [3, 3, 0, 0, 2, 3], bassString: 6, intervalMap: [4, 0, 7, 0, 7, 0] },
]

/** Templates for minor chords (m3 instead of M3) */
const MINOR_VOICING_TEMPLATES: Array<{
  name: string
  strings: number[]
  pattern: number[]
  bassString: number
  intervalMap: number[]
}> = [
  // E-minor shape (root on string 6) - minor: R, 5, R, m3, 5, R
  { name: 'Em-shape', strings: [1, 2, 3, 4, 5, 6], pattern: [0, 0, 0, 2, 2, 0], bassString: 6, intervalMap: [7, 3, 0, 3, 7, 0] },
  // A-minor shape (root on string 5) - minor: R, 5, R, m3, 5
  { name: 'Am-shape', strings: [1, 2, 3, 4, 5], pattern: [0, 0, 0, 2, 0], bassString: 5, intervalMap: [4, 7, 0, 3, 7] },
]

/** Templates for minor 7th chords (R, m3, 5, m7) */
const MINOR7_VOICING_TEMPLATES: Array<{
  name: string
  strings: number[]
  pattern: number[]
  bassString: number
  intervalMap: number[]
}> = [
  // Dm7 shape (root on string 4) - m7: R, 5, m7, m3, 5 (no root on string 1)
  { name: 'Dm7-shape', strings: [2, 3, 4, 5], pattern: [1, 2, 0, 1], bassString: 4, intervalMap: [10, 3, 0, 7] },
  // Em7 shape (root on string 6) - m7: R, m7, m3, 5, R, 5
  { name: 'Em7-shape', strings: [1, 2, 3, 4, 5, 6], pattern: [0, 0, 0, 0, 2, 0], bassString: 6, intervalMap: [10, 3, 7, 3, 7, 0] },
  // Am7 shape (root on string 5) - m7: R, 5, m7, m3, 5
  { name: 'Am7-shape', strings: [1, 2, 3, 4, 5], pattern: [0, 0, 0, 2, 0], bassString: 5, intervalMap: [4, 10, 0, 3, 7] },
]

export type VoicingMode = 'full' | 'compact'
export type PositionPreference = 'open' | 'low' | 'mid'

export interface FretboardCell {
  string: number // 1-6 (1 = high E)
  fret: number
  midi: number
  interval: number // Semitones from root (0 = root, 4 = M3, etc.)
}

/**
 * Parse a chord symbol into root note and quality
 * Handles formats like "C:maj", "F#:min7", "Bb:7", "N" (no chord)
 */
function parseChordSymbol(chordSymbol: string): { root: string; quality: string } | null {
  if (!chordSymbol || chordSymbol === 'N') return null

  // Extract root (1-2 chars: letter + optional # or b)
  const rootMatch = chordSymbol.match(/^([A-G][#b]?)/)
  if (!rootMatch) return null
  const root = rootMatch[1]

  // Get the rest of the string after the root
  const afterRoot = chordSymbol.slice(rootMatch[0].length)

  // Extract quality (everything after optional colon, or the remainder if no colon)
  let quality = 'maj' // default

  if (afterRoot.startsWith(':')) {
    // Format: C:maj, C:min7, etc.
    quality = afterRoot.slice(1).trim()
  } else if (afterRoot.length > 0) {
    // Format: Cmaj, Cm, C7, etc. (no colon)
    quality = afterRoot.trim()
  }

  // Normalize quality names - be careful with order of checks
  const q = quality.toLowerCase()

  // Check for specific patterns first (longer matches before shorter)
  if (q.includes('maj9')) quality = 'maj9'
  else if (q.includes('min9') || q === 'm9') quality = 'min9'
  else if (q.includes('9')) quality = '9'
  else if (q.includes('maj7') || q === 'M7') quality = 'maj7'
  else if (q.includes('min7') || q === 'm7') quality = 'min7'
  else if (q.includes('7sus4')) quality = '7sus4'
  else if (q.includes('sus4')) quality = 'sus4'
  else if (q.includes('sus2')) quality = 'sus2'
  else if (q.includes('min6') || q === 'm6') quality = 'min6'
  else if (q.includes('6')) quality = '6'
  else if (q === 'dim' || q === '°' || q === 'o') quality = 'dim'
  else if (q === 'aug' || q === '+') quality = 'aug'
  else if (q === 'min' || q === 'm' || q === 'minor') quality = 'min'
  else if (q === 'maj' || q === 'M' || q === 'major' || q === '') quality = 'maj'
  else if (q === '7') quality = '7'

  return { root, quality }
}

/**
 * Convert note name to MIDI pitch class (0-11)
 */
function noteToPitchClass(note: string): number {
  const NOTE_MAP: Record<string, number> = {
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
  return NOTE_MAP[note] ?? 0
}

/**
 * Build a compact voicing (3-4 notes, close position, easy to read)
 */
function buildCompactVoicing(
  rootMidi: number,
  intervals: number[],
  position: PositionPreference
): FretboardCell[] {
  // Use first 3-4 intervals (root position triad/quadad)
  const usedIntervals = intervals.slice(0, 4)

  // Find lowest fret position that can play all notes
  const cells: FretboardCell[] = []

  for (const interval of usedIntervals) {
    const targetMidi = rootMidi + interval
    const possibleCells = allCellsForMidi(targetMidi)

    if (possibleCells.length === 0) continue

    // Pick cell based on position preference
    let selectedCell = possibleCells[0]
    if (position === 'open') {
      // Prefer open strings (fret 0)
      selectedCell = possibleCells.find((c) => c.fret === 0) ?? possibleCells[0]
    } else if (position === 'low') {
      // Already sorted by lowest fret
      selectedCell = possibleCells[0]
    } else if (position === 'mid') {
      // Prefer position around fret 5
      selectedCell =
        possibleCells.find((c) => c.fret >= 3 && c.fret <= 7) ??
        possibleCells[Math.floor(possibleCells.length / 2)]
    }

    cells.push({
      string: selectedCell.row + 1, // Convert 0-indexed row to 1-indexed string
      fret: selectedCell.fret,
      midi: targetMidi,
      interval,
    })
  }

  // Ensure we have at least root + 2 more notes
  if (cells.length < 3) {
    // Fall back: add root on different string if needed
    const rootCells = allCellsForMidi(rootMidi)
    if (rootCells.length > 1 && !cells.some((c) => c.interval === 0 && c.string !== cells[0]?.string)) {
      const extraRoot = rootCells.find((c) => c.row + 1 !== cells[0]?.string)
      if (extraRoot) {
        cells.push({
          string: extraRoot.row + 1,
          fret: extraRoot.fret,
          midi: rootMidi,
          interval: 0,
        })
      }
    }
  }

  return cells
}

/**
 * Build a full voicing (authentic guitar chord shape with proper voice leading)
 */
function buildFullVoicing(
  rootMidi: number,
  intervals: number[],
  position: PositionPreference
): FretboardCell[] {
  const rootPc = rootMidi % 12

  // Determine base fret from root and desired position
  let baseFret = 0
  if (position === 'low') {
    // Find lowest position where root can be played on E or A string
    const eStringRoot = rootPc >= 4 ? rootPc - 4 : rootPc + 8 // E string = MIDI 40, 52, 64...
    const aStringRoot = rootPc >= 9 ? rootPc - 9 : rootPc + 3 // A string = MIDI 45, 57, 69...
    baseFret = Math.min(eStringRoot, aStringRoot)
  } else if (position === 'mid') {
    baseFret = 5
  } else if (position === 'open') {
    baseFret = 0
  }

  // Select template based on chord quality
  const isMinor = intervals.includes(3) && !intervals.includes(4)
  const isMinor7 = isMinor && intervals.includes(10)
  const isDominant7 = intervals.includes(4) && intervals.includes(10)

  let templates = FULL_VOICING_TEMPLATES
  if (isMinor7) {
    templates = MINOR7_VOICING_TEMPLATES
  } else if (isMinor) {
    templates = MINOR_VOICING_TEMPLATES
  }
  // For dominant 7 and major 7, we need extended templates - for now use full with fallback

  const template = templates[0] // Use first template

  // Build voicing from template using the intervalMap
  const cells: FretboardCell[] = []

  for (let i = 0; i < template.strings.length; i++) {
    const stringNum = template.strings[i]
    const fretOffset = template.pattern[i]
    if (fretOffset < 0) continue // Muted string

    const fret = baseFret + fretOffset
    const stringRow = 6 - stringNum // Convert to 0-indexed row (0 = high E)
    const midi = OPEN_MIDI_BY_ROW[stringRow] + fret

    // Use the interval from the template's intervalMap
    const interval = template.intervalMap[i]

    // Only include if this interval is in our target chord
    if (!intervals.includes(interval)) {
      continue
    }

    cells.push({
      string: stringNum,
      fret,
      midi,
      interval,
    })
  }

  // If we have too few chord tones, fall back to compact voicing
  if (cells.length < 3) {
    return buildCompactVoicing(rootMidi, intervals, position)
  }

  return cells
}

/**
 * Convert a chord symbol to fretboard positions
 *
 * @param chordSymbol - Chord symbol like "C:maj", "F#:min7", "N"
 * @param mode - 'full' for authentic guitar voicings, 'compact' for simplified triads
 * @param position - 'open', 'low', or 'mid' fretboard position preference
 * @returns Array of fretboard cells, or empty array if chord is "N" or unparseable
 */
export function chordToFretboardCells(
  chordSymbol: string,
  mode: VoicingMode = 'compact',
  position: PositionPreference = 'low'
): FretboardCell[] {
  const parsed = parseChordSymbol(chordSymbol)
  if (!parsed) return []

  const { root, quality } = parsed
  const rootPc = noteToPitchClass(root)

  // Determine octave - use octave 3 (MIDI 48-59) as base for E-string chords
  // This puts chords in playable range
  const baseOctave = 3
  const rootMidi = rootPc + (baseOctave + 1) * 12 // MIDI 60 = C4 as reference

  // Get intervals for this quality
  const intervals = CHORD_QUALITY_INTERVALS[quality] ?? CHORD_QUALITY_INTERVALS.maj

  // Build voicing based on mode
  if (mode === 'compact') {
    return buildCompactVoicing(rootMidi, intervals, position)
  } else {
    return buildFullVoicing(rootMidi, intervals, position)
  }
}

/**
 * Get a display name for a chord quality
 */
export function getChordQualityDisplay(quality: string): string {
  const DISPLAY_NAMES: Record<string, string> = {
    maj: '',
    min: 'm',
    dim: '°',
    aug: '+',
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
  }
  return DISPLAY_NAMES[quality] ?? quality
}

/**
 * Format chord symbol for display (compact notation)
 * "C:maj" → "C", "F#:min7" → "F#m7", "Bb:maj7" → "Bbmaj7"
 */
export function formatChordDisplay(chordSymbol: string): string {
  const parsed = parseChordSymbol(chordSymbol)
  if (!parsed) return chordSymbol === 'N' ? '—' : chordSymbol

  const { root, quality } = parsed
  const qualityDisplay = getChordQualityDisplay(quality)
  return `${root}${qualityDisplay}`
}
