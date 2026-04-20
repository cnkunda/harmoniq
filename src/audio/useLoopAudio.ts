import type { RefObject } from 'react'
import { useEffect, useRef } from 'react'

import type { StemMixer } from '@/src/audio/mixerTypes'

/**
 * Stem loop boundary: seeks to `startSec` when position reaches `endSec`
 * (bar-aligned seconds from `bar_timestamps`). Uses `requestAnimationFrame` instead of coarse intervals.
 *
 * Prefers `getPositionSecondsNow` when implemented so wrap detection stays on the same clock as
 * playback (MANUAL_QA loop precision); falls back to async `getPositionSeconds` only when sync API is absent.
 */
export function useLoopAudio(deps: {
  active: boolean
  startSec: number
  endSec: number
  mixerRef: RefObject<StemMixer | null>
  onWrappedToLoopStart?: (startSec: number) => void
}): void {
  const { active, startSec, endSec, mixerRef, onWrappedToLoopStart } = deps
  const onWrapRef = useRef(onWrappedToLoopStart)
  onWrapRef.current = onWrappedToLoopStart

  useEffect(() => {
    if (!active) return
    if (!Number.isFinite(startSec) || !Number.isFinite(endSec) || endSec <= startSec + 0.05) return

    let cancelled = false
    let raf = 0
    let wrapping = false

    const tick = () => {
      if (cancelled) return
      raf = requestAnimationFrame(tick)
      if (wrapping) return
      const m = mixerRef.current
      if (!m) return

      const tryWrap = (p: number) => {
        if (cancelled || wrapping) return
        if (p >= endSec - 1e-4) {
          wrapping = true
          void m
            .seek(startSec)
            .then(() => {
              onWrapRef.current?.(startSec)
            })
            .catch(() => {
              /* seek failure is surfaced by mixer / UI elsewhere */
            })
            .finally(() => {
              wrapping = false
            })
        }
      }

      const pNow = m.getPositionSecondsNow?.()
      if (typeof pNow === 'number' && Number.isFinite(pNow)) {
        tryWrap(pNow)
        return
      }

      void m.getPositionSeconds().then((p) => {
        tryWrap(p)
      })
    }

    raf = requestAnimationFrame(tick)
    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
    }
  }, [active, endSec, mixerRef, startSec])
}
