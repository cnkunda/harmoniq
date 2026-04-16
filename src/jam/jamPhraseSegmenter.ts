import type { PitchReading } from '@/src/pitch/pitchTypes'
import {
  JAM_PHRASE_ONSET_DEBOUNCE_MS,
  JAM_PHRASE_SILENCE_END_MS,
} from '@/src/utils/jamPhraseConfig'

export type JamPhraseNote = {
  tMs: number
  midi: number
  /** Loop timeline ms from `expo-av` when the note onset was captured (for beat feel). */
  backingPosMs?: number
}

export type JamPhrase = {
  startTime: number
  endTime: number
  notes: JamPhraseNote[]
}

export type JamPhraseSegmenterOptions = {
  /** Called when a phrase closes after sustained silence (or `flush`). */
  onPhraseClosed: (phrase: JamPhrase) => void
  silenceEndMs?: number
  onsetDebounceMs?: number
}

function isSilentFrame(r: PitchReading): boolean {
  const hz = r.hz
  const usable = hz != null && Number.isFinite(hz) && hz > 0
  return !usable
}

/**
 * Streams pitch readings into phrases bounded by ~500ms silence.
 * Onsets: phrase start + semitone changes (debounced). Same pitch legato = one note.
 */
export function createJamPhraseSegmenter(options: JamPhraseSegmenterOptions): {
  push: (reading: PitchReading, tMs: number, backingPosMs?: number | null) => void
  flush: (tMs: number) => void
  reset: () => void
} {
  const silenceEndMs = options.silenceEndMs ?? JAM_PHRASE_SILENCE_END_MS
  const onsetDebounceMs = options.onsetDebounceMs ?? JAM_PHRASE_ONSET_DEBOUNCE_MS

  let inPhrase = false
  let notes: JamPhraseNote[] = []
  let lastMidi: number | null = null
  let lastOnsetMs = -Infinity
  let lastNonSilentMs = 0
  let silenceStartedAt: number | null = null

  const closePhrase = (endMs: number) => {
    if (!inPhrase || notes.length === 0) {
      inPhrase = false
      notes = []
      lastMidi = null
      silenceStartedAt = null
      return
    }
    const startTime = notes[0]!.tMs
    const endTime = Math.max(startTime, endMs)
    options.onPhraseClosed({
      startTime,
      endTime,
      notes: [...notes],
    })
    inPhrase = false
    notes = []
    lastMidi = null
    silenceStartedAt = null
  }

  const reset = () => {
    inPhrase = false
    notes = []
    lastMidi = null
    lastOnsetMs = -Infinity
    lastNonSilentMs = 0
    silenceStartedAt = null
  }

  const push = (reading: PitchReading, tMs: number, backingPosMs?: number | null) => {
    const silent = isSilentFrame(reading)

    if (silent) {
      if (inPhrase) {
        if (silenceStartedAt == null) silenceStartedAt = tMs
        if (tMs - silenceStartedAt >= silenceEndMs) {
          closePhrase(lastNonSilentMs)
        }
      }
      return
    }

    // Audible frame
    silenceStartedAt = null
    lastNonSilentMs = tMs
    const midi = Math.round(reading.midi)
    const pos =
      typeof backingPosMs === 'number' && Number.isFinite(backingPosMs) ? backingPosMs : undefined

    if (!inPhrase) {
      inPhrase = true
      notes = [{ tMs, midi, ...(pos != null ? { backingPosMs: pos } : {}) }]
      lastMidi = midi
      lastOnsetMs = tMs
      return
    }

    if (lastMidi == null) {
      lastMidi = midi
      return
    }

    if (Math.abs(midi - lastMidi) >= 1 && tMs - lastOnsetMs >= onsetDebounceMs) {
      notes.push({ tMs, midi, ...(pos != null ? { backingPosMs: pos } : {}) })
      lastMidi = midi
      lastOnsetMs = tMs
    }
  }

  /** End open phrase when stopping jam (uses last heard time as boundary). */
  const flush = (tMs: number) => {
    if (!inPhrase || notes.length === 0) {
      reset()
      return
    }
    closePhrase(Math.max(lastNonSilentMs, tMs))
  }

  return { push, flush, reset }
}
