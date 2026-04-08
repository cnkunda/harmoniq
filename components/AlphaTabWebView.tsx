import { Asset } from 'expo-asset'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { ActivityIndicator, Platform, Pressable, Text, View, type StyleProp, type ViewStyle } from 'react-native'
import { WebView, type WebViewMessageEvent } from 'react-native-webview'

import { TAB_HARNESS_THEME } from '@/src/constants/tabHarnessTheme'
import type { TabInboundMessage, TabThemeColors } from '@/types/tabMessage'
import { decodeTabMessage, encodeTabMessage } from '@/types/tabMessage'

const HARNESS_HTML = require('../assets/alphatab-harness/index.html') as number

export type AlphaTabWebViewProps = {
  gp5Base64?: string | null
  style?: StyleProp<ViewStyle>
  onReady?: () => void
  onHarnessError?: (message: string) => void
}

export type AlphaTabWebViewRef = {
  scrollToBar: (barIndex: number) => void
  setTheme: (colors: Partial<TabThemeColors>) => void
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

export const AlphaTabWebView = forwardRef<AlphaTabWebViewRef, AlphaTabWebViewProps>(
  function AlphaTabWebView({ gp5Base64, style, onReady, onHarnessError }, ref) {
    const webRef = useRef<WebView>(null)
    const themeSentRef = useRef(false)

    const [reloadKey, setReloadKey] = useState(0)
    const [harnessUri, setHarnessUri] = useState<string | null>(null)
    const [assetError, setAssetError] = useState<string | null>(null)
    const [harnessError, setHarnessError] = useState<string | null>(null)
    const [harnessReady, setHarnessReady] = useState(false)

    const postInbound = useCallback((msg: TabInboundMessage) => {
      webRef.current?.postMessage(encodeTabMessage(msg))
    }, [])

    useImperativeHandle(
      ref,
      () => ({
        scrollToBar: (barIndex: number) => {
          postInbound({ type: 'scrollToBar', barIndex })
        },
        setTheme: (colors: Partial<TabThemeColors>) => {
          postInbound({ type: 'setTheme', colors })
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
      const raw = gp5Base64?.trim()
      if (raw) {
        postInbound({ type: 'setScore', gp5Base64: raw })
      }
    }, [harnessReady, gp5Base64, postInbound])

    const onRetry = useCallback(() => {
      themeSentRef.current = false
      setHarnessReady(false)
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
        if (msg.type === 'error') {
          setHarnessError(msg.message)
          onHarnessError?.(msg.message)
        }
      },
      [onHarnessError, onReady],
    )

    if (Platform.OS === 'web') {
      return (
        <View
          className="items-center justify-center rounded-xl border border-wood-600 bg-wood-900 p-4"
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
          className="min-h-[200px] items-center justify-center gap-3 rounded-xl border border-wood-600 bg-wood-900 p-4"
          style={style}
        >
          {assetError ? (
            <Text className="text-center font-sans text-sm text-red-300">{assetError}</Text>
          ) : (
            <ActivityIndicator color="#D4860A" />
          )}
          {assetError ? (
            <Pressable
              onPress={onRetry}
              className="rounded-lg border border-amber-accent px-4 py-2"
              accessibilityRole="button"
            >
              <Text className="font-sans-medium text-amber-light">Retry</Text>
            </Pressable>
          ) : null}
        </View>
      )
    }

    return (
      <View className="min-h-[220px] flex-1 overflow-hidden rounded-xl border border-wood-600 bg-wood-900" style={style}>
        {harnessError ? (
          <View className="border-b border-wood-600 bg-wood-800 px-3 py-2">
            <Text className="font-sans text-xs text-amber-light">{harnessError}</Text>
            <Pressable onPress={onRetry} className="mt-2 self-start" accessibilityRole="button">
              <Text className="font-sans-medium text-xs text-cream underline">Reload harness</Text>
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
        {!gp5Base64?.trim() ? (
          <View
            className="absolute bottom-2 left-2 right-2 rounded-lg bg-wood-900/90 px-2 py-1.5"
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
