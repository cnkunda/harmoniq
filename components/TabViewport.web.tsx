import { forwardRef } from 'react'

import { TAB_HARNESS_THEME } from '@/src/constants/tabHarnessTheme'
import type { AlphaTabSurfaceRef } from '@/types/tabMessage'

import { AlphaTabWeb } from './AlphaTabWeb'
import type { TabViewportProps } from './TabViewport.types'

export type { TabViewportProps } from './TabViewport.types'

/** Web: DOM AlphaTab — no `react-native-webview` in this bundle graph (PRIORITIES §22). */
export const TabViewport = forwardRef<AlphaTabSurfaceRef, TabViewportProps>(
  function TabViewport({ gp5Base64, transposeSemitones, style, onReady, onError }, ref) {
    return (
      <AlphaTabWeb
        ref={ref}
        gp5Base64={gp5Base64}
        transposeSemitones={transposeSemitones}
        theme={TAB_HARNESS_THEME}
        style={style}
        onReady={onReady}
        onError={onError}
      />
    )
  },
)
