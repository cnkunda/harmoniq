import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { Pressable, Text, View } from 'react-native'

import { LoadingSkeleton } from '@/components/LoadingSkeleton'
import { TAB_HARNESS_THEME } from '@/src/constants/tabHarnessTheme'
import { applyScaleDegreeHighlight, clearScaleDegreeHighlight } from '@/src/jam/alphaTabScaleHighlight'
import { base64ToUint8Array } from '@/src/utils/base64ToUint8Array'
import type { AlphaTabSurfaceRef, NoteEventMessage, TabLoopBarRegion, TabThemeColors } from '@/types/tabMessage'

import type { AlphaTabWebProps } from './AlphaTabWeb.types'

export type { AlphaTabWebProps } from './AlphaTabWeb.types'

/** Pinned — match `assets/alphatab-harness/index.html` (PRIORITIES 0.4). */
const ALPHATAB_PKG_VERSION = '1.6.1'
const SCRIPT_SRC = `https://cdn.jsdelivr.net/npm/@coderline/alphatab@${ALPHATAB_PKG_VERSION}/dist/alphaTab.min.js`
/** Same package/version as the script; avoids AlphaSynth/Tone init issues seen with remote GeneralUser.sf2. */
const SOUNDFONT_URL = `https://cdn.jsdelivr.net/npm/@coderline/alphatab@${ALPHATAB_PKG_VERSION}/dist/soundfont/sonivox.sf2`

type MasterBarBoundsLike = {
  visualBounds?: { x: number; y: number; w: number; h: number }
  realBounds?: { x: number; y: number; w: number; h: number }
}

type BoundsLookupLike = {
  findMasterBarByIndex?: (index: number) => MasterBarBoundsLike | null
}

