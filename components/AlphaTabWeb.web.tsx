import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { Pressable, Text, View } from 'react-native'

import { TAB_HARNESS_THEME } from '@/src/constants/tabHarnessTheme'
import type { AlphaTabSurfaceRef, TabThemeColors } from '@/types/tabMessage'

import type { AlphaTabWebProps } from './AlphaTabWeb.types'

export type { AlphaTabWebProps } from './AlphaTabWeb.types'

/** Pinned — match `assets/alphatab-harness/index.html` (PRIORITIES 0.4). */
const SCRIPT_SRC =
  'https://cdn.jsdelivr.net/npm/@coderline/alphatab@1.3.1/dist/alphaTab.min.js'

type AlphaTabApiLike = {
  load: (buffer: ArrayBuffer) => void
  updateSettings: () => void
  settings: { display: { resources: Record<string, string | undefined> } }
  uiFacade: {
    getScrollContainer: () => HTMLElement
    scrollToY: (el: HTMLElement, y: number, duration: number) => void
  }
  boundsLookup: {
    isFinished: boolean
    findMasterBarByIndex: (i: number) => { visualBounds: { y: number } } | null
  } | null
  error: { on: (cb: (err: unknown) => void) => void }
  renderFinished: { on: (cb: () => void) => void }
  destroy?: () => void
}

function loadAlphaTabScript(): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve()

  const w = window as Window & { __harmoniqAlphaTabScript?: Promise<void> }
  if (w.__harmoniqAlphaTabScript) return w.__harmoniqAlphaTabScript

  const hasApi = () => {
    const g = globalThis as { alphaTab?: { AlphaTabApi: unknown } }
    return Boolean(g.alphaTab && typeof g.alphaTab.AlphaTabApi === 'function')
  }

  if (hasApi()) {
    w.__harmoniqAlphaTabScript = Promise.resolve()
    return w.__harmoniqAlphaTabScript
  }

  w.__harmoniqAlphaTabScript = new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${SCRIPT_SRC}"]`)
    if (existing) {
      if (hasApi()) {
        resolve()
        return
      }
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('AlphaTab script error')))
      return
    }
    const s = document.createElement('script')
    s.src = SCRIPT_SRC
    s.async = true
    s.onload = () => resolve()
    s.onerror = () => reject(new Error('AlphaTab script failed to load'))
    document.head.appendChild(s)
  })

  return w.__harmoniqAlphaTabScript
}

function preventUiHooks() {
  document.addEventListener(
    'contextmenu',
    (e) => {
      e.preventDefault()
    },
    { capture: true },
  )
  document.addEventListener(
    'click',
    (e) => {
      const t = e.target as HTMLElement | null
      if (!t?.closest) return
      const a = t.closest('a[href]')
      if (a && a.getAttribute('href') && a.getAttribute('href') !== '#') {
        e.preventDefault()
        e.stopPropagation()
      }
    },
    true,
  )
}

function mergeResources(theme?: Partial<TabThemeColors>): Record<string, string> {
  const out: Record<string, string> = {}
  const base = { ...TAB_HARNESS_THEME, ...theme }
  for (const [k, v] of Object.entries(base)) {
    if (v) out[k] = v
  }
  return out
}

