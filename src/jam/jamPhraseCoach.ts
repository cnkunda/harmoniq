import type { JamPhraseFeatures } from '@/src/jam/jamPhraseFeatures'
import {
  JAM_PHRASE_DENSITY_HIGH,
  JAM_PHRASE_DENSITY_LOW,
  JAM_PHRASE_MIN_DURATION_MS,
  JAM_PHRASE_MIN_NOTES_FOR_COACH,
  JAM_PHRASE_NARROW_MIDI_SPAN_MAX,
  JAM_PHRASE_NARROW_UNIQUE_PC_MAX,
  JAM_PHRASE_SPACIOUS_MIN_MS,
  JAM_PHRASE_TIMING_PUSH_PULL_SEC,
} from '@/src/utils/jamPhraseConfig'

export type JamPhraseCoachLines = {
  observation: string
  suggestion: string
}

/**
 * One musical insight → two short lines. Empty strings when the phrase is too thin to read.
 */
export function coachFromPhraseFeatures(
  phrase: { startTime: number; endTime: number },
  f: JamPhraseFeatures,
): JamPhraseCoachLines {
  const durationMs = phrase.endTime - phrase.startTime

  if (durationMs < JAM_PHRASE_MIN_DURATION_MS || f.noteCount < JAM_PHRASE_MIN_NOTES_FOR_COACH) {
    return { observation: '', suggestion: '' }
  }

  const densityHigh = f.notesPerSecond >= JAM_PHRASE_DENSITY_HIGH
  const densityLow = f.notesPerSecond <= JAM_PHRASE_DENSITY_LOW && durationMs >= JAM_PHRASE_SPACIOUS_MIN_MS

  const timing = f.meanBeatOffsetSec
  const rushing =
    timing != null && timing < -JAM_PHRASE_TIMING_PUSH_PULL_SEC && f.noteCount >= JAM_PHRASE_MIN_NOTES_FOR_COACH
  const dragging =
    timing != null && timing > JAM_PHRASE_TIMING_PUSH_PULL_SEC && f.noteCount >= JAM_PHRASE_MIN_NOTES_FOR_COACH

  const narrowVocab =
    f.noteCount >= 3 &&
    (f.uniquePitchClasses <= JAM_PHRASE_NARROW_UNIQUE_PC_MAX ||
      f.midiSpan <= JAM_PHRASE_NARROW_MIDI_SPAN_MAX)

  if (densityHigh) {
    return {
      observation: 'You’re filling every gap in that line.',
      suggestion: 'Try letting the last note breathe before you reach for the next one.',
    }
  }

  if (rushing) {
    return {
      observation: 'You’re leaning a little ahead of the groove on that phrase.',
      suggestion: 'Let the pulse catch you — land relaxed, not early.',
    }
  }

  if (dragging) {
    return {
      observation: 'You’re settling behind the beat there.',
      suggestion: 'Nudge the next entrance a hair earlier so the line rides the pocket.',
    }
  }

  if (narrowVocab) {
    return {
      observation: 'You’re staying in a small melodic pocket.',
      suggestion: 'Reach up or down once to answer yourself — stretch the shape.',
    }
  }

  if (densityLow) {
    return {
      observation: 'The space in that phrase is doing real work.',
      suggestion: 'Keep trusting the gaps — that’s where the line speaks.',
    }
  }

  return { observation: '', suggestion: '' }
}
