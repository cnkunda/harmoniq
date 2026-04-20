import { setAppPref } from '@/src/db/client'
import { PREF_LAST_SOUNDFONT_PROFILE } from '@/src/db/schema'
import type { SoundFontProfileId } from '@/src/audio/soundfontProfiles'

/** Persist last successfully applied SoundFont profile (Commit 60). */
export async function persistLastSuccessfulSoundFontProfile(profileId: SoundFontProfileId): Promise<void> {
  await setAppPref(PREF_LAST_SOUNDFONT_PROFILE, profileId)
}
