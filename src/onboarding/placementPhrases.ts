/**
 * Three canned placement phrases — same bundled reference audio, distinct rhythmic grids for scoring variety.
 * PRIORITIES §32.
 */

export const PLACEMENT_SKILL_NODES = [
  'pitch_accuracy',
  'phrasing',
  'timing',
  'bend_accuracy',
  'vibrato_control',
] as const

export type PlacementPhraseConfig = {
  title: string
  instruction: string
  section: Record<string, unknown>
}

export const PLACEMENT_PHRASES: PlacementPhraseConfig[] = [
  {
    title: 'Phrase 1 — steady pocket',
    instruction: 'Play simple quarter notes with the click in your head. Keep volume even; we are mapping timing and pitch stability.',
    section: {
      label: 'Placement A',
      key: 'A minor',
      tempo: 70,
      beat_grid: [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5],
      bar_timestamps: [0, 2, 4],
    },
  },
  {
    title: 'Phrase 2 — syncopation',
    instruction: 'Lean slightly behind the beat on offbeats. Short notes, clear space between them.',
    section: {
      label: 'Placement B',
      key: 'A minor',
      tempo: 72,
      beat_grid: [0, 0.33, 0.66, 1, 1.5, 2, 2.25, 2.75, 3.25],
      bar_timestamps: [0, 1.5, 3],
    },
  },
  {
    title: 'Phrase 3 — lyrical line',
    instruction: 'Connect two small shapes on one breath. Let notes ring; vibrato optional.',
    section: {
      label: 'Placement C',
      key: 'A minor',
      tempo: 68,
      beat_grid: [0, 0.75, 1.5, 2.25, 3, 3.75, 4.5],
      bar_timestamps: [0, 2.25, 4.5],
    },
  },
]
