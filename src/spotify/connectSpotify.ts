import * as AuthSession from 'expo-auth-session'
import * as Linking from 'expo-linking'
import { Platform } from 'react-native'
import * as WebBrowser from 'expo-web-browser'

import { toast } from '@/components/ToastConfig'
import { initiateSpotifyAuth } from '@/src/api/analyze'
import { formatSpotifySetupError } from '@/src/spotify/spotifyConnectErrors'
import { API_BASE_URL } from '@/src/config'
import { getAppPref, setAppPref } from '@/src/db/client'
import { PREF_SPOTIFY_CLIENT_SESSION } from '@/src/db/schema'
import { fetchPersistAndDeriveSpotifyTaste } from '@/src/spotify/fetchPersistAndDeriveSpotify'
import type { SpotifyTasteProfile } from '@/src/types'

export async function ensureSpotifyClientSession(): Promise<string> {
  const existing = await getAppPref(PREF_SPOTIFY_CLIENT_SESSION)
  if (existing && existing.trim()) return existing.trim()
  const id =
    typeof globalThis.crypto !== 'undefined' && typeof globalThis.crypto.randomUUID === 'function'
      ? globalThis.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  await setAppPref(PREF_SPOTIFY_CLIENT_SESSION, id)
  return id
}

export type RunSpotifyConnectOptions = {
  onProfile?: (profile: SpotifyTasteProfile) => void
}

/**
 * Start Spotify OAuth (web redirect or native auth session), then fetch listening data and derive saved preferences.
 * Web returns early after navigation; completion runs when the app loads with Spotify return params (see Settings / entry).
 */
export async function runSpotifyConnect(options?: RunSpotifyConnectOptions): Promise<void> {
  const { onProfile } = options ?? {}
  try {
    const cs = await ensureSpotifyClientSession()
    if (Platform.OS === 'web') {
      if (typeof window === 'undefined') return
      const start = `${API_BASE_URL}/auth/spotify?client_session=${encodeURIComponent(cs)}&format=redirect&platform=web`
      window.location.assign(start)
      return
    }
    const redirectUrl = AuthSession.makeRedirectUri({ scheme: 'harmoniq', path: 'spotify-callback' })
    const authUrl = await initiateSpotifyAuth(cs, 'native')
    const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl)
    if (result.type !== 'success' || !result.url) {
      if (result.type === 'cancel' || result.type === 'dismiss') return
      toast.error('Spotify sign-in did not complete.')
      return
    }
    const parsed = Linking.parse(result.url)
    const q = parsed.queryParams ?? {}
    const rawResult = q.result
    const r = Array.isArray(rawResult) ? rawResult[0] : rawResult
    if (r === 'error') {
      toast.error('Spotify authorization was cancelled or failed.')
      return
    }
    if (r !== 'success') {
      toast.error('Unexpected Spotify callback.')
      return
    }
    try {
      const profile = await fetchPersistAndDeriveSpotifyTaste(cs)
      onProfile?.(profile)
      toast.success('Spotify connected.')
    } catch (e) {
      toast.error(formatSpotifySetupError(e))
    }
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Spotify connect failed')
  }
}
