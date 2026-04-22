import { useEffect, useRef, type MutableRefObject, type RefObject } from 'react'

import type { AlphaTabSurfaceRef } from '@/types/tabMessage'

import { barIndexForPlaybackSeconds, PREDICTIVE_SCROLL_MS } from './smartScroll'

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
  /** When false (e.g. tab-only Jam), do not auto-scroll from stem ticks. */
  enabled?: boolean
}

/**
 * AlphaTab cursor follows external media via `syncPlaybackTimelineMs`, but horizontal
 * overflow still needs explicit scroll when the active bar leaves the viewport.
 */
export function useSessionSmartScroll({
  tabRef,
  barTimestamps,
  tickRef,
  resetKey = 0,
  pollIntervalMs = 100,
  enabled = true,
}: UseSessionSmartScrollOptions): void {
  const lastEmittedBar = useRef<number | null>(null)

  useEffect(() => {
    lastEmittedBar.current = null
  }, [resetKey])

  useEffect(() => {
    if (!enabled) return
    if (typeof setInterval === 'undefined') return
    const ts = barTimestamps ?? []
    const id = setInterval(() => {
      const tick = tickRef.current
      if (!tick.ready || !tick.playing || ts.length === 0) return
      const bar = barIndexForPlaybackSeconds(ts, tick.positionSec, PREDICTIVE_SCROLL_MS)
      if (lastEmittedBar.current === bar) return
      lastEmittedBar.current = bar
      tabRef.current?.scrollMasterBarIntoView(bar)
    }, pollIntervalMs)
    return () => clearInterval(id)
  }, [barTimestamps, enabled, pollIntervalMs, resetKey, tabRef, tickRef])
}
