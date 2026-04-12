/**
 * Native (iOS/Android): DOM AlphaTab is not used — Study screen mounts `AlphaTabWebView` instead.
 * This stub keeps a stable import path and satisfies `forwardRef` when Metro resolves the non-web bundle.
 */
import { forwardRef, useImperativeHandle } from 'react'

import type { AlphaTabSurfaceRef } from '@/types/tabMessage'

import type { AlphaTabWebProps } from './AlphaTabWeb.types'

export type { AlphaTabWebProps } from './AlphaTabWeb.types'

export const AlphaTabWeb = forwardRef<AlphaTabSurfaceRef, AlphaTabWebProps>(
  function AlphaTabWeb(_props, ref) {
    useImperativeHandle(
      ref,
      () => ({
        setAudioSrc: () => {},
        setPlaybackRate: () => {},
        seekTo: () => {},
        syncPlaybackTimelineMs: () => {},
        getPosition: async () => null,
        setTheme: () => {},
        setTranspose: () => {},
        setLoopRegion: () => {},
        highlightScaleDegrees: () => {},
        clearScaleHighlight: () => {},
      }),
      [],
    )
    return null
  },
)
