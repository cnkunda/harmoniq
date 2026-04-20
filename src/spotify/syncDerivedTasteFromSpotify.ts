import { deriveTasteProfile } from '@/src/api/analyze'
import { commitTasteQuizProfile } from '@/src/db/client'
import type { SpotifyTasteProfile } from '@/src/types'

/** POST /taste/derive + persist prefs so practice plan / coach see derived taste (commit 68). */
export async function syncDerivedTasteFromSpotifyProfile(profile: SpotifyTasteProfile): Promise<void> {
  const taste = await deriveTasteProfile({
    spotify_profile: profile,
    taste_source: 'spotify',
  })
  await commitTasteQuizProfile(taste, 'intermediate')
}
