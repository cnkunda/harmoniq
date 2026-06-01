import type {
  ChordCorrection,
  ChordEvent,
  ChordTimeline,
  CorrectionSet,
  LessonJSON,
  NoteCorrection,
  SoloNote,
  SoloNotes,
  VoicingOverride,
} from '@/src/types'

/**
 * Apply chord corrections to a chord timeline, returning a new timeline.
 * Corrected chords get confidence=1.0 to distinguish from ML output.
 */
export function applyCorrectionsToChordTimeline(
  timeline: ChordTimeline | null | undefined,
  corrections: ChordCorrection[],
): ChordTimeline | null {
  if (!timeline?.events?.length || !corrections.length) return timeline ?? null
  const lookup = new Map(corrections.map((c) => [c.eventIndex, c]))
  const events: ChordEvent[] = timeline.events.map((ev, idx) => {
    const c = lookup.get(idx)
    if (!c) return ev
    return { ...ev, chord: c.correctedChord, confidence: 1.0 }
  })
  return { ...timeline, events }
}

/**
 * Apply note corrections to solo notes, returning new notes.
 * Corrected fields override originals; uncorrected fields are preserved.
 */
export function applyCorrectionsToSoloNotes(
  notes: { notes: Array<{ start_time: number; duration: number; pitch: number; velocity?: number }> } | null | undefined,
  corrections: NoteCorrection[],
): SoloNotes | null {
  if (!notes?.notes?.length || !corrections.length) return null
  const lookup = new Map(corrections.map((c) => [c.noteIndex, c]))
  const noteArr: SoloNote[] = notes.notes.map((note, idx) => {
    const c = lookup.get(idx)
    if (!c) return { ...note, velocity: note.velocity ?? 80 }
    return {
      start_time: c.correctedStartTime ?? note.start_time,
      duration: c.correctedDuration ?? note.duration,
      pitch: c.correctedPitch ?? note.pitch,
      velocity: note.velocity ?? 80,
    }
  })
  return { notes: noteArr }
}

/**
 * Build a map from chord timestamp to voicing override.
 */
export function buildVoicingMap(overrides: VoicingOverride[]): Map<number, string> {
  const m = new Map<number, string>()
  for (const o of overrides) m.set(o.chordTimestamp, o.correctedShape)
  return m
}

/**
 * Apply all corrections to a lesson, returning a new lesson object.
 * Does not mutate the original.
 */
export function applyCorrectionsToLesson(
  lesson: LessonJSON,
  corrections: CorrectionSet,
): LessonJSON {
  const hasChordCorrections = corrections.chordCorrections.length > 0
  const hasNoteCorrections = corrections.noteCorrections.length > 0
  if (!hasChordCorrections && !hasNoteCorrections) return lesson

  const patched = { ...lesson }

  if (hasChordCorrections && lesson.chord_timeline) {
    patched.chord_timeline = applyCorrectionsToChordTimeline(
      lesson.chord_timeline,
      corrections.chordCorrections,
    )
  }

  if (hasNoteCorrections && lesson.solo_notes) {
    patched.solo_notes = applyCorrectionsToSoloNotes(
      lesson.solo_notes,
      corrections.noteCorrections,
    )
  }

  // Compute correction metrics
  const totalEvents =
    (lesson.chord_timeline?.events?.length ?? 0) +
    (lesson.solo_notes?.notes?.length ?? 0)
  const totalCorrections =
    corrections.chordCorrections.length + corrections.noteCorrections.length
  patched.correction_count = totalCorrections
  patched.correction_coverage = totalEvents > 0 ? totalCorrections / totalEvents : 0

  return patched
}
