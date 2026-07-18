import { parseKey } from '@/src/music/capoSuggestion'
import { parseChordSymbol, noteToPitchClass } from '@/src/music/chordVoicing'
import { allCellsForMidi, inferMidiFromNoteSelection, resolveFretCell } from '@/src/music/fretboardCell'
import { suggestFingerings } from '@/src/music/fingerSuggestion'
import { buildStudyCoachLine, midiToNoteName, scaleDegreeLabel } from '@/src/music/scaleDegree'

export type SelectedFretNote = { string?: number; fret?: number; midi?: number }

export type ChordToneStatus = 'chord_tone' | 'tension' | 'chromatic'

export type NoteSelectionDetail = {
  noteName: string
  degree: string
  fingerLine: string
  alternateFingerLines: string[]
  coach: string
  chordToneStatus: ChordToneStatus | null
  confidence: number | null
}

const INTERVAL_PITCHES: Record<string, number[]> = {
  maj: [0, 4, 7],
  min: [0, 3, 7],
  dim: [0, 3, 6],
  aug: [0, 4, 8],
  '7': [0, 4, 7, 10],
  maj7: [0, 4, 7, 11],
  min7: [0, 3, 7, 10],
  '7sus4': [0, 5, 7, 10],
  sus4: [0, 5, 7],
  sus2: [0, 2, 7],
  '6': [0, 4, 7, 9],
  min6: [0, 3, 7, 9],
  '9': [0, 4, 7, 10, 14],
  maj9: [0, 4, 7, 11, 14],
  min9: [0, 3, 7, 10, 14],
  '7b9': [0, 4, 7, 10, 13],
  '7#9': [0, 4, 7, 10, 15],
  dim7: [0, 3, 6, 9],
  '11': [0, 4, 7, 10, 14, 17],
  '13': [0, 4, 7, 10, 14, 17, 21],
}

const MAJOR_SCALE_PITCHES = [0, 2, 4, 5, 7, 9, 11]
const MINOR_SCALE_PITCHES = [0, 2, 3, 5, 7, 8, 10]

function chordPitchClasses(chordSymbol: string): number[] {
  const parsed = parseChordSymbol(chordSymbol)
  if (!parsed) return []
  const rootPc = noteToPitchClass(parsed.root)
  const intervals = INTERVAL_PITCHES[parsed.quality] ?? INTERVAL_PITCHES.maj
  const pcs = intervals.map((iv) => (rootPc + (iv % 12)) % 12)
  // Include bass note pitch class in the set when present
  if (parsed.bass) {
    pcs.push(noteToPitchClass(parsed.bass))
  }
  return pcs
}

function scalePitchClasses(keyLabel: string): number[] {
  const parsed = parseKey(keyLabel)
  if (!parsed) return []
  const intervals = parsed.mode === 'minor' ? MINOR_SCALE_PITCHES : MAJOR_SCALE_PITCHES
  return intervals.map((iv) => (parsed.semitone + iv) % 12)
}

export function buildNoteSelectionDetail(
  keyLabel: string,
  selectedNote: SelectedFretNote | null,
  currentChord?: string | null,
  confidence?: number | null,
): NoteSelectionDetail | null {
  if (!selectedNote) return null
  const midi = inferMidiFromNoteSelection(selectedNote)
  const cell = resolveFretCell(selectedNote)
  if (midi == null || !cell) return null
  const noteName = midiToNoteName(midi)
  const degree = scaleDegreeLabel(keyLabel, midi)
  const { primary: fingerLine, alternates: alternateFingerLines } = suggestFingerings(cell, allCellsForMidi(midi))
  const coach = buildStudyCoachLine({
    noteName,
    degreeLabel: degree,
    fingerLine,
    keyLabel,
  })

  let chordToneStatus: ChordToneStatus | null = null
  if (currentChord && currentChord !== 'N') {
    const notePc = ((Math.round(midi) % 12) + 12) % 12
    const chordPcs = chordPitchClasses(currentChord)
    if (chordPcs.includes(notePc)) {
      chordToneStatus = 'chord_tone'
    } else {
      const scalePcs = scalePitchClasses(keyLabel)
      if (scalePcs.includes(notePc)) {
        chordToneStatus = 'tension'
      } else {
        chordToneStatus = 'chromatic'
      }
    }
  }

  return {
    noteName,
    degree,
    fingerLine,
    alternateFingerLines,
    coach,
    chordToneStatus,
    confidence: confidence ?? null,
  }
}