type AlphaTabApiLike = {
  load: (buffer: ArrayBuffer) => void
  updateSettings: () => void
  settings: { display: { resources: Record<string, string | undefined> } }
  boundsLookup?: BoundsLookupLike | null
  renderer?: { boundsLookup?: BoundsLookupLike | null }
  score?: { masterBars?: unknown[] }
  player?: {
    output?: {
      updatePosition?: (positionMs: number) => void
    }
    midiEventsPlayed?: { on?: (cb: (evt: unknown) => void) => void }
  }
  midiEventsPlayed?: { on?: (cb: (evt: unknown) => void) => void }
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

function mergeResources(theme?: Partial<TabThemeColors>): Record<string, string> {
  const out: Record<string, string> = {}
  const base = { ...TAB_HARNESS_THEME, ...theme }
  for (const [k, v] of Object.entries(base)) {
    if (v) out[k] = v
  }
  return out
}

export const AlphaTabWeb = forwardRef<AlphaTabSurfaceRef, AlphaTabWebProps>(
  function AlphaTabWeb({ gp5Base64, audioSrc, transposeSemitones = 0, theme, style, onReady, onError, onNoteEvent }, ref) {
    const hostRef = useRef<HTMLDivElement | null>(null)
    const apiRef = useRef<AlphaTabApiLike | null>(null)
    const audioRef = useRef<HTMLAudioElement | null>(null)
    const syncTimerRef = useRef<number | null>(null)
    const readyPostedRef = useRef(false)
    const loopStateRef = useRef<TabLoopBarRegion | null>(null)
    const loopBracketRef = useRef<HTMLDivElement | null>(null)

    const [mounted, setMounted] = useState(false)
    const [engineReady, setEngineReady] = useState(false)
    const [bootError, setBootError] = useState<string | null>(null)
    const [engineError, setEngineError] = useState<string | null>(null)
    const [soundFontReady, setSoundFontReady] = useState(false)
    const [reloadKey, setReloadKey] = useState(0)
    const lastNotePostMsRef = useRef(0)
    const onNoteEventRef = useRef(onNoteEvent)
    onNoteEventRef.current = onNoteEvent

    const themeKey = useMemo(() => JSON.stringify(theme ?? {}), [theme])

    const applyThemePartial = useCallback((api: AlphaTabApiLike, colors: Partial<TabThemeColors>) => {
      const res = api.settings.display.resources
      for (const [k, v] of Object.entries(colors)) {
        if (v) res[k] = v
      }
      api.updateSettings()
    }, [])

    const applyTranspose = useCallback((api: AlphaTabApiLike, semitones: number) => {
      const value = Math.max(-12, Math.min(12, Math.round(semitones)))
      const settings = api.settings as unknown as { notation?: { transpositionPitches?: number[] } }
      if (!settings.notation) settings.notation = {}
      settings.notation.transpositionPitches = [value]
      api.updateSettings()
    }, [])

    const updatePositionFromAudio = useCallback(() => {
      const api = apiRef.current
      const audio = audioRef.current
      if (!api || !audio) return
      api.player?.output?.updatePosition?.(audio.currentTime * 1000)
    }, [])

    const emitNoteEvent = useCallback((evt: unknown) => {
      const onNote = onNoteEventRef.current
      if (!onNote) return
      if (Array.isArray(evt)) {
        for (const row of evt) emitNoteEvent(row)
        return
      }
      const now = Date.now()
      if (now - lastNotePostMsRef.current < 30) return
      const row = evt as {
        eventType?: unknown
        velocity?: unknown
        note?: unknown
        beat?: unknown
        fret?: unknown
        string?: unknown
        noteValue?: unknown
        noteNumber?: unknown
      }
      const velocity = typeof row.velocity === 'number' ? row.velocity : 1
      if (velocity <= 0) return
      const midi =
        typeof row.noteValue === 'number'
          ? row.noteValue
          : typeof row.noteNumber === 'number'
            ? row.noteNumber
            : typeof row.note === 'number'
              ? row.note
              : null
      if (midi == null) return
      const beat = typeof row.beat === 'number' ? row.beat : 0
      const fret = typeof row.fret === 'number' ? row.fret : undefined
      const str = typeof row.string === 'number' ? row.string : undefined
      const payload: NoteEventMessage = {
        type: 'noteEvent',
        midi,
        beat,
        fret,
        string: str,
        hasExplicitTabPosition: typeof fret === 'number' && typeof str === 'number' ? true : undefined,
      }
      lastNotePostMsRef.current = now
      onNote(payload)
    }, [])

    const layoutLoopBracket = useCallback(() => {
      const container = hostRef.current
      const api = apiRef.current
      if (!container || !api) return

      const st = loopStateRef.current
      let bracket = loopBracketRef.current
      if (!st || st.startBarIndex >= st.endBarIndexExclusive) {
        if (bracket) bracket.style.display = 'none'
        return
      }

      if (!bracket) {
        bracket = document.createElement('div')
        bracket.setAttribute('aria-hidden', 'true')
        bracket.style.cssText =
          'display:none;position:absolute;pointer-events:none;z-index:50;border:2px solid rgba(240,222,180,0.92);border-radius:6px;background:rgba(240,222,180,0.06);box-sizing:border-box;'
        container.appendChild(bracket)
        loopBracketRef.current = bracket
      }

      const lookup = api.boundsLookup ?? api.renderer?.boundsLookup
      const startIdx = st.startBarIndex
      const endEx = st.endBarIndexExclusive
      let minX = Infinity
      let minY = Infinity
      let maxX = -Infinity
      let maxY = -Infinity
      let any = false

      if (lookup?.findMasterBarByIndex) {
        for (let b = startIdx; b < endEx; b += 1) {
          const mb = lookup.findMasterBarByIndex(b)
          if (!mb) continue
          const vb = mb.visualBounds ?? mb.realBounds
          if (!vb || typeof vb.x !== 'number' || typeof vb.y !== 'number') continue
          const w = typeof vb.w === 'number' ? vb.w : 0
          const h = typeof vb.h === 'number' ? vb.h : 0
          any = true
          minX = Math.min(minX, vb.x)
          minY = Math.min(minY, vb.y)
          maxX = Math.max(maxX, vb.x + w)
          maxY = Math.max(maxY, vb.y + h)
        }
      }

      if (!any) {
        const total = api.score?.masterBars?.length ?? 0
        if (total <= 0) {
          bracket.style.display = 'none'
          return
        }
        const cw = container.clientWidth || 1
        const ch = container.clientHeight || 120
        const left = (startIdx / total) * cw
        const width = Math.max(8, ((endEx - startIdx) / total) * cw)
        bracket.style.left = `${left}px`
        bracket.style.top = '8px'
        bracket.style.width = `${width}px`
        bracket.style.height = `${Math.max(48, ch - 16)}px`
        bracket.style.display = 'block'
        return
      }

      const sl = container.scrollLeft || 0
      const stTop = container.scrollTop || 0
      bracket.style.left = `${minX - sl}px`
      bracket.style.top = `${minY - stTop}px`
      bracket.style.width = `${Math.max(4, maxX - minX)}px`
      bracket.style.height = `${Math.max(4, maxY - minY)}px`
      bracket.style.display = 'block'
    }, [])

    useImperativeHandle(
      ref,
      () => ({
        setAudioSrc: (nextAudioSrc: string) => {
          const audio = audioRef.current
          if (!audio) return
          audio.src = nextAudioSrc
          audio.load()
        },
        setPlaybackRate: (playbackRate: number) => {
          const audio = audioRef.current
          if (!audio) return
          audio.playbackRate = Number.isFinite(playbackRate) ? Math.max(0.5, Math.min(1.25, playbackRate)) : 1
        },
        seekTo: (positionMs: number) => {
          const audio = audioRef.current
          if (!audio) return
          audio.currentTime = Math.max(0, positionMs / 1000)
          updatePositionFromAudio()
        },
        syncPlaybackTimelineMs: (positionMs: number) => {
          const api = apiRef.current
          if (!api) return
          api.player?.output?.updatePosition?.(Math.max(0, positionMs))
        },
        getPosition: async () => {
          const audio = audioRef.current
          if (!audio) return null
          return audio.currentTime * 1000
        },
        setTheme: (colors: Partial<TabThemeColors>) => {
          const api = apiRef.current
          if (api) applyThemePartial(api, colors)
        },
        setTranspose: (semitones: number) => {
          const api = apiRef.current
          if (api) applyTranspose(api, semitones)
        },
        setLoopRegion: (region: TabLoopBarRegion | null) => {
          loopStateRef.current = region
          layoutLoopBracket()
        },
        highlightScaleDegrees: (rootMidi: number, intervals: readonly number[]) => {
          const api = apiRef.current
          const tabNs = (globalThis as { alphaTab?: unknown }).alphaTab
          applyScaleDegreeHighlight(api as Record<string, unknown>, tabNs as Record<string, unknown>, rootMidi, intervals)
        },
        clearScaleHighlight: () => {
          const api = apiRef.current
          clearScaleDegreeHighlight(api as Record<string, unknown>)
        },
      }),
      [applyThemePartial, applyTranspose, layoutLoopBracket, updatePositionFromAudio],
    )

    useEffect(() => {
      setMounted(true)
    }, [])

    useEffect(() => {
      if (!mounted || typeof window === 'undefined') return
      const el = hostRef.current
      if (!el) return

      /** Scope to host `el` only — document-level capture broke Expo Router `<a>` tab links after leaving session. */
      const uiGuard = new AbortController()
      const { signal } = uiGuard
      el.addEventListener(
        'contextmenu',
        (e) => {
          e.preventDefault()
        },
        { capture: true, signal },
      )
      el.addEventListener(
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
        { capture: true, signal },
      )
      el.addEventListener('scroll', layoutLoopBracket, { passive: true, signal })

      let cancelled = false
      readyPostedRef.current = false
      setBootError(null)
      setEngineError(null)
      setEngineReady(false)
      setSoundFontReady(false)

      const run = async () => {
        try {
          await loadAlphaTabScript()
          if (cancelled) return

          const tabNs = (globalThis as { alphaTab?: unknown }).alphaTab as
            | {
                AlphaTabApi: new (container: HTMLElement, options: unknown) => AlphaTabApiLike
                PlayerMode?: { EnabledExternalMedia?: unknown }
              }
            | undefined
          const AlphaTabApi = tabNs?.AlphaTabApi
          if (!AlphaTabApi) {
            throw new Error('AlphaTab global missing after script load')
          }
          const playerModeExternal = tabNs?.PlayerMode?.EnabledExternalMedia
          if (playerModeExternal === undefined) {
            throw new Error('AlphaTab PlayerMode.EnabledExternalMedia missing — check script version')
          }

          const resources = mergeResources(theme ?? {})
          // Expo web / Metro: worker script URL resolution breaks (Invalid base URL) — render on main thread.
          const apiOptions = {
            core: {
              useWorkers: false,
              scriptFile: SCRIPT_SRC,
              enableLazyLoading: false,
            },
            display: {
              resources,
              scale: 1.1,
            },
            soundFont: SOUNDFONT_URL,
            notation: {
              transpositionPitches: [Math.max(-12, Math.min(12, Math.round(transposeSemitones)))],
            },
            player: {
              enablePlayer: true,
              playerMode: playerModeExternal,
              soundFont: SOUNDFONT_URL,
            },
          }
          const api = new AlphaTabApi(el, apiOptions)
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

          const midiPlayed = api.player?.midiEventsPlayed ?? api.midiEventsPlayed
          if (midiPlayed && typeof midiPlayed.on === 'function') {
            midiPlayed.on((evt: unknown) => {
              emitNoteEvent(evt)
            })
          }

          api.renderFinished.on(() => {
            layoutLoopBracket()
            if (!readyPostedRef.current) {
              readyPostedRef.current = true
              onReady?.()
            }
          })

          setEngineReady(true)
          void fetch(SOUNDFONT_URL)
            .then((res) => {
              if (!res.ok) throw new Error(`HTTP ${res.status}`)
              return res.arrayBuffer()
            })
            .then(() => {
              if (!cancelled) setSoundFontReady(true)
            })
            .catch((err: unknown) => {
              if (!cancelled) {
                setSoundFontReady(true)
                const m = err instanceof Error ? err.message : 'SoundFont load failed'
                setEngineError((prev) => prev ?? `SoundFont: ${m}`)
              }
            })
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
        uiGuard.abort()
        setEngineReady(false)
        if (syncTimerRef.current != null) {
          window.clearInterval(syncTimerRef.current)
          syncTimerRef.current = null
        }
        const api = apiRef.current
        const audio = audioRef.current
        apiRef.current = null
        audioRef.current = null
        readyPostedRef.current = false
        if (audio) {
          try {
            audio.pause()
            audio.src = ''
          } catch {
            /* ignore */
          }
        }
        if (api?.destroy) {
          try {
            api.destroy()
          } catch {
            /* ignore */
          }
        }
        loopBracketRef.current = null
        loopStateRef.current = null
        el.replaceChildren()
      }
    }, [layoutLoopBracket, mounted, onError, onReady, reloadKey, themeKey, transposeSemitones])

    useEffect(() => {
      if (!engineReady) return
      const api = apiRef.current
      if (!api) return
      const raw = gp5Base64?.trim()
      if (!raw) return
      try {
        const bytes = base64ToUint8Array(raw)
        const buf = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
        api.load(buf)
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Invalid GP5 base64'
        setEngineError(msg)
        onError?.(msg)
      }
    }, [engineReady, gp5Base64, onError])

    useEffect(() => {
      if (!engineReady) return
      if (typeof window === 'undefined') return
      if (!audioRef.current) {
        audioRef.current = new Audio()
        audioRef.current.preload = 'auto'
        audioRef.current.crossOrigin = 'anonymous'
      }
      const audio = audioRef.current
      const nextSrc = audioSrc?.trim()
      if (nextSrc && audio.src !== nextSrc) {
        audio.src = nextSrc
        audio.load()
      }
      if (syncTimerRef.current != null) {
        window.clearInterval(syncTimerRef.current)
        syncTimerRef.current = null
      }
      // Stems use Web Audio / expo-av; hidden `<audio>` is not advanced during play. Cursor is driven by
      // `syncPlaybackTimelineMs` from the stem poll (Study, SessionStemAndTab) — no interval vs host sync.
      return () => {
        if (syncTimerRef.current != null) {
          window.clearInterval(syncTimerRef.current)
          syncTimerRef.current = null
        }
      }
    }, [audioSrc, engineReady, updatePositionFromAudio])

    useEffect(() => {
      if (!engineReady) return
      const api = apiRef.current
      if (!api) return
      applyTranspose(api, transposeSemitones)
    }, [applyTranspose, engineReady, transposeSemitones])

    const onRetry = useCallback(() => {
      setBootError(null)
      setEngineError(null)
      setReloadKey((k) => k + 1)
    }, [])

    return (
      <View
        className="min-h-[220px] flex-1 overflow-hidden rounded-xl border border-wood-600/45 bg-ivory"
        style={style}
      >
        {(bootError || engineError) && (
          <View className="border-b border-amber-accent/30 bg-amber-accent/10 px-3 py-2">
            <Text className="font-sans text-xs text-wood-900">{bootError ?? engineError}</Text>
            <Pressable onPress={onRetry} className="mt-2 self-start" accessibilityRole="button">
              <Text className="font-sans-medium text-xs text-amber-accent underline">Retry</Text>
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
              position: 'relative',
            }}
          />
        )}
        {mounted && !soundFontReady ? (
          <View className="absolute left-3 right-3 top-3 rounded-lg border border-wood-600/45 bg-wood-800/70 p-3">
            <Text className="mb-2 font-sans text-[11px] text-cream">Loading guitar soundfont…</Text>
            <LoadingSkeleton height={10} borderRadius={6} />
          </View>
        ) : null}
        {!gp5Base64?.trim() && mounted ? (
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
