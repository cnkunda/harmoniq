# Demo lesson audio

The bundled demo lesson plays a short **WAV** clip shipped with the app (no `/lesson-file` fetch).
All six stem channels in the mixer reference the same audio file through separate
`bundled://` keys — this lets the demo showcase the full stem-mixer UX (solo/mute,
volume, pan) without requiring separate multi-track assets.

| File | Role |
|------|------|
| [`reggae_clean_30s.wav`](./reggae_clean_30s.wav) | Single 30s reggae sample shared by all 6 demo stems |

## Bundled stem keys

| Key | Used by |
|-----|---------|
| `bundled://demo/reggae-guitar` | `LessonJSON.stems.guitar` |
| `bundled://demo/reggae-bass` | `LessonJSON.stems.bass` |
| `bundled://demo/reggae-drums` | `LessonJSON.stems.drums` |
| `bundled://demo/reggae-vocals` | `LessonJSON.stems.vocals` |
| `bundled://demo/reggae-piano` | `LessonJSON.stems.piano` |
| `bundled://demo/reggae-other` | `LessonJSON.stems.other` |
| `bundled://demo/reggae` | Legacy alias (backward compat) |
| `bundled://demo/am-blues-70` | Legacy alias (backward compat) |

Defined in [`src/demo/bundledStemRegistry.ts`](../../src/demo/bundledStemRegistry.ts).

## Demo lesson metadata

The demo `LessonJSON` (produced by [`src/demo/demoLesson.ts`](../../src/demo/demoLesson.ts))
includes:

- **6 bundled stems** — all pointing to the same WAV via separate registry keys
- **3 sections** — Main Riff / Fill / Turnaround with GP5 tab on each
- **Chord timeline** — G-C-G-D-G-C progression timed to 90 BPM bars
- **Solo notes** — G major pentatonic phrases across all 11 bars
- **Beat grid** — 44 beat timestamps at 90 BPM 4/4
- **Bar timestamps** — 11 bars at ~2.667 s each

The demo runs fully offline — no backend analyze job, no `/lesson-file` requests,
no database persistence.

## Replacing the demo audio

Replace `reggae_clean_30s.wav` with your own rights-cleared clip if you redistribute;
keep the filename or update the registry + `getDemoLesson()` stem paths.
