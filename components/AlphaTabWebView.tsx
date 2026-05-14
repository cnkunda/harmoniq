import { Asset } from 'expo-asset'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { ActivityIndicator, Platform, Pressable, Text, View, type StyleProp, type ViewStyle } from 'react-native'
import { WebView, type WebViewMessageEvent } from 'react-native-webview'

import { LoadingSkeleton } from '@/components/LoadingSkeleton'
import { persistLastSuccessfulSoundFontProfile } from '@/src/audio/soundfontPersistence'
import {
    DEFAULT_SOUNDFONT_PROFILE_ID,
    isSoundFontProfileId,
    type SoundFontProfileId,
} from '@/src/audio/soundfontProfiles'
import colors from '@/src/constants/colors'
import type { TabRenderPresetName } from '@/src/session/tabThemePresets'
import { DEFAULT_TAB_RENDER_PRESET } from '@/src/session/tabThemePresets'
import { useAlphaTabRuntimeDiagStore } from '@/src/stores/alphaTabRuntimeDiagStore'
import type {
    AlphaTabSurfaceRef,
    NoteEventMessage,
    SongScoreMeta,
    TabInboundMessage,
    TabLoopBarRegion,
    TabThemeColors,
} from '@/types/tabMessage'
import { decodeTabMessage, encodeTabMessage } from '@/types/tabMessage'

/** @deprecated Use `AlphaTabSurfaceRef` from `@/types/tabMessage`. */
export type AlphaTabWebViewRef = AlphaTabSurfaceRef

const HARNESS_HTML = require('../assets/alphatab-harness/index.html') as number

export type AlphaTabWebViewProps = {
  gp5Base64?: string | null
  /** Native harness does not consume server prerender JSON yet — prop exists for API parity with web. */
  prerenderArtifactUrl?: string | null
  audioSrc?: string | null
  transposeSemitones?: number
  /** Commit 60: AlphaTab synth bank (native harness mirrors web resolution). */
  soundFontProfile?: SoundFontProfileId
  renderPreset?: TabRenderPresetName
  style?: StyleProp<ViewStyle>
  onReady?: () => void
  onHarnessError?: (message: string) => void
  onNoteEvent?: (evt: NoteEventMessage) => void
  onScoreSeekMs?: (positionMs: number) => void
  readOnlyFollowMode?: boolean
  onSongDetails?: (score: SongScoreMeta) => void
  onSongPlayback?: (payload: { masterBarIndex: number; sectionLabel: string | null }) => void
  runtimeDiagnosticsEnabled?: boolean
}

function isAllowedNavigationUrl(url: string): boolean {
  if (url.startsWith('file:')) return true
  if (url === 'about:blank') return true
  try {
    const u = new URL(url)
    if (u.protocol === 'https:' && u.hostname === 'cdn.jsdelivr.net') return true
  } catch {
    return false
  }
  return false
}

