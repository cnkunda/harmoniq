import { ApiError, fetchSpotifyPlaybackState } from '@/src/api/analyze'
import type { SpotifyPlaybackStatePayload } from '@/src/types'
import type { AlphaTabSurfaceRef } from '@/types/tabMessage'

export type SpotifyPlaybackBridgeErrorCode =
  | 'disconnected'
  | 'premium_required'
  | 'inactive_playback'
  | 'unavailable'

export type SpotifyPlaybackBridgeError = {
  code: SpotifyPlaybackBridgeErrorCode
  message: string
}

export type SpotifyPlaybackBridgeOptions = {
  clientSession: string
  tab: AlphaTabSurfaceRef
  pollMs?: number
  onPlaybackState?: (state: SpotifyPlaybackStatePayload) => void
  onError?: (error: SpotifyPlaybackBridgeError | null) => void
}

const DEFAULT_POLL_MS = 900

export function isSpotifyPlaybackBridgeSkipped(): boolean {
  const env = typeof process !== 'undefined' ? process.env : undefined
  if (!env) return false
  return (
    env.EXPO_PUBLIC_HARMONIQ_SKIP_SPOTIFY_PLAYBACK === '1' ||
    env.HARMONIQ_SKIP_SPOTIFY_PLAYBACK === '1'
  )
}

function mapBridgeError(error: unknown): SpotifyPlaybackBridgeError {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return { code: 'disconnected', message: 'Spotify session expired. Reconnect Spotify in Settings.' }
    }
    if (error.status === 403) {
      return { code: 'premium_required', message: 'Spotify Premium is required for follow mode.' }
    }
    if (error.status === 409) {
      return {
        code: 'inactive_playback',
        message: 'Start playback in Spotify, then return to Harmoniq.',
      }
    }
  }
  const msg = error instanceof Error && error.message.trim() ? error.message.trim() : 'Spotify playback follow failed.'
  return { code: 'unavailable', message: msg }
}

export function createSpotifyPlaybackBridge(options: SpotifyPlaybackBridgeOptions): {
  start: () => void
  stop: () => void
} {
  const pollMs = Math.max(300, Math.floor(options.pollMs ?? DEFAULT_POLL_MS))
  const { clientSession, tab, onPlaybackState, onError } = options
  let running = false
  let timer: ReturnType<typeof setTimeout> | null = null
  let inFlight = false
  let lastProgressMs: number | null = null
  let lastPlaying: boolean | null = null
  let lastErrorKey: string | null = null

  const clearTimer = () => {
    if (timer != null) {
      clearTimeout(timer)
      timer = null
    }
  }

  const schedule = (delayMs: number) => {
    clearTimer()
    timer = setTimeout(() => {
      void tick()
    }, delayMs)
  }

  const seekIfNeeded = (progressMs: number) => {
    const drift = lastProgressMs == null ? Number.POSITIVE_INFINITY : Math.abs(progressMs - lastProgressMs)
    if (drift >= 1100) {
      tab.seekTo(progressMs)
    }
    tab.syncPlaybackTimelineMs(progressMs + 50)
    lastProgressMs = progressMs
  }

  const tick = async () => {
    if (!running || inFlight) return
    inFlight = true
    try {
      const state = await fetchSpotifyPlaybackState(clientSession)
      if (!running) return
      const playbackRate =
        Number.isFinite(state.playback_rate) && state.playback_rate > 0 ? state.playback_rate : 1
      tab.setPlaybackRate(playbackRate)
      seekIfNeeded(Math.max(0, Math.floor(state.progress_ms ?? 0)))
      if (lastPlaying !== state.is_playing) {
        lastPlaying = state.is_playing
        tab.setStemPlaybackActive(state.is_playing)
      }
      onPlaybackState?.(state)
      if (lastErrorKey !== null) {
        lastErrorKey = null
        onError?.(null)
      }
    } catch (error) {
      if (!running) return
      const mapped = mapBridgeError(error)
      const key = `${mapped.code}:${mapped.message}`
      if (key !== lastErrorKey) {
        lastErrorKey = key
        onError?.(mapped)
      }
      tab.setStemPlaybackActive(false)
    } finally {
      inFlight = false
      if (running) schedule(pollMs)
    }
  }

  return {
    start: () => {
      if (running) return
      running = true
      void tick()
    },
    stop: () => {
      running = false
      clearTimer()
      lastProgressMs = null
      lastPlaying = null
      tab.setStemPlaybackActive(false)
    },
  }
}
