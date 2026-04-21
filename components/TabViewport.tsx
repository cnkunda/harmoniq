import { forwardRef } from 'react'

import type { AlphaTabSurfaceRef } from '@/types/tabMessage'

import { AlphaTabWebView } from './AlphaTabWebView'
import type { TabViewportProps } from './TabViewport.types'

export type { TabViewportProps } from './TabViewport.types'

/** Native: bundled HTML harness in WebView (commit 21). */
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
      readOnlyFollowMode,
      onSongDetails,
      onSongPlayback,
      runtimeDiagnosticsEnabled,
    },
    ref,
  ) {
    return (
      <AlphaTabWebView
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
        onHarnessError={onError}
        onNoteEvent={onNoteEvent}
        onScoreSeekMs={onScoreSeekMs}
        readOnlyFollowMode={readOnlyFollowMode}
        onSongDetails={onSongDetails}
        onSongPlayback={onSongPlayback}
      />
    )
  },
)
