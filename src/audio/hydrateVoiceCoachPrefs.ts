import { getAppPref } from '@/src/db/client'
import { PREF_VOICE_COACH_ENABLED, PREF_VOICE_COACH_GENDER, PREF_VOICE_COACH_RATE } from '@/src/db/schema'
import type { VoiceGenderPref } from '@/src/stores/voiceCoachPrefsStore'
import { useVoiceCoachPrefsStore } from '@/src/stores/voiceCoachPrefsStore'

function parseGender(raw: string | null): VoiceGenderPref {
  const g = (raw ?? '').trim().toLowerCase()
  if (g === 'female' || g === 'male') return g
  return 'default'
}

/** Load voice coach prefs into memory for synchronous `speak()` gating (commit 72). */
export async function hydrateVoiceCoachPrefs(): Promise<void> {
  const [en, r, g] = await Promise.all([
    getAppPref(PREF_VOICE_COACH_ENABLED),
    getAppPref(PREF_VOICE_COACH_RATE),
    getAppPref(PREF_VOICE_COACH_GENDER),
  ])
  const enabled = en !== '0'
  const parsed = Number.parseFloat(r ?? '1')
  const rate = Number.isFinite(parsed) ? Math.max(0.7, Math.min(1.2, parsed)) : 1
  useVoiceCoachPrefsStore.getState().setAll({ enabled, rate, gender: parseGender(g) })
}