export const AlphaTabWebView = forwardRef<AlphaTabSurfaceRef, AlphaTabWebViewProps>(
  function AlphaTabWebView(
    {
      gp5Base64,
      prerenderArtifactUrl: _prerenderArtifactUrl,
      audioSrc,
      transposeSemitones = 0,
      soundFontProfile = DEFAULT_SOUNDFONT_PROFILE_ID,
      renderPreset = DEFAULT_TAB_RENDER_PRESET,
      style,
      onReady,
      onHarnessError,
      onNoteEvent,
      onScoreSeekMs,
      readOnlyFollowMode = false,
      onSongDetails,
      onSongPlayback,
      runtimeDiagnosticsEnabled = false,
    },
    ref,
  ) {
    const webRef = useRef<WebView>(null)
    const getPositionResolverRef = useRef<((ms: number | null) => void) | null>(null)
    const songDetailsResolverRef = useRef<{
      requestId: string
      resolve: (v: SongScoreMeta | null) => void
    } | null>(null)
    // Optimistically track playback state for playPause toggle
    const isPlayingRef = useRef(false)

    const [reloadKey, setReloadKey] = useState(0)
    const [harnessUri, setHarnessUri] = useState<string | null>(null)
    const [assetError, setAssetError] = useState<string | null>(null)
    const [harnessError, setHarnessError] = useState<string | null>(null)
    const [harnessReady, setHarnessReady] = useState(false)
    const [soundFontReady, setSoundFontReady] = useState(false)

    const postInbound = useCallback((msg: TabInboundMessage) => {
      webRef.current?.postMessage(encodeTabMessage(msg))
    }, [])

    useImperativeHandle(
      ref,
      () => ({
        setAudioSrc: (nextAudioSrc: string) => {
          postInbound({ type: 'setAudioSrc', audioSrc: nextAudioSrc })
        },
        setMusicXml: (musicXml: string) => {
          postInbound({ type: 'setMusicXml', musicXml })
        },
        setPlaybackRate: (playbackRate: number) => {
          postInbound({ type: 'setPlaybackRate', playbackRate: Number.isFinite(playbackRate) ? playbackRate : 1 })
        },
        seekTo: (positionMs: number) => {
          postInbound({ type: 'seekTo', positionMs: Number.isFinite(positionMs) ? Math.max(0, positionMs) : 0 })
        },
        syncPlaybackTimelineMs: (positionMs: number) => {
          postInbound({
            type: 'syncTimelineMs',
            positionMs: Number.isFinite(positionMs) ? Math.max(0, positionMs + 50) : 0,
          })
        },
      setStemPlaybackActive: (active: boolean) => {
        isPlayingRef.current = Boolean(active)
        postInbound({ type: 'setStemPlaybackActive', active: Boolean(active) })
      },
      playPause: () => {
        isPlayingRef.current = !isPlayingRef.current
        postInbound({ type: 'setStemPlaybackActive', active: isPlayingRef.current })
      },
      getPosition: () =>
          new Promise<number | null>((resolve) => {
            getPositionResolverRef.current = resolve
            postInbound({ type: 'getPosition' })
            setTimeout(() => {
              if (getPositionResolverRef.current === resolve) {
                getPositionResolverRef.current = null
                resolve(null)
              }
            }, 800)
          }),
        setTheme: (nextColors: Partial<TabThemeColors>) => {
          postInbound({ type: 'setTheme', colors: nextColors })
        },
        setRenderPreset: (presetName: string) => {
          postInbound({ type: 'setRenderPreset', presetName })
        },
        setTranspose: (semitones: number) => {
          postInbound({ type: 'setTranspose', semitones: Math.max(-12, Math.min(12, Math.round(semitones))) })
        },
        setSoundFontProfile: (profileId: string) => {
          postInbound({
            type: 'setSoundFontProfile',
            profileId: isSoundFontProfileId(profileId) ? profileId : DEFAULT_SOUNDFONT_PROFILE_ID,
          })
        },
        setLoopRegion: (region: TabLoopBarRegion | null) => {
          if (!region) {
            postInbound({ type: 'clearLoopRegion' })
            return
          }
          postInbound({
            type: 'setLoopRegion',
            startBarIndex: Math.max(0, Math.floor(region.startBarIndex)),
            endBarIndexExclusive: Math.max(0, Math.floor(region.endBarIndexExclusive)),
          })
        },
        highlightScaleDegrees: (rootMidi: number, intervals: readonly number[]) => {
          const ints = [...intervals].map((n) => Math.round(n)).filter((n) => Number.isFinite(n))
          postInbound({
            type: 'highlightScaleDegrees',
            rootMidi: ((Math.round(rootMidi) % 12) + 12) % 12,
            intervals: ints,
          })
        },
        clearScaleHighlight: () => {
          postInbound({ type: 'clearScaleHighlight' })
        },
        scrollMasterBarIntoView: (barIndex: number) => {
          postInbound({
            type: 'scrollMasterBarIntoView',
            barIndex: Math.max(0, Math.floor(barIndex)),
          })
        },
        smartScrollSeekToBar: (positionSec: number, barTimestamps: number[]) => {
          postInbound({
            type: 'smartScrollSeekToBar',
            positionSec: Number.isFinite(positionSec) ? Math.max(0, positionSec) : 0,
            barTimestamps: Array.isArray(barTimestamps) ? barTimestamps : [],
          })
        },
        getSongDetails: () =>
          new Promise<SongScoreMeta | null>((resolve) => {
            const requestId = `sd_${Date.now()}_${Math.random().toString(36).slice(2)}`
            songDetailsResolverRef.current = { requestId, resolve }
            postInbound({ type: 'getSongDetails', requestId })
            setTimeout(() => {
              if (songDetailsResolverRef.current?.resolve === resolve) {
                songDetailsResolverRef.current = null
                resolve(null)
              }
            }, 800)
          }),
      }),
      [postInbound],
    )

    useEffect(() => {
      let cancelled = false
      ;(async () => {
        try {
          const asset = Asset.fromModule(HARNESS_HTML)
          await asset.downloadAsync()
          const uri = asset.localUri ?? asset.uri
          if (!cancelled) {
            setHarnessUri(uri ?? null)
            setAssetError(uri ? null : 'Harness asset has no local URI.')
          }
        } catch (e) {
          if (!cancelled) {
            setAssetError(e instanceof Error ? e.message : 'Failed to resolve harness asset.')
          }
        }
      })()
      return () => {
        cancelled = true
      }
    }, [])

    useEffect(() => {
      if (!harnessReady) return
      postInbound({
        type: 'setSoundFontProfile',
        profileId: soundFontProfile,
      })
      postInbound({ type: 'setRenderPreset', presetName: renderPreset })
      postInbound({ type: 'setTranspose', semitones: Math.max(-12, Math.min(12, Math.round(transposeSemitones))) })
      const raw = gp5Base64?.trim()
      if (raw) {
        postInbound({ type: 'setScore', gp5Base64: raw })
        const stemSrc = audioSrc?.trim()
        if (stemSrc) {
          // Score first, then wire external media source for cursor sync.
          setTimeout(() => {
            postInbound({ type: 'setAudioSrc', audioSrc: stemSrc })
          }, 0)
        }
      }
    }, [audioSrc, harnessReady, gp5Base64, postInbound, transposeSemitones, renderPreset, soundFontProfile])

    useEffect(() => {
      if (!harnessReady) return
      postInbound({ type: 'setReadOnlyFollowMode', enabled: readOnlyFollowMode })
    }, [harnessReady, postInbound, readOnlyFollowMode])

    useEffect(() => {
      if (!harnessReady) return
      postInbound({ type: 'setRuntimeDiagnosticsEnabled', enabled: runtimeDiagnosticsEnabled })
      return () => {
        postInbound({ type: 'setRuntimeDiagnosticsEnabled', enabled: false })
      }
    }, [harnessReady, runtimeDiagnosticsEnabled, postInbound])

    useEffect(() => {
      if (!harnessReady || !runtimeDiagnosticsEnabled) return
      const id = setInterval(() => {
        postInbound({
          type: 'diagPing',
          requestId: `dp_${Date.now()}_${Math.random().toString(36).slice(2)}`,
          t0: Date.now(),
        })
      }, 5000)
      return () => clearInterval(id)
    }, [harnessReady, runtimeDiagnosticsEnabled, postInbound])

    const onRetry = useCallback(() => {
      setHarnessReady(false)
      setSoundFontReady(false)
      setHarnessError(null)
      setAssetError(null)
      setReloadKey((k) => k + 1)
    }, [])

    const onMessage = useCallback(
      (e: WebViewMessageEvent) => {
        const msg = decodeTabMessage(e.nativeEvent.data)
        if (!msg) return
        if (msg.type === 'ready') {
          setHarnessReady(true)
          onReady?.()
          return
        }
        if (msg.type === 'position') {
          getPositionResolverRef.current?.(msg.positionMs)
          getPositionResolverRef.current = null
          return
        }
        if (msg.type === 'scoreSeek') {
          onScoreSeekMs?.(msg.positionMs)
          return
        }
        if (msg.type === 'noteEvent') {
          onNoteEvent?.(msg)
          return
        }
        if (msg.type === 'songDetails') {
          onSongDetails?.(msg.score)
          const pend = songDetailsResolverRef.current
          if (pend && msg.requestId === pend.requestId) {
            pend.resolve(msg.score)
            songDetailsResolverRef.current = null
          }
          return
        }
        if (msg.type === 'songPlayback') {
          onSongPlayback?.(msg)
          return
        }
        if (msg.type === 'runtimeDiagnostics') {
          useAlphaTabRuntimeDiagStore.getState().ingestHarnessWindow({
            windowMs: msg.windowMs,
            driftMs: msg.driftMs,
            noteEventHz: msg.noteEventHz,
            renderFps: msg.renderFps,
            breachFlags: msg.breachFlags ?? [],
            source: 'harness',
          })
          return
        }
        if (msg.type === 'diagPong') {
          useAlphaTabRuntimeDiagStore.getState().setBridgeLatencyMs(Date.now() - msg.t0)
          return
        }
        if (msg.type === 'smartScrollSeekResult') {
          // Log seek timing for diagnostics (optional)
          if (msg.estimatedSeekMs > 50) {
            console.warn('[AlphaTabWebView] SmartScroll seek exceeded 50ms:', msg.estimatedSeekMs)
          }
          return
        }
        if (msg.type === 'soundFontLoad') {
          const pid =
            typeof msg.profileId === 'string' && isSoundFontProfileId(msg.profileId)
              ? msg.profileId
              : DEFAULT_SOUNDFONT_PROFILE_ID
          if (msg.status === 'loaded') {
            setSoundFontReady(true)
            void persistLastSuccessfulSoundFontProfile(pid)
          }
          if (msg.status === 'error') {
            setSoundFontReady(true)
            if (msg.message) {
              setHarnessError(`SoundFont: ${msg.message}`)
            }
          }
          return
        }
        if (msg.type === 'error') {
          setHarnessError(msg.message)
          onHarnessError?.(msg.message)
        }
      },
      [onHarnessError, onNoteEvent, onReady, onScoreSeekMs, onSongDetails, onSongPlayback],
    )

    if (Platform.OS === 'web') {
      return (
        <View
          className="items-center justify-center rounded-xl border border-wood-600/45 bg-cream-dark/40 p-4"
          style={style}
        >
          <Text className="text-center font-sans text-sm text-muted-brown">
            AlphaTab runs in WebView on iOS/Android only. Web uses the DOM path (PRIORITIES §22).
          </Text>
        </View>
      )
    }

    if (assetError || !harnessUri) {
      return (
        <View
          className="min-h-[200px] items-center justify-center gap-3 rounded-xl border border-wood-600/45 bg-ivory p-4"
          style={style}
        >
          {assetError ? (
            <Text className="text-center font-sans text-sm text-danger">{assetError}</Text>
          ) : (
            <ActivityIndicator color={colors.amber.accent} />
          )}
          {assetError ? (
            <Pressable
              onPress={onRetry}
              className="rounded-lg border border-amber-accent/50 bg-amber-accent/90 px-4 py-2"
              accessibilityRole="button"
            >
              <Text className="font-sans-medium text-wood-900">Retry</Text>
            </Pressable>
          ) : null}
        </View>
      )
    }

    return (
      <View className="min-h-[220px] flex-1 overflow-hidden rounded-xl border border-wood-600/45 bg-ivory" style={style}>
        {harnessError ? (
          <View className="border-b border-amber-accent/30 bg-amber-accent/10 px-3 py-2">
            <Text className="font-sans text-xs text-wood-900">{harnessError}</Text>
            <Pressable onPress={onRetry} className="mt-2 self-start" accessibilityRole="button">
              <Text className="font-sans-medium text-xs text-amber-accent underline">Reload harness</Text>
            </Pressable>
          </View>
        ) : null}
        <WebView
          key={reloadKey}
          ref={webRef}
          source={{ uri: harnessUri }}
          onMessage={onMessage}
          onError={(ev) => {
            const desc = ev.nativeEvent.description || 'WebView load error'
            setAssetError(desc)
          }}
          onHttpError={(ev) => {
            setAssetError(`HTTP ${ev.nativeEvent.statusCode}`)
          }}
          originWhitelist={['*']}
          onShouldStartLoadWithRequest={(req) => isAllowedNavigationUrl(req.url)}
          javaScriptEnabled
          domStorageEnabled
          allowsInlineMediaPlayback
          allowFileAccess
          allowUniversalAccessFromFileURLs
          mixedContentMode="always"
          setSupportMultipleWindows={false}
          style={{ flex: 1, backgroundColor: '#2B1D0E' }}
        />
        {!soundFontReady ? (
          <View className="absolute left-3 right-3 top-3 rounded-lg border border-wood-600/45 bg-wood-800/70 p-3">
            <Text className="mb-2 font-sans text-[11px] text-cream">Loading instrument sounds…</Text>
            <LoadingSkeleton height={10} borderRadius={6} />
          </View>
        ) : null}
        {!gp5Base64?.trim() ? (
          <View
            className="absolute bottom-2 left-2 right-2 rounded-lg border border-wood-600/40 bg-ivory px-2 py-1.5"
            pointerEvents="none"
          >
            <Text className="text-center font-sans text-[11px] text-muted-brown">
              {
                "Tab preview isn't available for this song yet. Try analyzing a song or another tab variant."
              }
            </Text>
          </View>
        ) : null}
      </View>
    )
  },
)
