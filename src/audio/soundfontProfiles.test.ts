import { describe, expect, it } from 'vitest'

import {
  DEFAULT_SOUNDFONT_PROFILE_ID,
  resolveSoundFontProfileFromStyleAndSession,
} from '@/src/audio/soundfontProfiles'

describe('resolveSoundFontProfileFromStyleAndSession', () => {
  it('fixture: Rock Lead → fluid_r3_mono', () => {
    expect(
      resolveSoundFontProfileFromStyleAndSession('Rock Lead', 'play', null),
    ).toBe('fluid_r3_mono')
  })

  it('fixture: Fingerstyle Acoustic → general_user', () => {
    expect(
      resolveSoundFontProfileFromStyleAndSession('Fingerstyle Acoustic', 'study', null),
    ).toBe('general_user')
  })

  it('defaults when style unknown and no persisted profile', () => {
    expect(resolveSoundFontProfileFromStyleAndSession('', 'study', null)).toBe(
      DEFAULT_SOUNDFONT_PROFILE_ID,
    )
  })

  it('uses persisted profile for empty style on listen when provided', () => {
    expect(resolveSoundFontProfileFromStyleAndSession('', 'listen', 'fluid_r3_mono')).toBe(
      'fluid_r3_mono',
    )
  })
})
