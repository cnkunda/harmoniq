/**
 * SoundFont profiles for AlphaTab synth (Commit 60).
 * Keep `PINNED_*_URL` values in sync with `assets/alphatab-harness/index.html` (`SOUNDFONT_PROFILE_URLS`).
 */

export const DEFAULT_SOUNDFONT_PROFILE_ID = 'general_user' as const

export const SOUND_FONT_PROFILE_IDS = ['general_user', 'fluid_r3_mono'] as const

export type SoundFontProfileId = (typeof SOUND_FONT_PROFILE_IDS)[number]

/** Pinned CDN mirrors — same banks as bundled assets under `assets/soundfonts/` (see SOURCES.md). */
export const PINNED_GENERAL_USER_SF2_URL =
  'https://cdn.jsdelivr.net/gh/ad-si/GeneralUser@f553a9866915130d5fffaa01e457ad53c60bef82/GeneralUser.sf2'

export const PINNED_FLUID_R3_MONO_SF3_URL =
  'https://cdn.jsdelivr.net/gh/musescore/MuseScore@master/share/sound/FluidR3Mono_GM.sf3'

export const SOUNDFONT_PROFILE_LOAD_TIMEOUT_MS = 25_000

export function isSoundFontProfileId(value: unknown): value is SoundFontProfileId {
  return typeof value === 'string' && (SOUND_FONT_PROFILE_IDS as readonly string[]).includes(value)
}

/**
 * Session + style hooks for automatic profile selection (two reference fixtures in tests).
 */
export function resolveSoundFontProfileFromStyleAndSession(
  styleLabel: string | null | undefined,
  renderPreset: string | undefined,
  persistedProfile: SoundFontProfileId | null | undefined,
): SoundFontProfileId {
  const style = styleLabel?.trim().toLowerCase() ?? ''

  if (
    /\b(rock|metal|punk|grunge|shred|distortion|overdrive|hard\s*rock)\b/.test(style) ||
    /\b(electric\s*lead|lead\s*guitar)\b/.test(style)
  ) {
    return 'fluid_r3_mono'
  }

  if (/\b(bass|funk|rhythm\s*guitar|ensemble)\b/.test(style)) {
    return 'fluid_r3_mono'
  }

  if (
    /\b(acoustic|fingerstyle|finger\s*style|classical|folk|country|bluegrass|ballad|worship|clean|jazz)\b/.test(style)
  ) {
    return 'general_user'
  }

  const preset = renderPreset?.trim().toLowerCase()
  if (!style && persistedProfile && (preset === 'listen' || preset === 'play')) {
    return persistedProfile
  }

  return DEFAULT_SOUNDFONT_PROFILE_ID
}
