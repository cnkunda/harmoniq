import { Audio } from 'expo-av'
import { useCallback, useEffect, useRef, useState } from 'react'

import { API_BASE_URL } from '@/src/config'

type OrientClipState = {
  url: string | null
  annotation: string | null
  usedPlaceholder: boolean
  placeholderReason: string | null
  isLoading: boolean
  error: string | null
  isPlaying: boolean
}

const EMPTY_STATE: OrientClipState = {
  url: null,
  annotation: null,
  usedPlaceholder: false,
  placeholderReason: null,
  isLoading: false,
  error: null,
  isPlaying: false,
}

/**
 * Module-level cache so repeated mounts on the same lesson don't re-hit the server.
 */
const cache = new Map<string, OrientClipState>()

/**
 * On-demand orient-clip hook (Commit 163 rewrite).
 *
 * Call `fetchOrientClip()` when the learner opens the `?` overlay.
 * The result is cached per `lessonId` so Study and Play share the same clip.
 */
export function useOrientClip(lessonId: string | undefined) {
  const [state, setState] = useState<OrientClipState>(() => (lessonId ? cache.get(lessonId) ?? EMPTY_STATE : EMPTY_STATE))
  const audioRef = useRef<Audio.Sound | null>(null)

  const fetchOrientClip = useCallback(async () => {
    if (!lessonId) return
    const cached = cache.get(lessonId)
    if (cached && !cached.error) {
      setState(cached)
      return
    }

    setState((prev) => ({ ...prev, isLoading: true, error: null }))

    try {
      const response = await fetch(`${API_BASE_URL}/session/orient-clip`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: lessonId }),
      })

      if (!response.ok) {
        throw new Error(`Failed to fetch orient clip: ${response.statusText}`)
      }

      const result = await response.json()
      const url = result.wav_path
        ? `${API_BASE_URL}/lesson-file?rel=${encodeURIComponent(result.wav_path)}`
        : null

      const next: OrientClipState = {
        url,
        annotation: result.annotation ?? null,
        usedPlaceholder: result.used_placeholder ?? false,
        placeholderReason: result.placeholder_reason ?? null,
        isLoading: false,
        error: null,
        isPlaying: false,
      }
      cache.set(lessonId, next)
      setState(next)
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to load orient clip'
      console.error('[useOrientClip]', message)
      setState((prev) => ({ ...prev, isLoading: false, error: message }))
    }
  }, [lessonId])

  const togglePlayback = useCallback(async () => {
    if (!state.url) return
    try {
      if (audioRef.current) {
        const status = await audioRef.current.getStatusAsync()
        if (status.isLoaded && status.isPlaying) {
          await audioRef.current.pauseAsync()
          setState((prev) => ({ ...prev, isPlaying: false }))
          return
        }
        await audioRef.current.playAsync()
        setState((prev) => ({ ...prev, isPlaying: true }))
        return
      }
      const { sound } = await Audio.Sound.createAsync({ uri: state.url }, { shouldPlay: true })
      audioRef.current = sound
      setState((prev) => ({ ...prev, isPlaying: true }))
      sound.setOnPlaybackStatusUpdate((status) => {
        if (status.isLoaded && status.didJustFinish) {
          setState((prev) => ({ ...prev, isPlaying: false }))
        }
      })
    } catch (e) {
      console.error('[useOrientClip] playback error', e)
      setState((prev) => ({ ...prev, isPlaying: false, error: 'Could not play orient clip' }))
    }
  }, [state.url])

  const stopPlayback = useCallback(async () => {
    if (audioRef.current) {
      await audioRef.current.stopAsync().catch(() => {})
      await audioRef.current.unloadAsync().catch(() => {})
      audioRef.current = null
    }
    setState((prev) => ({ ...prev, isPlaying: false }))
  }, [])

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.unloadAsync().catch(() => {})
        audioRef.current = null
      }
    }
  }, [])

  return { ...state, fetchOrientClip, togglePlayback, stopPlayback }
}
