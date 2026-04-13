import { allCellsForMidi, inferMidiFromNoteSelection, resolveFretCell } from '@/src/music/fretboardCell'
import { suggestFingerings } from '@/src/music/fingerSuggestion'
import { buildStudyCoachLine, midiToNoteName, scaleDegreeLabel } from '@/src/music/scaleDegree'

export type SelectedFretNote = { string?: number; fret?: number; midi?: number }

export type NoteSelectionDetail = {
  noteName: string
  degree: string
  fingerLine: string
  alternateFingerLines: string[]
  coach: string
}

export function buildNoteSelectionDetail(keyLabel: string, selectedNote: SelectedFretNote | null): NoteSelectionDetail | null {
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
  return { noteName, degree, fingerLine, alternateFingerLines, coach }
}
