import { useEffect, useRef, type MutableRefObject, type RefObject } from 'react'

import type { AlphaTabSurfaceRef } from '@/types/tabMessage'

import {
  barIndexForPlaybackSeconds,
  decideSmartScroll,
  normalizeBarTimestamps,
  type SmartScrollSample,
} from './smartScroll'

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
 * While audio plays, maps `lesson.bar_timestamps` + mixer clock → `scrollToBar`.
 */
export function useSessionSmartScroll({
  tabRef,
  barTimestamps,
  tickRef,
  resetKey = 0,
  pollIntervalMs = 200,
  skewDemoGeneration = 0,
}: UseSessionSmartScrollOptions): void {
  const lastEmittedBar = useRef<number | null>(null)
  const lastSample = useRef<SmartScrollSample | null>(null)
  const tsRef = useRef<readonly number[]>([])
  const skewPhase = useRef<'idle' | 'wrong' | 'truth'>('idle')
  const lastSkewGen = useRef(0)

  useEffect(() => {
    tsRef.current = barTimestamps ?? []
  }, [barTimestamps])

  useEffect(() => {
    lastEmittedBar.current = null
    lastSample.current = null
    skewPhase.current = 'idle'
  }, [resetKey])

  useEffect(() => {
    if (skewDemoGeneration !== lastSkewGen.current && skewDemoGeneration > 0) {
      lastSkewGen.current = skewDemoGeneration
      skewPhase.current = 'wrong'
    }
  }, [skewDemoGeneration])

  useEffect(() => {
    const id = setInterval(() => {
      const ctx = tickRef.current
      if (!ctx.ready || !ctx.playing) return

      const ts = normalizeBarTimestamps(tsRef.current)
      if (ts.length === 0) return

      const tab = tabRef.current
      if (!tab) return

      if (skewPhase.current === 'wrong') {
        const wrongBar = barIndexForPlaybackSeconds(ts, ctx.positionSec + 0.18)
        tab.scrollToBar(wrongBar)
        skewPhase.current = 'truth'
        return
      }

      if (skewPhase.current === 'truth') {
        const truthBar = barIndexForPlaybackSeconds(ts, ctx.positionSec)
        tab.scrollToBar(truthBar)
        lastEmittedBar.current = truthBar
        lastSample.current = { wallTimeMs: Date.now(), playbackSeconds: ctx.positionSec }
        skewPhase.current = 'idle'
        return
      }

      const d = decideSmartScroll({
        barTimestamps: ts,
        playbackSeconds: ctx.positionSec,
        playbackRate: ctx.rate,
        lastEmittedBarIndex: lastEmittedBar.current,
        lastSample: lastSample.current,
      })

      if (d.shouldScroll) {
        tab.scrollToBar(d.barIndex)
        lastEmittedBar.current = d.barIndex
        lastSample.current = d.nextSample
      }
    }, pollIntervalMs)

    return () => clearInterval(id)
  }, [pollIntervalMs, tabRef, tickRef])
}