export const AlphaTabWeb = forwardRef<AlphaTabSurfaceRef, AlphaTabWebProps>(
  function AlphaTabWeb({ gp5Base64, theme, style, onReady, onError }, ref) {
    const hostRef = useRef<HTMLDivElement | null>(null)
    const apiRef = useRef<AlphaTabApiLike | null>(null)
    const readyPostedRef = useRef(false)

    const [mounted, setMounted] = useState(false)
    const [engineReady, setEngineReady] = useState(false)
    const [bootError, setBootError] = useState<string | null>(null)
    const [engineError, setEngineError] = useState<string | null>(null)
    const [reloadKey, setReloadKey] = useState(0)

    const themeKey = useMemo(() => JSON.stringify(theme ?? {}), [theme])

    const scrollToBarIndex = useCallback((api: AlphaTabApiLike, barIndex: number) => {
      const lookup = api.boundsLookup
      if (!lookup?.isFinished) {
        const msg = 'scrollToBar: bounds not ready yet'
        setEngineError(msg)
        onError?.(msg)
        return
      }
      const mb = lookup.findMasterBarByIndex(barIndex)
      if (!mb) {
        const msg = `scrollToBar: unknown bar index ${barIndex}`
        setEngineError(msg)
        onError?.(msg)
        return
      }
      try {
        const scrollEl = api.uiFacade.getScrollContainer()
        const y = mb.visualBounds.y
        api.uiFacade.scrollToY(scrollEl, Math.max(0, y - 24), 200)
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'scrollToBar failed'
        setEngineError(msg)
        onError?.(msg)
      }
    }, [onError])

    const applyThemePartial = useCallback((api: AlphaTabApiLike, colors: Partial<TabThemeColors>) => {
      const res = api.settings.display.resources
      for (const [k, v] of Object.entries(colors)) {
        if (v) res[k] = v
      }
      api.updateSettings()
    }, [])

    useImperativeHandle(
      ref,
      () => ({
        scrollToBar: (barIndex: number) => {
          const api = apiRef.current
          if (api) scrollToBarIndex(api, barIndex)
        },
        setTheme: (colors: Partial<TabThemeColors>) => {
          const api = apiRef.current
          if (api) applyThemePartial(api, colors)
        },
      }),
      [applyThemePartial, scrollToBarIndex],
    )

    useEffect(() => {
      setMounted(true)
    }, [])

    useEffect(() => {
      if (!mounted || typeof window === 'undefined') return
      const el = hostRef.current
      if (!el) return

      let cancelled = false
      readyPostedRef.current = false
      setBootError(null)
      setEngineError(null)
      setEngineReady(false)

      const run = async () => {
        try {
          preventUiHooks()
          await loadAlphaTabScript()
          if (cancelled) return

          const g = globalThis as {
            alphaTab?: { AlphaTabApi: new (container: HTMLElement, options: unknown) => AlphaTabApiLike }
          }
          const AlphaTabApi = g.alphaTab?.AlphaTabApi
          if (!AlphaTabApi) {
            throw new Error('AlphaTab global missing after script load')
          }

          const resources = mergeResources(theme ?? {})
          const api = new AlphaTabApi(el, {
            display: {
              resources,
              scale: 1.1,
            },
            player: { enablePlayer: false },
          })
          if (cancelled) {
            api.destroy?.()
            return
          }
          apiRef.current = api

          api.error.on((err: unknown) => {
            const m =
              err && typeof err === 'object' && 'message' in err
                ? String((err as { message: unknown }).message)
                : String(err)
            const msg = m || 'AlphaTab error'
            setEngineError(msg)
            onError?.(msg)
          })

          api.renderFinished.on(() => {
            if (readyPostedRef.current) return
            readyPostedRef.current = true
            onReady?.()
          })

          setEngineReady(true)
        } catch (e) {
          if (!cancelled) {
            const msg = e instanceof Error ? e.message : 'AlphaTab init failed'
            setBootError(msg)
            onError?.(msg)
          }
        }
      }

      void run()

      return () => {
        cancelled = true
        setEngineReady(false)
        const api = apiRef.current
        apiRef.current = null
        readyPostedRef.current = false
        if (api?.destroy) {
          try {
            api.destroy()
          } catch {
            /* ignore */
          }
        }
        el.replaceChildren()
      }
    }, [mounted, onError, onReady, reloadKey, themeKey])

    useEffect(() => {
      if (!engineReady) return
      const api = apiRef.current
      if (!api) return
      const raw = gp5Base64?.trim()
      if (!raw) return
      try {
        const bytes = Uint8Array.from(atob(raw), (c) => c.charCodeAt(0))
        api.load(bytes.buffer)
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Invalid GP5 base64'
        setEngineError(msg)
        onError?.(msg)
      }
    }, [engineReady, gp5Base64, onError])

    const onRetry = useCallback(() => {
      setBootError(null)
      setEngineError(null)
      setReloadKey((k) => k + 1)
    }, [])

    return (
      <View
        className="min-h-[220px] flex-1 overflow-hidden rounded-xl border border-wood-600 bg-wood-900"
        style={style}
      >
        {(bootError || engineError) && (
          <View className="border-b border-wood-600 bg-wood-800 px-3 py-2">
            <Text className="font-sans text-xs text-amber-light">{bootError ?? engineError}</Text>
            <Pressable onPress={onRetry} className="mt-2 self-start" accessibilityRole="button">
              <Text className="font-sans-medium text-xs text-cream underline">Retry</Text>
            </Pressable>
          </View>
        )}
        {!mounted ? (
          <View className="min-h-[200px] items-center justify-center p-4">
            <Text className="font-sans text-sm text-muted-brown">Preparing AlphaTab…</Text>
          </View>
        ) : (
          <div
            key={reloadKey}
            ref={hostRef}
            style={{
              width: '100%',
              minHeight: 240,
              flex: 1,
              backgroundColor: '#2B1D0E',
              overflow: 'auto',
            }}
          />
        )}
        {!gp5Base64?.trim() && mounted ? (
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
