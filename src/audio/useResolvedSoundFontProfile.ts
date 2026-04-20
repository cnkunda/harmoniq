import { useEffect, useMemo, useState } from 'react'

import { getAppPref } from '@/src/db/client'
import { PREF_LAST_SOUNDFONT_PROFILE } from '@/src/db/schema'
import type { TabRenderPresetName } from '@/src/session/tabThemePresets'
import {
  isSoundFontProfileId,
  resolveSoundFontProfileFromStyleAndSession,
  type SoundFontProfileId,
} from '@/src/audio/soundfontProfiles'

/** Reads persisted last-good profile once, then resolves automatic profile from style + session step. */
export function useResolvedSoundFontProfile(
  styleLabel: string | null | undefined,
  tabRenderPreset: TabRenderPresetName | undefined,
): SoundFontProfileId {
  const [persisted, setPersisted] = useState<SoundFontProfileId | null>(null)

  useEffect(() => {
    let cancelled = false
    void getAppPref(PREF_LAST_SOUNDFONT_PROFILE).then((raw) => {
      if (cancelled) return
      if (isSoundFontProfileId(raw)) setPersisted(raw)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return useMemo(
    () => resolveSoundFontProfileFromStyleAndSession(styleLabel, tabRenderPreset, persisted),
    [styleLabel, tabRenderPreset, persisted],
  )
}
