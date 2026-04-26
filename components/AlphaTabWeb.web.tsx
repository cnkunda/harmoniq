import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { Pressable, Text, View } from 'react-native'

import { LoadingSkeleton } from '@/components/LoadingSkeleton'
import { resolveBundledSoundFontUrlForProfile } from '@/src/audio/soundfontBundled'
import { persistLastSuccessfulSoundFontProfile } from '@/src/audio/soundfontPersistence'
import {
  DEFAULT_SOUNDFONT_PROFILE_ID,
  isSoundFontProfileId,
  SOUNDFONT_PROFILE_LOAD_TIMEOUT_MS,
  type SoundFontProfileId,
} from '@/src/audio/soundfontProfiles'
import { ALPHA_TAB_NOTE_EVENT_MIN_INTERVAL_MS } from '@/src/constants/alphaTabBridge'
import { ALPHATAB_WEB_SURFACE_CSS } from '@/src/constants/alphaTabPlayerUi'
import { RUNTIME_DIAG_THRESHOLDS, RUNTIME_DIAG_WINDOW_MS } from '@/src/constants/alphaTabRuntimeDiag'
import { TAB_HARNESS_THEME } from '@/src/constants/tabHarnessTheme'
import { applyScaleDegreeHighlight, clearScaleDegreeHighlight } from '@/src/jam/alphaTabScaleHighlight'
import {
  extractSongMetaFromScore,
  resolveMasterBarIndexFromTick,
  sectionLabelAtMasterBar,
  type TickLookupApi,
} from '@/src/session/alphatabSongMeta'
import {
  DEFAULT_TAB_RENDER_PRESET,
  getTabRenderPreset,
  type TabRenderPreset,
} from '@/src/session/tabThemePresets'
import { useAlphaTabRuntimeDiagStore } from '@/src/stores/alphaTabRuntimeDiagStore'
import { base64ToUint8Array } from '@/src/utils/base64ToUint8Array'
import type { AlphaTabSurfaceRef, NoteEventMessage, SongScoreMeta, TabLoopBarRegion, TabThemeColors } from '@/types/tabMessage'

import type { AlphaTabWebProps } from './AlphaTabWeb.types'

export type { AlphaTabWebProps } from './AlphaTabWeb.types'

/** Pinned — match `assets/alphatab-harness/index.html` (PRIORITIES 0.4). */
const ALPHATAB_PKG_VERSION = '1.6.1'
const SCRIPT_SRC = `https://cdn.jsdelivr.net/npm/@coderline/alphatab@${ALPHATAB_PKG_VERSION}/dist/alphaTab.min.js`
type MasterBarBoundsLike = {
  visualBounds?: { x: number; y: number; w: number; h: number }
  realBounds?: { x: number; y: number; w: number; h: number }
}

type BoundsLookupLike = {
  findMasterBarByIndex?: (index: number) => MasterBarBoundsLike | null
}

type AlphaTabApiLike = {
  /** Must match stem `playbackRate` for follow-scroll / cursor timing (see alphaTab audio-video sync guide). */
  playbackSpeed?: number
  load: (buffer: ArrayBuffer) => void
  updateSettings: () => void
  score?: { masterBars?: unknown[] }
  tickCache?: { findBeat?: (tick: number) => unknown } | null
  tickPosition?: number
  play?: () => boolean | void
  pause?: () => void
  settings: {
    display: {
      resources: Record<string, string | undefined>
      scale?: number
      stretchForce?: number
    }
  }
  boundsLookup?: BoundsLookupLike | null
  renderer?: { boundsLookup?: BoundsLookupLike | null }
  player?: {
    setExternalMediaHandler?: (handler: unknown) => void
    output?: {
      updatePosition?: (positionMs: number) => void
      setExternalMediaHandler?: (handler: unknown) => void
    }
    midiEventsPlayed?: { on?: (cb: (evt: unknown) => void) => void }
  }
  midiEventsPlayed?: { on?: (cb: (evt: unknown) => void) => void }
  error: { on: (cb: (err: unknown) => void) => void }
  renderFinished: { on: (cb: () => void) => void }
  loadSoundFontFromUrl?: (url: string, append: boolean) => void
  soundFontLoaded?: { on?: (cb: () => void) => void }
  soundFontLoadFailed?: { on?: (cb: (e: unknown) => void) => void }
  destroy?: () => void
  /** Score playback timeline (ms) — used for drift samples vs stem sync (Commit 61). */
  timePosition?: number
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

function clampStemPlaybackRate(rate: number): number {
  if (!Number.isFinite(rate)) return 1
  return Math.max(0.25, Math.min(1.25, rate))
}

function applyStemPlaybackSpeed(api: AlphaTabApiLike, rate: number): void {
  const clamped = clampStemPlaybackRate(rate)
  try {
    api.playbackSpeed = clamped
  } catch {
    /* ignore */
  }
}

function mergeResources(...partials: (Partial<TabThemeColors> | undefined)[]): Record<string, string> {
  const base: TabThemeColors = { ...TAB_HARNESS_THEME }
  for (const p of partials) {
    if (!p) continue
    Object.assign(base, p)
  }
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(base)) {
    if (v) out[k] = v
  }
  return out
}

