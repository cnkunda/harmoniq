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
  gp5Base64: string
}

// Stub GP5 base64 for placement phrases (simple A minor pentatonic pattern)
// Generated from backend tabgen STUB_TAB_FULL_GP5_BASE64
const PLACEMENT_GP5_STUB =
  'GEZJQ0hJRVIgR1VJVEFSIFBSTyB2NS4xMAAAAAAAABQAAAATSGFybW9uaXEgdGFiIChmdWxsKQEAAAAAAQAAAAABAAAAAAEAAAAAAQAAAAABAAAAAAEAAAAAAAAAAAAAAAAEAAAAAAAAAAQAAAAAAAAABAAAAAAAAAAEAAAAAAAAAAQAAAAAAAABkAAAAAAAAAAAAAAAAAAAAAAAA0gAAACkBAAAKAAAACgAAAA8AAAAKAAAAZAAAAP8BCAAAAAcldGl0bGUlCwAAAAolc3VidGl0bGUlCQAAAAglYXJ0aXN0JQgAAAAHJWFsYnVtJREAAAAQV29yZHMgYnkgJXdvcmRzJREAAAAQTXVzaWMgYnkgJW11c2ljJR4AAAAdV29yZHMgJiBNdXNpYyBieSAlV09SRFNNVVNJQyUWAAAAFUNvcHlyaWdodCAlY29weXJpZ2h0JTYAAAA1QWxsIFJpZ2h0cyBSZXNlcnZlZCAtIEludGVybmF0aW9uYWwgQ29weXJpZ2h0IFNlY3VyZWQNAAAADFBhZ2UgJU4lLyVQJQkAAAAITW9kZXJhdGV4AAAAAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAA/////w0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAA/////w0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAA/////w0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAAGQAAAA0IAAAAAAAA//////////////////////////////////////////////////8AAAAAAQAAAAEAAABDBAQAAAICAgIAAAAIBkd1aXRhcgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGAAAAQAAAADsAAAA3AAAAMgAAAC0AAAAoAAAAAAAAAAEAAAABAAAAAgAAABgAAAAAAAAA/wAAAEMAAAAAAAAAAAAAAABkAAAAAAAAAAAAAAAAAAAA/////////////////////wAAAAABAAAAAAEAAAAAAAQAAAAAAEAgAQAAAAAAAEAgAQMAAABAAgAAAABAAgAAAAAAAAAAAA=='

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
    gp5Base64: PLACEMENT_GP5_STUB,
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
    gp5Base64: PLACEMENT_GP5_STUB,
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
    gp5Base64: PLACEMENT_GP5_STUB,
  },
]
