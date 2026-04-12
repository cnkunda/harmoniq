import { useCallback, useEffect, useMemo, useRef } from 'react'
import { Platform } from 'react-native'

import { createBeatMetronome } from './createBeatMetronome'
import type { BeatMetronome, BeatMetronomeParams } from './beatMetronome.types'
import type { MetronomeSubdivision } from './metronomeShared'

export type UseMetronomeResult = {
  /** Web: call when stem mixer exposes its shared AudioContext (may be null before load). */
  bindAudioContext: (ctx: AudioContext | null) => void
  start: (params: Omit<BeatMetronomeParams, 'subdivision'> & Partial<Pick<BeatMetronomeParams, 'subdivision'>>) => void
  stop: () => void
  /** Updates default subdivision merged into subsequent `start` calls. */
  setSubdivision: (s: MetronomeSubdivision) => void
}

/**
 * Shared metronome controller for Listen / Slow / Play (PRIORITIES §50).
 */
export function useMetronome(): UseMetronomeResult {
  const ctxRef = useRef<AudioContext | null>(null)
  const backendRef = useRef<BeatMetronome | null>(null)
  const subdivRef = useRef<MetronomeSubdivision>(1)

  const ensureBackend = useCallback(() => {
    const ctx = Platform.OS === 'web' ? ctxRef.current : null
    backendRef.current?.stop()
    backendRef.current = createBeatMetronome(ctx)
  }, [])

  useEffect(() => {
    return () => {
      backendRef.current?.stop()
      backendRef.current = null
    }
  }, [])

  const bindAudioContext = useCallback(
    (ctx: AudioContext | null) => {
      ctxRef.current = ctx
      ensureBackend()
    },
    [ensureBackend],
  )

  const start = useCallback(
    (params: Omit<BeatMetronomeParams, 'subdivision'> & Partial<Pick<BeatMetronomeParams, 'subdivision'>>) => {
      if (!backendRef.current) ensureBackend()
      backendRef.current?.start({
        ...params,
        subdivision: params.subdivision ?? subdivRef.current,
      })
    },
    [ensureBackend],
  )

  const stop = useCallback(() => {
    backendRef.current?.stop()
  }, [])

  const setSubdivision = useCallback((s: MetronomeSubdivision) => {
    subdivRef.current = s
  }, [])

  return useMemo(
    () => ({
      bindAudioContext,
      start,
      stop,
      setSubdivision,
    }),
    [bindAudioContext, setSubdivision, start, stop],
  )
}
