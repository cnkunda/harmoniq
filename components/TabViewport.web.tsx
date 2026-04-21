import { forwardRef } from 'react'

import type { AlphaTabSurfaceRef } from '@/types/tabMessage'

import { AlphaTabWeb } from './AlphaTabWeb'
import type { TabViewportProps } from './TabViewport.types'

export type { TabViewportProps } from './TabViewport.types'

/** Web: DOM AlphaTab — no `react-native-webview` in this bundle graph (PRIORITIES §22). */
export const TabViewport = forwardRef<AlphaTabSurfaceRef, TabViewportProps>(
  function TabViewport(
    {
      gp5Base64,
      prerenderArtifactUrl,
      audioSrc,
      transposeSemitones,
      soundFontProfile,
      renderPreset,
      style,
      onReady,
      onError,
      onNoteEvent,
      onScoreSeekMs,
      onSongDetails,
      onSongPlayback,
      runtimeDiagnosticsEnabled,
    },
    ref,
  ) {
    return (
      <AlphaTabWeb
        ref={ref}
        gp5Base64={gp5Base64}
        prerenderArtifactUrl={prerenderArtifactUrl}
        audioSrc={audioSrc}
        transposeSemitones={transposeSemitones}
        soundFontProfile={soundFontProfile}
        renderPreset={renderPreset}
        runtimeDiagnosticsEnabled={runtimeDiagnosticsEnabled}
        style={style}
        onReady={onReady}
        onError={onError}
        onNoteEvent={onNoteEvent}
        onScoreSeekMs={onScoreSeekMs}
        onSongDetails={onSongDetails}
        onSongPlayback={onSongPlayback}
      />
    )
  },
)
