import { describe, expect, it } from 'vitest'

import { resolveJamBackingSource, type JamBackingProvenance } from '@/src/jam/jamBackingSource'

const base: JamBackingProvenance = {
  prompt_used: 'Instrumental guitar practice backing track. Key: A minor. Tempo: 70 BPM',
}

describe('resolveJamBackingSource', () => {
  it('reports server generation when no fallback marker is present', () => {
    expect(resolveJamBackingSource(base)).toEqual({
      provider: 'server',
      usedFallback: false,
      fallbackTrack: null,
    })
  })

  it('detects the legacy bundled fallback marker in prompt_used', () => {
    expect(
      resolveJamBackingSource({
        ...base,
        prompt_used: `${base.prompt_used} [fallback_track=a-minor-blues.mp3]`,
      }),
    ).toEqual({
      provider: 'bundled',
      usedFallback: true,
      fallbackTrack: 'a-minor-blues.mp3',
    })
  })

  it('honors explicit provider metadata from newer backends', () => {
    expect(
      resolveJamBackingSource({
        ...base,
        provider: 'ace-step-modal',
        used_fallback: false,
      }),
    ).toEqual({
      provider: 'ace-step-modal',
      usedFallback: false,
      fallbackTrack: null,
    })
  })

  it('trusts explicit used_fallback=true even without a track name', () => {
    expect(
      resolveJamBackingSource({
        ...base,
        provider: 'bundled',
        used_fallback: true,
        fallback_reason: 'provider_timeout',
      }),
    ).toEqual({
      provider: 'bundled',
      usedFallback: true,
      fallbackTrack: null,
    })
  })
})
