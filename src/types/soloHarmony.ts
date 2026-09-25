/** Commit 123: Solo Harmony Enrichment — frontend types. */

export interface ChordToneAnalysis {
  /** Diatonic scale degree (1-7) for chord tones/tensions; null for chromatic passing tones */
  scale_degree: number | null
  /** Human-readable label: "R", "b3", "3", "4", "b5", "5", "b7", "7", "#4", etc. */
  scale_degree_name: string
  /** Harmonic role of this note in the current chord */
  chord_tone_type: 'chord_tone' | 'tension' | 'chromatic' | 'pedal'
  /** Absolute distance from chord root in semitones (0-11) */
  semitone_distance: number
}

export interface HarmonizedSoloNote {
  start_time: number
  duration: number
  pitch: number
  velocity: number
  /** Active chord symbol at note onset (e.g., "C:maj7"); null if no chord */
  chord: string | null
  /** Harmonic analysis of this note; null when chord is unavailable or "N" */
  chord_analysis: ChordToneAnalysis | null
}

export interface HarmonizedSoloNotes {
  notes: HarmonizedSoloNote[]
  /** Total solo notes (including those over "N" chords) */
  note_count: number
  /** Fraction of harmonically analyzed notes that are chord tones (0-1) */
  chord_tone_pct: number
  /** Fraction of harmonically analyzed notes that are tensions (0-1) */
  tension_note_pct: number
  /** Fraction of harmonically analyzed notes that are chromatic (0-1) */
  chromatic_pct: number
}

export interface BarScope {
  /** Zero-based bar index */
  bar_index: number
  start_time: number
  end_time: number
  /** Dominant chord in this bar; null if no chord events fall in this bar */
  chord: string | null
  /** Suggested scale names for improvisation over this bar */
  suggested_scales: string[]
  /** Inferred CAGED position (e.g., "position 2 (CAGED: E-form)") */
  primary_position: string | null
  /** Indices into HarmonizedSoloNotes.notes for notes in this bar */
  notes: number[]
}
