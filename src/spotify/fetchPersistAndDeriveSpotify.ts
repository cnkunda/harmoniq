import { fetchSpotifyTasteProfile } from '@/src/api/analyze'
import { setAppPref } from '@/src/db/client'
import { PREF_SPOTIFY_TASTE_PROFILE_JSON } from '@/src/db/schema'
import type { SpotifyTasteProfile } from '@/src/types'

import { syncDerivedTasteFromSpotifyProfile } from '@/src/spotify/syncDerivedTasteFromSpotify'

/** Fetch Spotify aggregates, save raw pref, derive unified taste + skill seed (same path as taste quiz). */
export async function fetchPersistAndDeriveSpotifyTaste(clientSession: string): Promise<SpotifyTasteProfile> {
  const profile = await fetchSpotifyTasteProfile(clientSession)
  await setAppPref(PREF_SPOTIFY_TASTE_PROFILE_JSON, JSON.stringify(profile))
  await syncDerivedTasteFromSpotifyProfile(profile)
  return profile
}
