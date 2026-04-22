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
        setMusicXml: () => {},
        setPlaybackRate: () => {},
        seekTo: () => {},
        syncPlaybackTimelineMs: () => {},
        setStemPlaybackActive: () => {},
        getPosition: async () => null,
        setTheme: () => {},
        setRenderPreset: () => {},
        setTranspose: () => {},
        setSoundFontProfile: () => {},
        setLoopRegion: () => {},
        highlightScaleDegrees: () => {},
        clearScaleHighlight: () => {},
        scrollMasterBarIntoView: () => {},
        getSongDetails: async () => null,
      }),
      [],
    )
    return null
  },
)