function applyRenderPresetToApi(
  api: AlphaTabApiLike,
  preset: TabRenderPreset,
  themeExtra?: Partial<TabThemeColors>,
): void {
  const res = api.settings.display.resources
  const mergedColors = { ...themeExtra, ...preset.colors }
  for (const [k, v] of Object.entries(mergedColors)) {
    if (v) res[k] = v
  }
  api.settings.display.scale = preset.scale
  api.settings.display.stretchForce = preset.stretchForce
  api.updateSettings()
}

function bytesToAsciiPreview(bytes: Uint8Array, limit = 96): string {
  let out = ''
  const n = Math.min(limit, bytes.length)
  for (let i = 0; i < n; i += 1) {
    const b = bytes[i] ?? 0
    out += b >= 32 && b <= 126 ? String.fromCharCode(b) : ' '
  }
  return out
}

function assertLikelyGpPayload(bytes: Uint8Array): void {
  if (bytes.byteLength < 24) {
    throw new Error(`GP payload too small (${bytes.byteLength} bytes)`)
  }
  const preview = bytesToAsciiPreview(bytes)
  if (!preview.includes('FICHIER GUITAR PRO')) {
    throw new Error('GP payload header mismatch (expected Guitar Pro signature)')
  }
}

export const AlphaTabWeb = forwardRef<AlphaTabSurfaceRef, AlphaTabWebProps>(
  function AlphaTabWeb(
    {
      gp5Base64,
      prerenderArtifactUrl,
      audioSrc,
      transposeSemitones = 0,
      soundFontProfile: soundFontProfileProp = DEFAULT_SOUNDFONT_PROFILE_ID,
      renderPreset = DEFAULT_TAB_RENDER_PRESET,
      theme,
      style,
      onReady,
      onError,
      onNoteEvent,
      onScoreSeekMs,
      readOnlyFollowMode = false,
      onSongDetails,
      onSongPlayback,
      runtimeDiagnosticsEnabled = false,
    },
    ref,
  ) {
    const hostRef = useRef<HTMLDivElement | null>(null)
    const apiRef = useRef<AlphaTabApiLike | null>(null)
    const audioRef = useRef<HTMLAudioElement | null>(null)
    const syncTimerRef = useRef<number | null>(null)
    const readyPostedRef = useRef(false)
    const loopStateRef = useRef<TabLoopBarRegion | null>(null)
    const loopBracketRef = useRef<HTMLDivElement | null>(null)
    /** Smooth horizontal scroll to target `scrollLeft` (SmartScroll bar follow). */
    const scrollSmoothRafRef = useRef<number | null>(null)
    const scrollTargetLeftRef = useRef<number | null>(null)

    const [mounted, setMounted] = useState(false)
    const [engineReady, setEngineReady] = useState(false)
    const [bootError, setBootError] = useState<string | null>(null)
    const [engineError, setEngineError] = useState<string | null>(null)
    const [soundFontReady, setSoundFontReady] = useState(false)
    const [reloadKey, setReloadKey] = useState(0)
    /** Server SVG overlay hidden after first client layout pass. */
    const [tabFullyPainted, setTabFullyPainted] = useState(false)
    const [prerenderMarkup, setPrerenderMarkup] = useState<string | null>(null)
    const lastNotePostMsRef = useRef(0)
    const pendingNoteRef = useRef<NoteEventMessage | null>(null)
    const noteFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
    /** Mirrors ListenStemPanel / mixer rate so AlphaTab scroll + cursor use the same speed factor. */
    const stemPlaybackRateRef = useRef(1)
    const onNoteEventRef = useRef(onNoteEvent)
    onNoteEventRef.current = onNoteEvent
    const onScoreSeekMsRef = useRef(onScoreSeekMs)
    onScoreSeekMsRef.current = onScoreSeekMs
    const readOnlyFollowModeRef = useRef(readOnlyFollowMode)
    readOnlyFollowModeRef.current = readOnlyFollowMode
    const appliedSoundFontProfileRef = useRef<SoundFontProfileId | null>(null)
    const activeSoundFontProfileRef = useRef<SoundFontProfileId>(DEFAULT_SOUNDFONT_PROFILE_ID)
    const webRuntimeDiagOnRef = useRef(false)
    const webDiagNoteRef = useRef(0)
    const webDiagRenderRef = useRef(0)
    const webDiagDriftSumRef = useRef(0)
    const webDiagDriftNRef = useRef(0)
    const webDiagIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

    const themeKey = useMemo(() => JSON.stringify(theme ?? {}), [theme])
    const soundFontProfileResolved: SoundFontProfileId = isSoundFontProfileId(soundFontProfileProp)
      ? soundFontProfileProp
      : DEFAULT_SOUNDFONT_PROFILE_ID

    const backgroundColor = useMemo(() => {
      return renderPreset === 'light' ? '#F5F0E8' : '#2B1D0E'
    }, [renderPreset])

    useEffect(() => {
      webRuntimeDiagOnRef.current = runtimeDiagnosticsEnabled
    }, [runtimeDiagnosticsEnabled])

    useEffect(() => {
      setTabFullyPainted(false)
    }, [gp5Base64, reloadKey])

    useEffect(() => {
      let cancelled = false
      const url = prerenderArtifactUrl?.trim()
      if (!url) {
        setPrerenderMarkup(null)
        return
      }
      void fetch(url)
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          return res.json() as Promise<{ partials?: Array<{ svg?: string }> }>
        })
        .then((data) => {
          const parts = data.partials ?? []
          const merged = parts.map((p) => p.svg ?? '').join('')
          if (!cancelled && merged.trim()) setPrerenderMarkup(merged)
          else if (!cancelled) setPrerenderMarkup(null)
        })
        .catch(() => {
          if (!cancelled) setPrerenderMarkup(null)
        })
      return () => {
        cancelled = true
      }
    }, [prerenderArtifactUrl])

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

    const flushPendingNoteEvent = useCallback(() => {
      noteFlushTimerRef.current = null
      const onNote = onNoteEventRef.current
      const p = pendingNoteRef.current
      pendingNoteRef.current = null
      if (!onNote || !p) return
      lastNotePostMsRef.current = Date.now()
      onNote(p)
      if (webRuntimeDiagOnRef.current) webDiagNoteRef.current += 1
    }, [])

    const emitNoteEvent = useCallback(
      (evt: unknown) => {
        const onNote = onNoteEventRef.current
        if (!onNote) return
        if (Array.isArray(evt)) {
          for (const row of evt) emitNoteEvent(row)
          return
        }
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

        const now = Date.now()
        const elapsed = now - lastNotePostMsRef.current
        if (elapsed < ALPHA_TAB_NOTE_EVENT_MIN_INTERVAL_MS) {
          pendingNoteRef.current = payload
          if (noteFlushTimerRef.current == null) {
            noteFlushTimerRef.current = setTimeout(
              flushPendingNoteEvent,
              Math.max(1, ALPHA_TAB_NOTE_EVENT_MIN_INTERVAL_MS - elapsed),
            )
          }
          return
        }
        if (noteFlushTimerRef.current != null) {
          clearTimeout(noteFlushTimerRef.current)
          noteFlushTimerRef.current = null
        }
        pendingNoteRef.current = null
        lastNotePostMsRef.current = now
        onNote(payload)
        if (webRuntimeDiagOnRef.current) webDiagNoteRef.current += 1
      },
      [flushPendingNoteEvent],
    )

    /** Score tap → fretboard (no midiEventsPlayed throttle — MANUAL_QA ~33 Hz cap applies to playback stream only). */
    const emitNoteTapFromScore = useCallback((clientX: number, clientY: number) => {
      const onNote = onNoteEventRef.current
      const api = apiRef.current
      const el = hostRef.current
      if (!onNote || !api || !el) return
      const rect = el.getBoundingClientRect()
      const x = clientX - rect.left + el.scrollLeft
      const y = clientY - rect.top + el.scrollTop
      const lookup = api.boundsLookup ?? api.renderer?.boundsLookup
      if (!lookup || typeof lookup !== 'object') return
      const lu = lookup as Record<string, unknown>
      const tryNames = ['getBeatAtPos', 'getBeatAtPosition', 'findBeatAt', 'getBeat'] as const
      for (const name of tryNames) {
        const fn = lu[name]
        if (typeof fn !== 'function') continue
        try {
          const res = (fn as (a: number, b: number) => unknown).call(lookup, x, y)
          if (!res || typeof res !== 'object') continue
          const beatObj = res as Record<string, unknown>
          const beatIdx =
            typeof beatObj.index === 'number'
              ? beatObj.index
              : typeof beatObj.globalBeatIndex === 'number'
                ? beatObj.globalBeatIndex
                : 0
          const notes = beatObj.notes
          if (!Array.isArray(notes) || notes.length === 0) continue
          const n0 = notes[0]
          if (!n0 || typeof n0 !== 'object') continue
          const row = n0 as Record<string, unknown>
          const midiRaw =
            typeof row.noteValue === 'number'
              ? row.noteValue
              : typeof row.noteNumber === 'number'
                ? row.noteNumber
                : typeof row.realValue === 'number'
                  ? row.realValue
                  : typeof row.midi === 'number'
                    ? row.midi
                : typeof row.note === 'number'
                  ? row.note
                  : null
          if (midiRaw == null) continue
          const midi = Math.round(midiRaw)
          const fret = typeof row.fret === 'number' ? row.fret : undefined
          const str = typeof row.string === 'number' ? row.string : undefined
          onNote({
            type: 'noteEvent',
            midi,
            beat: beatIdx,
            fret,
            string: str,
            hasExplicitTabPosition: typeof fret === 'number' && typeof str === 'number' ? true : undefined,
            fromScoreTap: true,
          })
          if (webRuntimeDiagOnRef.current) webDiagNoteRef.current += 1
          return
        } catch {
          /* try next API name */
        }
      }
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

    const scrollMasterBarIntoViewImpl = useCallback(
      (barIndex: number, attempt: number) => {
        const container = hostRef.current
        const api = apiRef.current
        if (!container || !api) return
        const idx = Math.max(0, Math.floor(barIndex))
        const lookup = api.boundsLookup ?? api.renderer?.boundsLookup
        const mb = lookup?.findMasterBarByIndex?.(idx)
        const vb = mb?.visualBounds ?? mb?.realBounds
        const cw = container.clientWidth || 0
        if (cw <= 0 && attempt < 6) {
          requestAnimationFrame(() => scrollMasterBarIntoViewImpl(barIndex, attempt + 1))
          return
        }
        const MAX_BOUNDS_ATTEMPTS = 18
        if (!vb || typeof vb.x !== 'number') {
          if (attempt < MAX_BOUNDS_ATTEMPTS) {
            requestAnimationFrame(() => scrollMasterBarIntoViewImpl(barIndex, attempt + 1))
          } else if (typeof __DEV__ !== 'undefined' && __DEV__) {
            console.warn(
              '[AlphaTabWeb] scrollMasterBarIntoView: no bounds for master bar',
              idx,
              'after',
              MAX_BOUNDS_ATTEMPTS,
              'attempts (excerpt vs global bar index?)',
            )
          }
          return
        }
        const w = typeof vb.w === 'number' ? vb.w : 0
        const barLeft = vb.x
        const barRight = vb.x + w
        const sl = container.scrollLeft
        const viewRight = sl + cw
        const margin = 32
        let next = sl
        if (barLeft < sl + margin) {
          next = Math.max(0, barLeft - margin)
        } else if (barRight > viewRight - margin) {
          const maxScroll = Math.max(0, container.scrollWidth - cw)
          next = Math.min(maxScroll, barRight - cw + margin)
        }
        if (Math.abs(next - sl) < 0.5) {
          layoutLoopBracket()
          return
        }
        scrollTargetLeftRef.current = next
        const stepScroll = () => {
          const target = scrollTargetLeftRef.current
          const host = hostRef.current
          if (target == null || !host) {
            scrollSmoothRafRef.current = null
            return
          }
          const cur = host.scrollLeft
          const delta = target - cur
          if (Math.abs(delta) < 0.75) {
            host.scrollLeft = target
            scrollSmoothRafRef.current = null
            layoutLoopBracket()
            return
          }
          const stepPx = Math.sign(delta) * Math.min(Math.abs(delta), Math.max(6, Math.abs(delta) * 0.18))
          host.scrollLeft = cur + stepPx
          layoutLoopBracket()
          scrollSmoothRafRef.current = requestAnimationFrame(stepScroll)
        }
        if (scrollSmoothRafRef.current == null) {
          scrollSmoothRafRef.current = requestAnimationFrame(stepScroll)
        }
      },
      [layoutLoopBracket],
    )

    const lastSongDetailsJsonRef = useRef('')
    const lastSongPlaybackBarRef = useRef(-1)
    const lastSongPlaybackLabelRef = useRef('\u0000')

    const onSongDetailsRef = useRef(onSongDetails)
    onSongDetailsRef.current = onSongDetails
    const onSongPlaybackRef = useRef(onSongPlayback)
    onSongPlaybackRef.current = onSongPlayback

    const resetSongMetaRefs = useCallback(() => {
      lastSongDetailsJsonRef.current = ''
      lastSongPlaybackBarRef.current = -1
      lastSongPlaybackLabelRef.current = '\u0000'
    }, [])

    const emitSongDetailsSnap = useCallback((opts?: { force?: boolean }) => {
      const api = apiRef.current as { score?: unknown } | null
      if (!api) return
      const meta = extractSongMetaFromScore(api.score ?? null)
      try {
        const js = JSON.stringify(meta)
        if (!opts?.force && js === lastSongDetailsJsonRef.current) return
        lastSongDetailsJsonRef.current = js
      } catch {
        /* ignore */
      }
      onSongDetailsRef.current?.(meta)
    }, [])

    const emitSongPlaybackMaybe = useCallback(() => {
      const api = apiRef.current as TickLookupApi & { score?: unknown }
      if (!api?.score) return
      const tick =
        typeof api.tickPosition === 'number' && Number.isFinite(api.tickPosition) ? api.tickPosition : 0
      let mbIdx = resolveMasterBarIndexFromTick(api, tick)
      if (mbIdx === null || mbIdx < 0) mbIdx = 0
      const label = sectionLabelAtMasterBar(api.score, mbIdx)
      const labStr = label ?? ''
      if (mbIdx === lastSongPlaybackBarRef.current && labStr === lastSongPlaybackLabelRef.current) return
      lastSongPlaybackBarRef.current = mbIdx
      lastSongPlaybackLabelRef.current = labStr
      onSongPlaybackRef.current?.({ masterBarIndex: mbIdx, sectionLabel: label })
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
        setMusicXml: (musicXml: string) => {
          const api = apiRef.current
          if (!api) return
          // Load MusicXML using AlphaTab's import API
          // Convert string to Uint8Array then to ArrayBuffer
          const encoder = new TextEncoder()
          const bytes = encoder.encode(musicXml)
          const buf = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
          resetSongMetaRefs()
          api.load(buf)
        },
        setPlaybackRate: (playbackRate: number) => {
          const c = clampStemPlaybackRate(Number.isFinite(playbackRate) ? playbackRate : 1)
          stemPlaybackRateRef.current = c
          const audio = audioRef.current
          if (audio) audio.playbackRate = c
          const apiNow = apiRef.current
          if (apiNow) applyStemPlaybackSpeed(apiNow, c)
        },
        seekTo: (positionMs: number) => {
          if (typeof window !== 'undefined' && scrollSmoothRafRef.current != null) {
            window.cancelAnimationFrame(scrollSmoothRafRef.current)
            scrollSmoothRafRef.current = null
          }
          scrollTargetLeftRef.current = null
          const ms = Math.max(0, Number.isFinite(positionMs) ? positionMs : 0)
          const audio = audioRef.current
          const api = apiRef.current
          const pr = stemPlaybackRateRef.current
          if (audio) audio.currentTime = (ms * pr) / 1000
          api?.player?.output?.updatePosition?.(ms)
          emitSongPlaybackMaybe()
          layoutLoopBracket()
        },
        scrollMasterBarIntoView: (barIndex: number) => {
          if (typeof window === 'undefined') {
            scrollMasterBarIntoViewImpl(barIndex, 0)
            return
          }
          requestAnimationFrame(() => scrollMasterBarIntoViewImpl(barIndex, 0))
        },
        smartScrollSeekToBar: (positionSec: number, barTimestamps: number[]) => {
          const t0 = performance.now()
          const clampedPos = Math.max(0, Number.isFinite(positionSec) ? positionSec : 0)
          const timestamps = Array.isArray(barTimestamps) ? barTimestamps : []
          
          // Binary search for bar index
          let barIndex = 0
          if (timestamps.length > 0) {
            let lo = 0
            let hi = timestamps.length - 1
            while (lo < hi) {
              const mid = Math.ceil((lo + hi) / 2)
              if (timestamps[mid]! <= clampedPos) lo = mid
              else hi = mid - 1
            }
            barIndex = lo
          }
          
          const barTimestampSec = timestamps[barIndex] ?? 0
          const seekMs = performance.now() - t0
          
          // Log if seek exceeds 50ms threshold
          if (seekMs > 50) {
            console.warn('[AlphaTabWeb] SmartScroll seek exceeded 50ms:', seekMs)
          }
          
          // Seek to the bar timestamp
          const ms = barTimestampSec * 1000
          const audio = audioRef.current
          const api = apiRef.current
          const pr = stemPlaybackRateRef.current
          if (audio) audio.currentTime = (ms * pr) / 1000
          api?.player?.output?.updatePosition?.(ms)
          emitSongPlaybackMaybe()
          layoutLoopBracket()
        },
        syncPlaybackTimelineMs: (positionMs: number) => {
          const api = apiRef.current
          if (!api) return
          const syncMs = Math.max(0, positionMs)
          api.player?.output?.updatePosition?.(syncMs)
          if (webRuntimeDiagOnRef.current) {
            const tp = api.timePosition
            if (typeof tp === 'number' && Number.isFinite(tp)) {
              webDiagDriftSumRef.current += Math.abs(syncMs - tp)
              webDiagDriftNRef.current += 1
            }
          }
          emitSongPlaybackMaybe()
        },
        setStemPlaybackActive: (active: boolean) => {
          const api = apiRef.current
          if (!api) return
          try {
            if (active) api.play?.()
            else api.pause?.()
          } catch {
            /* ignore */
          }
        },
        getPosition: async () => {
          const audio = audioRef.current
          if (!audio) return null
          const pr =
            Number.isFinite(audio.playbackRate) && audio.playbackRate > 0
              ? audio.playbackRate
              : stemPlaybackRateRef.current
          const safePr = Math.max(0.25, Math.min(1.25, pr))
          return (audio.currentTime / safePr) * 1000
        },
        setTheme: (colors: Partial<TabThemeColors>) => {
          const api = apiRef.current
          if (api) applyThemePartial(api, colors)
        },
        setRenderPreset: (presetName: string) => {
          const api = apiRef.current
          if (!api) return
          applyRenderPresetToApi(api, getTabRenderPreset(presetName), theme)
        },
        setTranspose: (semitones: number) => {
          const api = apiRef.current
          if (api) applyTranspose(api, semitones)
        },
        setSoundFontProfile: (profileId: string) => {
          const apiNow = apiRef.current
          if (!apiNow?.loadSoundFontFromUrl) return
          const id: SoundFontProfileId = isSoundFontProfileId(profileId) ? profileId : DEFAULT_SOUNDFONT_PROFILE_ID
          appliedSoundFontProfileRef.current = id
          activeSoundFontProfileRef.current = id
          setSoundFontReady(false)
          void resolveBundledSoundFontUrlForProfile(id)
            .then((url) => {
              apiNow.loadSoundFontFromUrl?.(url, false)
            })
            .catch(() => {
              void resolveBundledSoundFontUrlForProfile(DEFAULT_SOUNDFONT_PROFILE_ID).then((fallbackUrl) => {
                appliedSoundFontProfileRef.current = DEFAULT_SOUNDFONT_PROFILE_ID
                activeSoundFontProfileRef.current = DEFAULT_SOUNDFONT_PROFILE_ID
                apiNow.loadSoundFontFromUrl?.(fallbackUrl, false)
              })
            })
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
        getSongDetails: async (): Promise<SongScoreMeta | null> => {
          const api = apiRef.current as { score?: unknown } | null
          if (!api?.score) return null
          return extractSongMetaFromScore(api.score)
        },
      }),
      [
        applyThemePartial,
        applyTranspose,
        emitSongPlaybackMaybe,
        layoutLoopBracket,
        scrollMasterBarIntoViewImpl,
        theme,
      ],
    )

    useEffect(() => {
      if (!engineReady || typeof window === 'undefined') return
      const api = apiRef.current
      if (!api?.loadSoundFontFromUrl) return
      if (appliedSoundFontProfileRef.current === soundFontProfileResolved) return

      appliedSoundFontProfileRef.current = soundFontProfileResolved
      activeSoundFontProfileRef.current = soundFontProfileResolved

      let cancelledLocal = false
      const tid = window.setTimeout(() => {
        if (cancelledLocal || soundFontProfileResolved === DEFAULT_SOUNDFONT_PROFILE_ID) return
        void resolveBundledSoundFontUrlForProfile(DEFAULT_SOUNDFONT_PROFILE_ID).then((fallbackUrl) => {
          if (cancelledLocal || !apiRef.current?.loadSoundFontFromUrl) return
          appliedSoundFontProfileRef.current = DEFAULT_SOUNDFONT_PROFILE_ID
          activeSoundFontProfileRef.current = DEFAULT_SOUNDFONT_PROFILE_ID
          apiRef.current.loadSoundFontFromUrl(fallbackUrl, false)
          setEngineError((prev) => prev ?? 'SoundFont: switched to general_user (timeout)')
        })
      }, SOUNDFONT_PROFILE_LOAD_TIMEOUT_MS)

      setSoundFontReady(false)
      void resolveBundledSoundFontUrlForProfile(soundFontProfileResolved)
        .then((url) => {
          const a = apiRef.current
          if (cancelledLocal || !a?.loadSoundFontFromUrl) return
          a.loadSoundFontFromUrl(url, false)
        })
        .catch(() => {
          void resolveBundledSoundFontUrlForProfile(DEFAULT_SOUNDFONT_PROFILE_ID).then((fallbackUrl) => {
            if (cancelledLocal || !apiRef.current?.loadSoundFontFromUrl) return
            appliedSoundFontProfileRef.current = DEFAULT_SOUNDFONT_PROFILE_ID
            activeSoundFontProfileRef.current = DEFAULT_SOUNDFONT_PROFILE_ID
            apiRef.current.loadSoundFontFromUrl(fallbackUrl, false)
            setEngineError((prev) => prev ?? 'SoundFont: switched to general_user')
          })
        })

      return () => {
        cancelledLocal = true
        window.clearTimeout(tid)
      }
    }, [engineReady, soundFontProfileResolved])

    useEffect(() => {
      if (!engineReady || typeof window === 'undefined') return
      if (!runtimeDiagnosticsEnabled) {
        if (webDiagIntervalRef.current != null) {
          clearInterval(webDiagIntervalRef.current)
          webDiagIntervalRef.current = null
        }
        return
      }
      const w = RUNTIME_DIAG_WINDOW_MS
      webDiagIntervalRef.current = window.setInterval(() => {
        const sec = w / 1000
        const hz = webDiagNoteRef.current / sec
        const rps = webDiagRenderRef.current / sec
        const n = webDiagDriftNRef.current
        const drift = n > 0 ? webDiagDriftSumRef.current / n : null
        const breachFlags: string[] = []
        if (drift != null && drift > RUNTIME_DIAG_THRESHOLDS.driftMsFail) breachFlags.push('DRIFT_MS')
        if (hz > RUNTIME_DIAG_THRESHOLDS.noteEventHzFail) breachFlags.push('NOTE_EVENT_HZ')
        if (rps > RUNTIME_DIAG_THRESHOLDS.renderFpsFail) breachFlags.push('RENDER_CHURN')
        useAlphaTabRuntimeDiagStore.getState().ingestHarnessWindow({
          windowMs: w,
          driftMs: drift,
          noteEventHz: hz,
          renderFps: rps,
          breachFlags,
          source: 'web-dom',
        })
        webDiagNoteRef.current = 0
        webDiagRenderRef.current = 0
        webDiagDriftSumRef.current = 0
        webDiagDriftNRef.current = 0
      }, w)
      return () => {
        if (webDiagIntervalRef.current != null) {
          clearInterval(webDiagIntervalRef.current)
          webDiagIntervalRef.current = null
        }
      }
    }, [engineReady, runtimeDiagnosticsEnabled])

    useEffect(() => {
      if (!engineReady) return
      const api = apiRef.current
      if (!api) return
      applyRenderPresetToApi(api, getTabRenderPreset(renderPreset), theme)
    }, [engineReady, renderPreset, themeKey])

    useEffect(() => {
      setMounted(true)
      if (typeof document !== 'undefined') {
        const id = 'harmoniq-alphatab-player-cursor'
        const existing = document.getElementById(id)
        if (existing) {
          existing.textContent = ALPHATAB_WEB_SURFACE_CSS
        } else {
          const el = document.createElement('style')
          el.id = id
          el.textContent = ALPHATAB_WEB_SURFACE_CSS
          document.head.appendChild(el)
        }
      }
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
      el.addEventListener(
        'pointerdown',
        (e: PointerEvent) => {
          if (readOnlyFollowModeRef.current) return
          if (e.button !== 0) return
          emitNoteTapFromScore(e.clientX, e.clientY)
        },
        { signal },
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
                LayoutMode?: { Horizontal?: number }
                ScrollMode?: { OffScreen?: number }
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
          const layoutHorizontal = tabNs?.LayoutMode?.Horizontal ?? 1
          const scrollFollow = tabNs?.ScrollMode?.OffScreen ?? 2

          const soundFontUrl = await resolveBundledSoundFontUrlForProfile(soundFontProfileResolved)
          if (cancelled) return

          const preset = getTabRenderPreset(renderPreset)
          const resources = mergeResources(theme, preset.colors)
          // Expo web / Metro: worker script URL resolution breaks (Invalid base URL) — render on main thread.
          const apiOptions = {
            core: {
              useWorkers: false,
              scriptFile: SCRIPT_SRC,
              enableLazyLoading: false,
            },
            display: {
              resources,
              scale: preset.scale,
              layoutMode: layoutHorizontal,
              stretchForce: preset.stretchForce,
            },
            soundFont: soundFontUrl,
            notation: {
              transpositionPitches: [Math.max(-12, Math.min(12, Math.round(transposeSemitones)))],
            },
            player: {
              enablePlayer: true,
              enableCursor: true,
              enableElementHighlighting: true,
              playerMode: playerModeExternal,
              soundFont: soundFontUrl,
              scrollMode: scrollFollow,
              // Native smooth scroll ignores `scrollSpeed` and stays ~wall-clock — desyncs at 65% stem rate.
              nativeBrowserSmoothScroll: false,
              scrollSpeed: 0,
              // https://alphatab.net/docs/reference/settings/player/scrollelement — default html/body cannot scroll here.
              scrollElement: el,
            },
          }
          const api = new AlphaTabApi(el, apiOptions)
          if (cancelled) {
            api.destroy?.()
            return
          }
          apiRef.current = api

          activeSoundFontProfileRef.current = soundFontProfileResolved
          appliedSoundFontProfileRef.current = soundFontProfileResolved
          api.soundFontLoaded?.on?.(() => {
            if (cancelled) return
            setSoundFontReady(true)
            void persistLastSuccessfulSoundFontProfile(activeSoundFontProfileRef.current)
          })
          api.soundFontLoadFailed?.on?.((sfErr: unknown) => {
            if (cancelled) return
            const m =
              sfErr && typeof sfErr === 'object' && 'message' in sfErr
                ? String((sfErr as { message: unknown }).message)
                : String(sfErr)
            setEngineError((prev) => prev ?? `SoundFont: ${m || 'load failed'}`)
            if (soundFontProfileResolved !== DEFAULT_SOUNDFONT_PROFILE_ID) {
              void resolveBundledSoundFontUrlForProfile(DEFAULT_SOUNDFONT_PROFILE_ID).then((fallbackUrl) => {
                if (cancelled || !apiRef.current?.loadSoundFontFromUrl) return
                activeSoundFontProfileRef.current = DEFAULT_SOUNDFONT_PROFILE_ID
                appliedSoundFontProfileRef.current = DEFAULT_SOUNDFONT_PROFILE_ID
                apiRef.current.loadSoundFontFromUrl(fallbackUrl, false)
              })
            }
          })

          /** https://alphatab.net/docs/guides/audio-video-sync — host pushes syncTimelineMs; play() no-op avoids double stem. */
          const getAudioEl = () => audioRef.current
          const wireWebExternalStemHandler = () => {
            const p = api.player as
              | {
                  setExternalMediaHandler?: (h: unknown) => void
                  output?: {
                    handler?: unknown
                    setExternalMediaHandler?: (h: unknown) => void
                    updatePosition?: (ms: number) => void
                  }
                }
              | undefined
            const out = p?.output
            const handler = {
              get backingTrackDuration() {
                const a = getAudioEl()
                const d = a?.duration
                return d != null && Number.isFinite(d) ? d * 1000 : 0
              },
              get playbackRate() {
                return getAudioEl()?.playbackRate ?? stemPlaybackRateRef.current
              },
              set playbackRate(v: number) {
                const a = getAudioEl()
                const next = Number.isFinite(v) ? v : 1
                stemPlaybackRateRef.current = clampStemPlaybackRate(next)
                if (a) a.playbackRate = stemPlaybackRateRef.current
                applyStemPlaybackSpeed(api, stemPlaybackRateRef.current)
              },
              get masterVolume() {
                return getAudioEl()?.volume ?? 1
              },
              set masterVolume(v: number) {
                const a = getAudioEl()
                if (a) a.volume = Number.isFinite(v) ? v : 1
              },
              seekTo: (timeMs: number) => {
                const a = getAudioEl()
                if (!a) return
                const ms = Math.max(0, Number(timeMs))
                const pr = stemPlaybackRateRef.current
                a.currentTime = (ms * pr) / 1000
                out?.updatePosition?.(ms)
                emitSongPlaybackMaybe()
                if (!readOnlyFollowModeRef.current) {
                  onScoreSeekMsRef.current?.(ms)
                }
              },
              play: () => Promise.resolve(),
              pause: () => {
                try {
                  getAudioEl()?.pause()
                } catch {
                  /* ignore */
                }
              },
            }
            try {
              if (out) {
                try {
                  out.handler = handler
                  return
                } catch {
                  /* fall through */
                }
              }
              if (p && typeof p.setExternalMediaHandler === 'function') {
                p.setExternalMediaHandler(handler)
              } else if (out && typeof out.setExternalMediaHandler === 'function') {
                out.setExternalMediaHandler(handler)
              }
            } catch {
              /* ignore */
            }
          }

          let externalStemWired = false
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
            if (webRuntimeDiagOnRef.current) webDiagRenderRef.current += 1
            layoutLoopBracket()
            emitSongDetailsSnap()
            emitSongPlaybackMaybe()
            if (!externalStemWired) {
              externalStemWired = true
              wireWebExternalStemHandler()
              applyStemPlaybackSpeed(api, stemPlaybackRateRef.current)
            }
            if (!readyPostedRef.current) {
              readyPostedRef.current = true
              onReady?.()
            }
            setTabFullyPainted(true)
          })

          setEngineReady(true)
          if (typeof window !== 'undefined') {
            window.setTimeout(() => {
              if (!cancelled) setSoundFontReady(true)
            }, 16_000)
          }
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
        if (noteFlushTimerRef.current != null) {
          clearTimeout(noteFlushTimerRef.current)
          noteFlushTimerRef.current = null
        }
        pendingNoteRef.current = null
        if (scrollSmoothRafRef.current != null) {
          window.cancelAnimationFrame(scrollSmoothRafRef.current)
          scrollSmoothRafRef.current = null
        }
        scrollTargetLeftRef.current = null
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
        appliedSoundFontProfileRef.current = null
        el.replaceChildren()
      }
    }, [
      emitNoteEvent,
      emitNoteTapFromScore,
      emitSongDetailsSnap,
      emitSongPlaybackMaybe,
      layoutLoopBracket,
      mounted,
      onError,
      onReady,
      reloadKey,
      themeKey,
      transposeSemitones,
    ])

    useEffect(() => {
      if (!engineReady) return
      const api = apiRef.current
      if (!api) return
      const raw = gp5Base64?.trim()
      if (!raw) return
      try {
        const bytes = base64ToUint8Array(raw)
        assertLikelyGpPayload(bytes)
        const buf = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
        resetSongMetaRefs()
        api.load(buf)
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Invalid GP5 payload'
        setEngineError(msg)
        onError?.(msg)
      }
    }, [engineReady, gp5Base64, onError, resetSongMetaRefs])

    useEffect(() => {
      if (!engineReady) return
      if (typeof window === 'undefined') return
      if (!audioRef.current) {
        audioRef.current = new Audio()
        audioRef.current.preload = 'auto'
        audioRef.current.crossOrigin = 'anonymous'
        audioRef.current.playbackRate = stemPlaybackRateRef.current
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
    }, [audioSrc, engineReady])

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
        className="min-h-[220px] flex flex-1 flex-col overflow-hidden rounded-xl border border-wood-600/45 bg-ivory"
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
            style={{
              display: 'flex',
              flexDirection: 'column',
              flex: 1,
              minHeight: 0,
              width: '100%',
              height: '100%',
            }}
          >
            {/*
              Scroll host = AlphaTab container + scrollElement only.
              Bottom strip is a sibling so inset isn’t drawn under the horizontal scrollbar track.
            */}
            <div
              style={{
                flex: 1,
                minHeight: 0,
                width: '100%',
                position: 'relative',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <div
                ref={hostRef}
                className="harmoniq-alphatab-scroll"
                data-theme={renderPreset === 'light' ? 'light' : 'dark'}
                style={{
                  flex: 1,
                  minHeight: 0,
                  width: '100%',
                  backgroundColor,
                  overflowX: 'auto',
                  overflowY: 'hidden',
                  position: 'relative',
                }}
              />
              {prerenderMarkup && !tabFullyPainted ? (
                <div
                  className="harmoniq-prerender-svg"
                  style={{
                    position: 'absolute',
                    left: 0,
                    top: 0,
                    right: 0,
                    bottom: 0,
                    overflow: 'auto',
                    zIndex: 6,
                    backgroundColor,
                    pointerEvents: 'none',
                  }}
                  // Trusted lesson artifact from Harmoniq backend only.
                  dangerouslySetInnerHTML={{ __html: prerenderMarkup }}
                />
              ) : null}
            </div>
            <div
              aria-hidden
              style={{
                height: 20,
                flexShrink: 0,
                width: '100%',
                backgroundColor,
              }}
            />
          </div>
        )}
        {mounted && !soundFontReady ? (
          <View className="absolute left-3 right-3 top-3 rounded-lg border border-wood-600/45 bg-wood-800/70 p-3">
            <Text className="mb-2 font-sans text-[11px] text-cream">Loading instrument sounds…</Text>
            <LoadingSkeleton height={10} borderRadius={6} />
          </View>
        ) : null}
        {!gp5Base64?.trim() && mounted ? (
          <View
            className="absolute bottom-2 left-2 right-2 rounded-lg border border-wood-600/40 bg-ivory px-2 py-1.5"
            pointerEvents="none"
          >
            <Text className="text-center font-sans text-[11px] text-muted-brown">
              {
                "Tab preview isn't available for this lesson yet. Try analyzing a song or another tab variant."
              }
            </Text>
          </View>
        ) : null}
      </View>
    )
  },
)
