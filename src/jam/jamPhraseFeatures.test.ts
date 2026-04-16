import { describe, expect, it } from 'vitest'

import { phraseToFeatures } from '@/src/jam/jamPhraseFeatures'
import type { JamPhrase } from '@/src/jam/jamPhraseSegmenter'

describe('phraseToFeatures', () => {
  it('computes beat offsets when every note has backing positions', () => {
    const beatMs = 60000 / 120 // 500ms
    const phrase: JamPhrase = {
      startTime: 0,
      endTime: 2000,
      notes: [
        { tMs: 0, midi: 60, backingPosMs: 0 },
        { tMs: 400, midi: 64, backingPosMs: 400 },
        { tMs: 800, midi: 67, backingPosMs: 800 + beatMs * 0.06 },
      ],
    }
    const f = phraseToFeatures(phrase, 120)
    expect(f.meanBeatOffsetSec).not.toBeNull()
    expect(f.beatOffsetVarianceSec2).not.toBeNull()
    expect(f.noteCount).toBe(3)
  })

  it('omits beat stats when bpm is missing', () => {
    const phrase: JamPhrase = {
      startTime: 0,
      endTime: 1000,
      notes: [
        { tMs: 0, midi: 60, backingPosMs: 0 },
        { tMs: 500, midi: 64, backingPosMs: 500 },
      ],
    }
    const f = phraseToFeatures(phrase, null)
    expect(f.meanBeatOffsetSec).toBeNull()
  })
})
