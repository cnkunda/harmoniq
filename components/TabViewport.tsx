import { forwardRef } from 'react'

import type { AlphaTabSurfaceRef } from '@/types/tabMessage'

import { AlphaTabWebView } from './AlphaTabWebView'
import type { TabViewportProps } from './TabViewport.types'

export type { TabViewportProps } from './TabViewport.types'

/** Native: bundled HTML harness in WebView (commit 21). */
export const TabViewport = forwardRef<AlphaTabSurfaceRef, TabViewportProps>(
  function TabViewport({ gp5Base64, audioSrc, transposeSemitones, style, onReady, onError, onNoteEvent }, ref) {
    return (
      <AlphaTabWebView
        ref={ref}
        gp5Base64={gp5Base64}
        audioSrc={audioSrc}
        transposeSemitones={transposeSemitones}
        style={style}
        onReady={onReady}
        onHarnessError={onError}
        onNoteEvent={onNoteEvent}
      />
    )
  },
)
