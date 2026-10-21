import { describe, expect, it, vi } from 'vitest'

vi.mock('@/src/constants/backingTracks', () => ({
  BACKING_TRACKS: [
    { id: 'am-blues-70', label: 'A minor — slow blues shuffle', bpm: 70, key: 'A minor', source: 1 },
    { id: 'g-finger-80', label: 'G major — fingerpicking groove', bpm: 80, key: 'G major', source: 2 },
  ],
}))

import { buildJamPracticeHref, resolveJamPracticeTrack } from '@/src/jam/jamPracticeTrack'

describe('resolveJamPracticeTrack', () => {
  it('resolves a classic snapshot by track id', () => {
    const track = resolveJamPracticeTrack({
      trackId: 'am-blues-70',
      trackKey: 'A minor',
      trackBpm: 70,
    })
    expect(track?.id).toBe('am-blues-70')
  })

  it('matches an AI snapshot to a classic loop by key and tempo', () => {
    const track = resolveJamPracticeTrack({
      trackId: 'ai-instrumental',
      trackKey: 'G major',
      trackBpm: 80,
    })
    expect(track?.id).toBe('g-finger-80')
  })

  it('returns null when no classic loop shares the key', () => {
    const track = resolveJamPracticeTrack({
      trackId: 'ai-instrumental',
      trackKey: 'D dorian',
      trackBpm: 70,
    })
    expect(track).toBeNull()
  })
})

describe('buildJamPracticeHref', () => {
  it('encodes the loop region and phrase index', () => {
    expect(
      buildJamPracticeHref({
        trackId: 'am-blues-70',
        startMs: 1000.4,
        endMs: 2000.6,
        phraseIndex: 2,
      }),
    ).toBe('/jam-practice?trackId=am-blues-70&startMs=1000&endMs=2001&phraseIndex=2')
  })
})
