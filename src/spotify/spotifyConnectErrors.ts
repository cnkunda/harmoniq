import { ApiError } from '@/src/api/analyze'

/** User-visible message when fetchPersistAndDeriveSpotifyTaste or OAuth completion fails. */
export function formatSpotifySetupError(e: unknown): string {
  if (e instanceof ApiError) {
    const m = (e.message || '').trim()
    if (e.status === 401 || m.toLowerCase().includes('not connected')) {
      return 'Spotify session was lost—usually the API restarted while you were signing in. Keep the backend running and tap Connect again.'
    }
    if (e.status === 503 && m.includes('Taste derivation disabled')) {
      return 'Taste derivation is turned off on the server (HARMONIQ_SKIP_TASTE_DERIVE). Disable it in backend/.env and restart the API.'
    }
    if (m) return m
    return `Request failed (${e.status}).`
  }
  if (e instanceof Error && e.message) {
    const low = e.message.toLowerCase()
    if (low.includes('failed to fetch') || low.includes('network request failed')) {
      return 'Cannot reach the Harmoniq API. Confirm the backend is running and EXPO_PUBLIC_API_URL matches it (try http://127.0.0.1:8000).'
    }
    return e.message
  }
  return 'Could not finish Spotify setup.'
}
