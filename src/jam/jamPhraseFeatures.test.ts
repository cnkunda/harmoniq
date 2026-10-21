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

  it('computes mean absolute cents from onset readings', () => {
    const phrase: JamPhrase = {
      startTime: 0,
      endTime: 1000,
      notes: [
        { tMs: 0, midi: 60, cents: 20 },
        { tMs: 500, midi: 64, cents: -10 },
        { tMs: 750, midi: 67, cents: null },
      ],
    }
    const f = phraseToFeatures(phrase, 120)
    expect(f.meanAbsCents).toBe(15)
  })

  it('reports phrase and backing boundaries', () => {
    const phrase: JamPhrase = {
      startTime: 200,
      endTime: 2400,
      notes: [
        { tMs: 200, midi: 60, backingPosMs: 5000 },
        { tMs: 900, midi: 64, backingPosMs: 5700 },
        { tMs: 1600, midi: 67 },
      ],
    }
    const f = phraseToFeatures(phrase, 120)
    expect(f.startMs).toBe(200)
    expect(f.endMs).toBe(2400)
    expect(f.backingStartMs).toBe(5000)
    expect(f.backingEndMs).toBe(7200)
  })

  it('maps phrase end when the last note has no backing position', () => {
    const phrase: JamPhrase = {
      startTime: 100,
      endTime: 1100,
      notes: [
        { tMs: 100, midi: 60, backingPosMs: 300 },
        { tMs: 600, midi: 64 },
      ],
    }
    const f = phraseToFeatures(phrase, null)
    expect(f.backingStartMs).toBe(300)
    expect(f.backingEndMs).toBe(1300)
  })
})
