/**
 * Cold-start taste quiz entry rules (PRIORITIES §69).
 */

import { parseTasteProfileJson } from '@/src/api/analyze'
import { getAppPref } from '@/src/db/client'
import { PREF_SPOTIFY_TASTE_PROFILE_JSON, PREF_TASTE_PROFILE_JSON } from '@/src/db/schema'

export function spotifyTasteLooksPresent(raw: string | null): boolean {
  if (!raw || !raw.trim()) return false
  try {
    const o = JSON.parse(raw) as unknown
    if (!o || typeof o !== 'object' || Array.isArray(o)) return false
    const rec = o as Record<string, unknown>
    const artists = rec.top_artists
    const genres = rec.top_genres
    const a = Array.isArray(artists) ? artists.filter((x) => typeof x === 'string' && x.trim()).length : 0
    const g = Array.isArray(genres) ? genres.filter((x) => typeof x === 'string' && x.trim()).length : 0
    return a + g > 0
  } catch {
    return false
  }
}

/** True when user has committed derived taste (quiz/derive) or raw Spotify aggregates worth skipping placement gate. */
export async function hasCommittedTasteOrSpotifyRaw(): Promise<boolean> {
  const [tasteRaw, spotRaw] = await Promise.all([
    getAppPref(PREF_TASTE_PROFILE_JSON),
    getAppPref(PREF_SPOTIFY_TASTE_PROFILE_JSON),
  ])
  return parseTasteProfileJson(tasteRaw) != null || spotifyTasteLooksPresent(spotRaw)
}

/** True when first-time onboarding should route through the taste quiz before mic placement. */
export async function shouldOfferTasteQuizOnboarding(): Promise<boolean> {
  const [tasteRaw, spotRaw] = await Promise.all([
    getAppPref(PREF_TASTE_PROFILE_JSON),
    getAppPref(PREF_SPOTIFY_TASTE_PROFILE_JSON),
  ])
  if (parseTasteProfileJson(tasteRaw) != null) return false
  if (spotifyTasteLooksPresent(spotRaw)) return false
  return true
}
