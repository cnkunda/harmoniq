import { Asset } from 'expo-asset'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { ActivityIndicator, Platform, Pressable, Text, View, type StyleProp, type ViewStyle } from 'react-native'
import { WebView, type WebViewMessageEvent } from 'react-native-webview'

import { LoadingSkeleton } from '@/components/LoadingSkeleton'
import colors from '@/src/constants/colors'
import { TAB_HARNESS_THEME } from '@/src/constants/tabHarnessTheme'
import type { AlphaTabSurfaceRef, NoteEventMessage, TabInboundMessage, TabThemeColors } from '@/types/tabMessage'
import { decodeTabMessage, encodeTabMessage } from '@/types/tabMessage'

/** @deprecated Use `AlphaTabSurfaceRef` from `@/types/tabMessage`. */
export type AlphaTabWebViewRef = AlphaTabSurfaceRef

const HARNESS_HTML = require('../assets/alphatab-harness/index.html') as number

export type AlphaTabWebViewProps = {
  gp5Base64?: string | null
  audioSrc?: string | null
  transposeSemitones?: number
  style?: StyleProp<ViewStyle>
  onReady?: () => void
  onHarnessError?: (message: string) => void
  onNoteEvent?: (evt: NoteEventMessage) => void
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
  function AlphaTabWebView({ gp5Base64, audioSrc, transposeSemitones = 0, style, onReady, onHarnessError, onNoteEvent }, ref) {
    const webRef = useRef<WebView>(null)
    const themeSentRef = useRef(false)
    const getPositionResolverRef = useRef<((ms: number | null) => void) | null>(null)

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
        setPlaybackRate: (playbackRate: number) => {
          postInbound({ type: 'setPlaybackRate', playbackRate: Number.isFinite(playbackRate) ? playbackRate : 1 })
        },
        seekTo: (positionMs: number) => {
          postInbound({ type: 'seekTo', positionMs: Number.isFinite(positionMs) ? Math.max(0, positionMs) : 0 })
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
        setTranspose: (semitones: number) => {
          postInbound({ type: 'setTranspose', semitones: Math.max(-12, Math.min(12, Math.round(semitones))) })
        },
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
      if (!themeSentRef.current) {
        themeSentRef.current = true
        postInbound({ type: 'setTheme', colors: TAB_HARNESS_THEME })
      }
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
    }, [audioSrc, harnessReady, gp5Base64, postInbound, transposeSemitones])

    const onRetry = useCallback(() => {
      themeSentRef.current = false
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
        if (msg.type === 'noteEvent') {
          onNoteEvent?.(msg)
          return
        }
        if (msg.type === 'soundFontLoad') {
          if (msg.status === 'loaded') setSoundFontReady(true)
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
      [onHarnessError, onNoteEvent, onReady],
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
            <Text className="mb-2 font-sans text-[11px] text-cream">Loading guitar soundfont…</Text>
            <LoadingSkeleton height={10} borderRadius={6} />
          </View>
        ) : null}
        {!gp5Base64?.trim() ? (
          <View
            className="absolute bottom-2 left-2 right-2 rounded-lg border border-wood-600/40 bg-ivory px-2 py-1.5"
            pointerEvents="none"
          >
            <Text className="text-center font-sans text-[11px] text-muted-brown">
              No GP5 for this view — analyze a song or switch tab variant.
            </Text>
          </View>
        ) : null}
      </View>
    )
  },
)
