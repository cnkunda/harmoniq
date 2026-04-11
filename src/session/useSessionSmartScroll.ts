import { useEffect, useRef, type MutableRefObject, type RefObject } from 'react'

import type { AlphaTabSurfaceRef } from '@/types/tabMessage'

import type { SmartScrollSample } from './smartScroll'

export type PlaybackTickContext = {
  positionSec: number
  playing: boolean
  rate: number
  ready: boolean
}

export type UseSessionSmartScrollOptions = {
  tabRef: RefObject<AlphaTabSurfaceRef | null>
  barTimestamps: readonly number[] | undefined | null
  /** Updated every tick by `ListenStemPanel` (or equivalent). */
  tickRef: MutableRefObject<PlaybackTickContext>
  /** Increment after seek / section jump to clear bar latch. */
  resetKey?: number
  pollIntervalMs?: number
  /** Increment (e.g. dev button) to run one wrong-bar scroll then correct (skew demo). */
  skewDemoGeneration?: number
}

/**
 * Deprecated in commit 45. AlphaTab external media sync now drives cursor internally.
 */
export function useSessionSmartScroll({
  tabRef: _tabRef,
  barTimestamps,
  tickRef: _tickRef,
  resetKey = 0,
  pollIntervalMs: _pollIntervalMs = 200,
  skewDemoGeneration = 0,
}: UseSessionSmartScrollOptions): void {
  const _lastEmittedBar = useRef<number | null>(null)
  const lastSample = useRef<SmartScrollSample | null>(null)
  const _tsRef = useRef<readonly number[]>([])
  const _skewPhase = useRef<'idle' | 'wrong' | 'truth'>('idle')
  const lastSkewGen = useRef(0)

  useEffect(() => {
    _tsRef.current = barTimestamps ?? []
  }, [barTimestamps])

  useEffect(() => {
    _lastEmittedBar.current = null
    lastSample.current = null
    _skewPhase.current = 'idle'
  }, [resetKey])

  useEffect(() => {
    if (skewDemoGeneration !== lastSkewGen.current && skewDemoGeneration > 0) {
      lastSkewGen.current = skewDemoGeneration
      _skewPhase.current = 'wrong'
    }
  }, [skewDemoGeneration])

  // External media mode keeps AlphaTab in sync with real audio timeline.
  // This hook intentionally does not schedule timers or post bar-scroll commands anymore.
  useEffect(() => {
    return () => {}
  }, [])
}
