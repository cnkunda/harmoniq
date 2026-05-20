/**
 * Onboarding song suggestion engine.
 *
 * Suggests 2 YouTube songs based on the user's taste profile.
 * Uses a hardcoded vibe → YouTube URL mapping as fallback,
 * and Spotify recommendations if the user has connected Spotify.
 */

import { getAppPref } from '@/src/db/client'
import { PREF_SPOTIFY_TASTE_PROFILE_JSON, PREF_TASTE_PROFILE_JSON } from '@/src/db/schema'
import type { TasteProfilePayload } from '@/src/types'
import { parseTasteProfileJson } from '@/src/api/analyze'

export type SongSuggestion = {
  title: string
  artist: string
  youtubeUrl: string
  vibe: string
}

/**
 * Hardcoded vibe → YouTube URL mapping.
 * Each vibe has 3 candidates; we pick 2.
 */
const VIBE_SONG_MAP: Record<string, SongSuggestion[]> = {
  blues: [
    {
      title: 'The Sky Is Crying',
      artist: 'Stevie Ray Vaughan',
      youtubeUrl: 'https://www.youtube.com/watch?v=6eebXuYXqJg',
      vibe: 'blues',
    },
    {
      title: 'Crossroads',
      artist: 'Eric Clapton',
      youtubeUrl: 'https://www.youtube.com/watch?v=2WgDnHh6v5c',
      vibe: 'blues',
    },
    {
      title: 'Pride and Joy',
      artist: 'Stevie Ray Vaughan',
      youtubeUrl: 'https://www.youtube.com/watch?v=Zw0rIy1vMjA',
      vibe: 'blues',
    },
  ],
  rock: [
    {
      title: 'Back in Black',
      artist: 'AC/DC',
      youtubeUrl: 'https://www.youtube.com/watch?v=pAgnJDJN4VA',
      vibe: 'rock',
    },
    {
      title: 'Smoke on the Water',
      artist: 'Deep Purple',
      youtubeUrl: 'https://www.youtube.com/watch?v=zUwkD8FOV3Y',
      vibe: 'rock',
    },
    {
      title: 'Sunshine of Your Love',
      artist: 'Cream',
      youtubeUrl: 'https://www.youtube.com/watch?v=wdkae35082E',
      vibe: 'rock',
    },
  ],
  fingerstyle: [
    {
      title: 'Classical Gas',
      artist: 'Tommy Emmanuel',
      youtubeUrl: 'https://www.youtube.com/watch?v=6ulI7K3erG8',
      vibe: 'fingerstyle',
    },
    {
      title: 'Dust in the Wind',
      artist: 'Kansas',
      youtubeUrl: 'https://www.youtube.com/watch?v=tH2wp6eDg1U',
      vibe: 'fingerstyle',
    },
    {
      title: 'Blackbird',
      artist: 'The Beatles',
      youtubeUrl: 'https://www.youtube.com/watch?v=Man4NTwUEP4',
      vibe: 'fingerstyle',
    },
  ],
  jazz: [
    {
      title: 'Take Five',
      artist: 'Dave Brubeck',
      youtubeUrl: 'https://www.youtube.com/watch?v=vmDDOFXSgAs',
      vibe: 'jazz',
    },
    {
      title: 'Autumn Leaves',
      artist: 'Wes Montgomery',
      youtubeUrl: 'https://www.youtube.com/watch?v=ZEcqHA7dbwM',
      vibe: 'jazz',
    },
    {
      title: 'Blue Bossa',
      artist: 'Joe Pass',
      youtubeUrl: 'https://www.youtube.com/watch?v=57cspLzKvCk',
      vibe: 'jazz',
    },
  ],
}

/**
 * Map style labels from the backend to vibe keys.
 */
const STYLE_TO_VIBE: Record<string, string> = {
  'blues': 'blues',
  'blues-rock': 'blues',
  'texas blues': 'blues',
  'chicago blues': 'blues',
  'rock': 'rock',
  'classic rock': 'rock',
  'hard rock': 'rock',
  'fingerstyle': 'fingerstyle',
  'acoustic': 'fingerstyle',
  'folk': 'fingerstyle',
  'jazz': 'jazz',
  'jazz guitar': 'jazz',
  'bebop': 'jazz',
  'smooth jazz': 'jazz',
}

/**
 * Get suggestions from the hardcoded vibe map.
 */
function getHardcodedSuggestions(vibe: string): SongSuggestion[] {
  const key = vibe.toLowerCase()
  const candidates = VIBE_SONG_MAP[key]
  if (!candidates || candidates.length === 0) {
    // Default to blues if vibe not recognized
    return VIBE_SONG_MAP.blues.slice(0, 2)
  }
  return candidates.slice(0, 2)
}

/**
 * Extracts the vibe from the Spotify taste profile and returns hardcoded suggestions.
 * Does not call the Spotify API. Returns null if Spotify is not connected.
 */
async function getSpotifyVibeSuggestions(): Promise<SongSuggestion[] | null> {
  try {
    const spotifyProfileJson = await getAppPref(PREF_SPOTIFY_TASTE_PROFILE_JSON)
    if (!spotifyProfileJson) return null

    const spotifyProfile = parseTasteProfileJson(spotifyProfileJson)
    if (!spotifyProfile || spotifyProfile.source !== 'spotify') return null

    const vibe = spotifyProfile.style_label.toLowerCase()
    return getHardcodedSuggestions(vibe)
  } catch {
    return null
  }
}

/**
 * Suggest 2 songs for the onboarding session based on taste profile.
 *
 * Priority:
 * 1. Spotify suggestions (if connected)
 * 2. Hardcoded vibe-based suggestions
 */
export async function suggestOnboardingSongs(
  tasteProfile: TasteProfilePayload | null,
): Promise<SongSuggestion[]> {
  // Try Spotify vibe first
  const spotifySuggestions = await getSpotifyVibeSuggestions()
  if (spotifySuggestions && spotifySuggestions.length > 0) {
    return spotifySuggestions
  }

  // Fall back to hardcoded based on taste profile
  if (tasteProfile) {
    const vibe = STYLE_TO_VIBE[tasteProfile.style_label.toLowerCase()] ?? 'blues'
    return getHardcodedSuggestions(vibe)
  }

  // Default fallback
  return getHardcodedSuggestions('blues')
}
