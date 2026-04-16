import { describe, expect, it } from 'vitest'

import { coachFromPhraseFeatures } from '@/src/jam/jamPhraseCoach'
import type { JamPhraseFeatures } from '@/src/jam/jamPhraseFeatures'

function feat(partial: Partial<JamPhraseFeatures>): JamPhraseFeatures {
  return {
    durationSec: 1.2,
    notesPerSecond: 2,
    uniquePitchClasses: 4,
    midiSpan: 7,
    contour: 'mixed',
    meanBeatOffsetSec: null,
    beatOffsetVarianceSec2: null,
    noteCount: 3,
    ...partial,
  }
}

describe('coachFromPhraseFeatures', () => {
  it('returns empty when phrase is too short', () => {
    const phrase = { startTime: 0, endTime: 150 }
    const out = coachFromPhraseFeatures(phrase, feat({ noteCount: 4 }))
    expect(out.observation).toBe('')
    expect(out.suggestion).toBe('')
  })

  it('returns empty when too few notes', () => {
    const phrase = { startTime: 0, endTime: 2000 }
    const out = coachFromPhraseFeatures(phrase, feat({ noteCount: 1 }))
    expect(out.observation).toBe('')
  })

  it('prefers overplaying when density is high', () => {
    const phrase = { startTime: 0, endTime: 2000 }
    const out = coachFromPhraseFeatures(phrase, feat({ notesPerSecond: 6, noteCount: 8 }))
    expect(out.observation).toContain('gap')
    expect(out.suggestion).toContain('breathe')
  })

  it('detects rushing when mean beat offset is negative', () => {
    const phrase = { startTime: 0, endTime: 2000 }
    const out = coachFromPhraseFeatures(
      phrase,
      feat({ notesPerSecond: 2, meanBeatOffsetSec: -0.08, noteCount: 3 }),
    )
    expect(out.observation).toContain('ahead')
    expect(out.suggestion).toContain('pulse')
  })

  it('detects dragging when mean beat offset is positive', () => {
    const phrase = { startTime: 0, endTime: 2000 }
    const out = coachFromPhraseFeatures(
      phrase,
      feat({ notesPerSecond: 2, meanBeatOffsetSec: 0.09, noteCount: 3 }),
    )
    expect(out.observation).toContain('behind')
  })

  it('praises space when density is low and phrase is long enough', () => {
    const phrase = { startTime: 0, endTime: 1200 }
    const out = coachFromPhraseFeatures(
      phrase,
      feat({ notesPerSecond: 0.8, noteCount: 3, durationSec: 1.2 }),
    )
    expect(out.observation).toContain('space')
  })
})
