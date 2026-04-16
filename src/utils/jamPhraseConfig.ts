/** Tunable thresholds for Jam phrase segmentation + coaching (QA can adjust here). */

export const JAM_PHRASE_SILENCE_END_MS = 500

/** Ignore phrase-level coaching for very short utterances. */
export const JAM_PHRASE_MIN_DURATION_MS = 200

/** Min notes to emit non-neutral coaching. */
export const JAM_PHRASE_MIN_NOTES_FOR_COACH = 2

/** Debounce between counted onsets (same thread as pitch callbacks). */
export const JAM_PHRASE_ONSET_DEBOUNCE_MS = 45

/** Notes per second above this → “overplaying” hint. */
export const JAM_PHRASE_DENSITY_HIGH = 4.5

/** Notes per second below this (with long enough phrase) → spacious. */
export const JAM_PHRASE_DENSITY_LOW = 1.2

/** |mean beat offset| above this (seconds) → rushing / dragging copy. */
export const JAM_PHRASE_TIMING_PUSH_PULL_SEC = 0.05

/** Unique pitch classes ≤ this → “narrow vocabulary”. */
export const JAM_PHRASE_NARROW_UNIQUE_PC_MAX = 2

/** MIDI span (max-min) ≤ this for ≥3 notes → narrow. */
export const JAM_PHRASE_NARROW_MIDI_SPAN_MAX = 4

/** Phrase duration (ms) to qualify for “space” praise. */
export const JAM_PHRASE_SPACIOUS_MIN_MS = 900
