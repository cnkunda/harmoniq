import Slider from '@react-native-community/slider'
import { useIsFocused } from '@react-navigation/native'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState, type ReactNode } from 'react'
import { Platform, Pressable, ScrollView, Switch, Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import type { PlayLessonCaptureContext } from '@/components/play/playLessonCaptureTypes'
import { PlayCaptureLessonCardBanner } from '@/components/play'
import { MetronomeArcReadout } from '@/components/MetronomeArcReadout'
import type { MetronomeSubdivision } from '@/src/audio/metronomeShared'
import { createStemMixer } from '@/src/audio/Mixer'
import { GHOST_MIX_LINEAR, GHOST_STEM_ID } from '@/src/audio/ghostConstants'
import type { StemMixer } from '@/src/audio/mixerTypes'
import { useGhostStemSidecar } from '@/src/audio/useGhostStemSidecar'
import { useLoopAudio } from '@/src/audio/useLoopAudio'
import { useMetronome } from '@/src/audio/useMetronome'
import colors from '@/src/constants/colors'
import type { PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import { SESSION_PLAYBACK_CARD_CLASS } from '@/src/constants/sessionPlaybackCard'
import { logFirstAudioPlay } from '@/src/analytics/firstAudioPlay'
import { DEMO_LESSON_JOB_ID } from '@/src/demo/constants'
import { useLessonStore } from '@/src/stores/lessonStore'
import type { LessonJSON } from '@/src/types'
import { parseSectionRecord, sectionSeekSeconds, stemRelPathToDefinition } from '@/src/utils/lessonAudio'
import type { LucideIcon } from 'lucide-react-native'
import { AudioWaveform, Drum, Guitar, KeyboardMusic, Layers, Mic, Pause, Play } from 'lucide-react-native'

const STEM_UI_ORDER = ['guitar', 'bass', 'drums', 'vocals', 'piano', 'other'] as const

const STEM_ICONS: Record<(typeof STEM_UI_ORDER)[number], LucideIcon> = {
  guitar: Guitar,
  bass: AudioWaveform,
  drums: Drum,
  vocals: Mic,
  piano: KeyboardMusic,
  other: Layers,
}

/** Toggles (metronome, stems): amber “on”, wood track off — matches playback accent controls. */
const STEM_SWITCH_TRACK = { false: colors.wood[500], true: `${colors.amber.accent}80` } as const
const STEM_SWITCH_THUMB_ON = colors.cream
const STEM_SWITCH_THUMB_OFF = colors.wood[600]

const METRO_SUBDIV_OPTIONS: { value: MetronomeSubdivision; label: string }[] = [
  { value: 1, label: '1/4' },
  { value: 2, label: '1/8' },
  { value: 4, label: '1/16' },
]

/**
 * Choice chips (speed %, subdivide, sections): one inactive/active system — filled accent
 * when selected, neutral surface + hairline border when not (standard segmented / filter-chip pattern).
 */
const CHOICE_CHIP_BASE =
  'min-w-0 items-center justify-center rounded-full border px-3 py-1.5'
const CHOICE_CHIP_OFF = 'border-wood-600/40 bg-wood-900/10'
const CHOICE_CHIP_ON = 'border-amber-accent bg-amber-accent'
const CHOICE_LABEL_MONO_OFF = 'font-mono text-[11px] font-medium text-muted-light'
const CHOICE_LABEL_MONO_ON = 'font-mono text-[11px] font-medium text-wood-900'
const CHOICE_LABEL_SANS_OFF = 'font-sans text-xs text-muted-light'
const CHOICE_LABEL_SANS_ON = 'font-sans text-xs font-sans-medium text-wood-900'

function orderedStemIds(stems: Record<string, string>): string[] {
  const keys = Object.keys(stems)
  keys.sort((a, b) => {
    const ia = STEM_UI_ORDER.indexOf(a as (typeof STEM_UI_ORDER)[number])
    const ib = STEM_UI_ORDER.indexOf(b as (typeof STEM_UI_ORDER)[number])
    const sa = ia >= 0 ? ia : 99
    const sb = ib >= 0 ? ib : 99
    if (sa !== sb) return sa - sb
    return a.localeCompare(b)
  })
  return keys
}

export type ListenStemPanelProps = {
  /** Rendered inside the “Current lesson” card (e.g. Play capture controls). */
  lessonCardInsert?: ReactNode
  /** When set, replaces the third “Stems” column (e.g. Play step scoring UI). */
  stemsColumnReplacement?: ReactNode
  /** Fired on playback poll while playing, and once after pause when position is refreshed. */
  onPlaybackTick?: (ctx: PlaybackTickContext) => void
  /** Fired after a section chip seek completes. */
  onSeek?: () => void
  /** Fired with exact seek target in seconds after a seek completes. */
  onSeekSeconds?: (seconds: number) => void
  /** Fired when playback rate changes. */
  onRateChange?: (rate: number) => void
  /** Optional initial speed (e.g. 0.65 for Slow step). */
  initialRate?: number
  /** Optional initial metronome state. */
  initialMetronomeOn?: boolean
  /** Optional pre-entered loop region. Can be cleared by user. */
  autoLoopRegion?: { startSec: number; endSec: number; label?: string } | null
  /** Optional per-stem initial mute defaults (true = muted). */
  initialStemMuteById?: Record<string, boolean>
  /** Play session: reframe first card for capture + backing track. */
  lessonPlaybackCardVariant?: 'default' | 'play'
  /** When variant is `play`, reflects mic capture from `usePlayCapture`. */
  captureRecording?: boolean
  /** Play session: full capture card (backing state from this panel); supersedes title/banner/`lessonCardInsert`. */
  playCaptureSlot?: (ctx: PlayLessonCaptureContext) => ReactNode
  /** Bundled demo only: start playback once stems load (≤3 taps from Home). */
  autoPlayOnReady?: boolean
  /** Commit 75: playable URI for the latest ghost reference (blob / file path). */
  ghostStemPlaybackUri?: string | null
  ghostAnchorSec?: number | null
  /** Mix ghost under backing only while capturing when true. */
  playGhostWhileRecording?: boolean
}

export type ListenStemPanelHandle = {
  /** Seek stem mixer and notify `onSeek` / `onSeekSeconds` (tab + UI stay aligned). */
  seekTransportToSeconds: (sec: number) => Promise<void>
}

function lessonLoadKey(lesson: LessonJSON | null): string {
  if (!lesson?.stems || Object.keys(lesson.stems).length === 0) return ''
  const paths = orderedStemIds(lesson.stems).map((k) => lesson.stems![k] ?? '')
  return `${lesson.job_id ?? 'nj'}|${paths.join('|')}`
}

function clampPlaybackRate(value: number): number {
  if (!Number.isFinite(value)) return 1
  return Math.max(0.25, Math.min(1.25, value))
}

const SPEED_PRESETS = [
  { label: '0.5×', value: 0.5 },
  { label: '0.75×', value: 0.75 },
  { label: '1.0×', value: 1.0 },
  { label: '1.25×', value: 1.25 },
] as const

const RATE_MATCH_EPS = 0.02

export const ListenStemPanel = forwardRef<ListenStemPanelHandle, ListenStemPanelProps>(
  function ListenStemPanel(
    {
      lessonCardInsert,
      stemsColumnReplacement,
      onPlaybackTick,
      onSeek,
      onSeekSeconds,
      onRateChange,
      initialRate = 1,
      initialMetronomeOn = false,
      autoLoopRegion = null,
      initialStemMuteById,
      lessonPlaybackCardVariant = 'default',
      captureRecording = false,
      playCaptureSlot,
      autoPlayOnReady = false,
      ghostStemPlaybackUri = null,
      ghostAnchorSec = null,
      playGhostWhileRecording = false,
    },
    ref,
  ) {
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)
  const isScreenFocused = useIsFocused()

  const mixerRef = useRef<StemMixer | null>(null)
  const paddedGhostRevokeRef = useRef<string | null>(null)
  const metro = useMetronome()

  const [ready, setReady] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const [positionSec, setPositionSec] = useState(0)
  const [durationSec, setDurationSec] = useState(0)
  const [rate, setRate] = useState(clampPlaybackRate(initialRate))
  const [metronomeOn, setMetronomeOn] = useState(Boolean(initialMetronomeOn))
  const [metroSubdivision, setMetroSubdivision] = useState<MetronomeSubdivision>(1)
  const [beatFlashTick, setBeatFlashTick] = useState(0)
  const [lastDownbeatFlash, setLastDownbeatFlash] = useState(true)
  const [stemMute, setStemMute] = useState<Record<string, boolean>>({})
  const [loopRegion, setLoopRegion] = useState<{ startSec: number; endSec: number; label?: string } | null>(autoLoopRegion)
  /** Non-null while dragging the timeline scrubber (decouples slider from transport poll). */
  const [scrubTimelineSec, setScrubTimelineSec] = useState<number | null>(null)

  const positionRef = useRef(0)
  positionRef.current = positionSec

  const playingRef = useRef(playing)
  playingRef.current = playing

  const rateRef = useRef(rate)
  rateRef.current = rate

  useGhostStemSidecar({
    ghostFileUri: Platform.OS === 'web' ? null : ghostStemPlaybackUri,
    anchorSec: ghostAnchorSec ?? 0,
    ghostAudible: Boolean(playGhostWhileRecording && captureRecording && ghostStemPlaybackUri),
    mixerPlaying: playing,
    getMixerPositionSec: () => {
      const m = mixerRef.current
      const live = m?.getPositionSecondsNow?.()
      if (typeof live === 'number' && Number.isFinite(live)) return live
      return positionRef.current
    },
    masterDurationSec: durationSec,
    playbackRate: rateRef.current,
    mixerReady: ready,
  })

  useEffect(() => {
    if (isScreenFocused) return
    metro.stop()
    const m = mixerRef.current
    if (!m) {
      setPlaying(false)
      return
    }
    void m.pause().then(() => setPlaying(false)).catch(() => setPlaying(false))
  }, [isScreenFocused, metro])

  const loadKey = lessonLoadKey(lesson)
  const beatGridKey = lesson?.beat_grid?.join(',') ?? ''
  const barLineKey = lesson?.bar_timestamps?.join(',') ?? ''

  const onPlaybackTickRef = useRef(onPlaybackTick)
  onPlaybackTickRef.current = onPlaybackTick
  const onSeekRef = useRef(onSeek)
  onSeekRef.current = onSeek
  const onSeekSecondsRef = useRef(onSeekSeconds)
  onSeekSecondsRef.current = onSeekSeconds
  const onRateChangeRef = useRef(onRateChange)
  onRateChangeRef.current = onRateChange

  const autoDemoPlayRef = useRef(false)

  const seekTransportToSeconds = useCallback(
    async (positionSec: number) => {
      const m = mixerRef.current
      if (!m || !ready) return
      const t = Math.max(0, Number.isFinite(positionSec) ? positionSec : 0)
      try {
        await m.seek(t)
        setPositionSec(t)
        onSeekRef.current?.()
        onSeekSecondsRef.current?.(t)
      } catch (e) {
        setLoadError(e instanceof Error ? e.message : 'Seek failed')
      }
    },
    [ready],
  )

  useImperativeHandle(ref, () => ({ seekTransportToSeconds }), [seekTransportToSeconds])

  useEffect(() => {
    setRate(clampPlaybackRate(initialRate))
  }, [initialRate])

  useEffect(() => {
    setMetronomeOn(Boolean(initialMetronomeOn))
  }, [initialMetronomeOn])

  useEffect(() => {
    setLoopRegion(autoLoopRegion)
  }, [autoLoopRegion])

  useEffect(() => {
    setScrubTimelineSec(null)
  }, [loadKey])

  useEffect(() => {
    autoDemoPlayRef.current = false
  }, [loadKey])

  const onBeatFlash = useCallback((info: { isDownbeat: boolean }) => {
    setLastDownbeatFlash(info.isDownbeat)
    setBeatFlashTick((n) => n + 1)
  }, [])

  const syncStemGains = useCallback(
    async (mixer: StemMixer, muteMap: Record<string, boolean>) => {
      const ids = Object.keys(muteMap)
      for (const id of ids) {
        await mixer.setStemGain(id, muteMap[id] ? 0 : 1).catch(() => {})
      }
    },
    [],
  )

  useEffect(() => {
    if (!lesson?.stems || Object.keys(lesson.stems).length === 0) {
      setReady(false)
      setLoadError(null)
      setDurationSec(0)
      setPositionSec(0)
      setPlaying(false)
      mixerRef.current = null
      metro.stop()
      return
    }

    let cancelled = false
    const mixer = createStemMixer()
    mixerRef.current = mixer

    const boot = async () => {
      setLoading(true)
      setLoadError(null)
      setReady(false)
      try {
        const ids = orderedStemIds(lesson.stems as Record<string, string>)
        const defs = ids.map((id) =>
          stemRelPathToDefinition(id, (lesson.stems as Record<string, string>)[id]!),
        )
        await mixer.load(defs)
        if (cancelled) {
          await mixer.unload().catch(() => {})
          return
        }

        if (Platform.OS === 'web' && ghostStemPlaybackUri) {
          try {
            const masterDur = mixer.getDurationSeconds()
            const ghostWeb = require('@/src/audio/ghostStem.web') as typeof import('@/src/audio/ghostStem.web')
            const paddedUrl = await ghostWeb.buildPaddedGhostStemBlobUrl({
              ghostPlaybackUri: ghostStemPlaybackUri,
              anchorSec: ghostAnchorSec ?? 0,
              masterDurationSec: masterDur,
            })
            if (paddedUrl && !cancelled) {
              if (paddedGhostRevokeRef.current) {
                URL.revokeObjectURL(paddedGhostRevokeRef.current)
              }
              paddedGhostRevokeRef.current = paddedUrl
              await mixer.unload()
              await mixer.load([...defs, ghostWeb.ghostStemDefinition(paddedUrl)])
            }
          } catch (e) {
            console.warn('[ListenStemPanel] ghost stem pad/decode skipped — playback continues without ghost', e)
          }
        }

        if (cancelled) {
          await mixer.unload().catch(() => {})
          return
        }

        const initMute: Record<string, boolean> = {}
        for (const id of ids) initMute[id] = Boolean(initialStemMuteById?.[id])
        setStemMute(initMute)
        await syncStemGains(mixer, initMute)
        if (Platform.OS === 'web') {
          await mixer.setStemGain(GHOST_STEM_ID, 0).catch(() => {})
        }
        setDurationSec(mixer.getDurationSeconds())
        const idx = useLessonStore.getState().lessonSectionIndex
        const t0 = sectionSeekSeconds(lesson, idx)
        const seededRate = clampPlaybackRate(initialRate)
        await mixer.setPlaybackRate(seededRate).catch(() => {})
        await mixer.seek(t0)
        setPositionSec(t0)
        setReady(true)
        onRateChangeRef.current?.(seededRate)

        if (autoPlayOnReady && !autoDemoPlayRef.current) {
          autoDemoPlayRef.current = true
          try {
            await mixer.play()
            setPlaying(true)
            logFirstAudioPlay({
              source: 'demo_listen',
              job_id: useLessonStore.getState().lesson?.job_id ?? null,
            })
          } catch {
            autoDemoPlayRef.current = false
          }
        }

        metro.stop()
        const ctx = mixer.getAudioContext?.() ?? null
        metro.bindAudioContext(ctx)
      } catch (e) {
        if (!cancelled) {
          const jobId = lesson?.job_id ?? 'unknown'
          const detail = e instanceof Error ? `${e.message} (job=${jobId})` : `Could not load stems (job=${jobId})`
          console.error('[ListenStemPanel] stem load failed:', e, { jobId })
          setLoadError(detail)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void boot()

    return () => {
      cancelled = true
      metro.stop()
      mixer.unload().catch(() => {})
      mixerRef.current = null
      if (paddedGhostRevokeRef.current) {
        URL.revokeObjectURL(paddedGhostRevokeRef.current)
        paddedGhostRevokeRef.current = null
      }
    }
  }, [
    autoPlayOnReady,
    ghostAnchorSec,
    ghostStemPlaybackUri,
    initialRate,
    initialStemMuteById,
    loadKey,
    lesson,
    metro,
    syncStemGains,
  ])

  useEffect(() => {
    if (Platform.OS !== 'web') return
    const m = mixerRef.current
    if (!m || !ready) return
    const audible = Boolean(playGhostWhileRecording && captureRecording && ghostStemPlaybackUri)
    void m.setStemGain(GHOST_STEM_ID, audible ? GHOST_MIX_LINEAR : 0).catch(() => {})
  }, [captureRecording, ghostStemPlaybackUri, playGhostWhileRecording, ready])

  useEffect(() => {
    if (!ready) return

    const emitTick = (p: number) => {
      onPlaybackTickRef.current?.({
        positionSec: p,
        playing: playingRef.current,
        rate: rateRef.current,
        ready: true,
      })
    }

    if (!playing) {
      const m = mixerRef.current
      if (m) {
        void m.getPositionSeconds().then((p) => {
          setPositionSec(p)
          emitTick(p)
        })
      }
      return
    }

    let rafId = 0
    let lastUiMs = 0
    const UI_THROTTLE_MS = 80

    const step = () => {
      rafId = requestAnimationFrame(step)
      const m = mixerRef.current
      if (!m) return
      const p = m.getPositionSecondsNow?.() ?? positionRef.current
      emitTick(p)
      const now = typeof performance !== 'undefined' ? performance.now() : Date.now()
      if (now - lastUiMs >= UI_THROTTLE_MS) {
        lastUiMs = now
        setPositionSec(p)
      }
    }
    rafId = requestAnimationFrame(step)
    return () => cancelAnimationFrame(rafId)
  }, [playing, ready])

  useEffect(() => {
    if (!lesson || !ready) return
    if (!metronomeOn || !playing) {
      metro.stop()
      return
    }
    if (Platform.OS === 'web') {
      const ctx = mixerRef.current?.getAudioContext?.() ?? null
      metro.bindAudioContext(ctx)
    }
    const beatGrid = lesson.beat_grid ?? []
    const barTimestamps = lesson.bar_timestamps ?? []
    const tempoBpm = lesson.tempo != null && lesson.tempo > 0 ? lesson.tempo : 120
    const alignOff =
      typeof lesson.beat_align_offset_sec === 'number' && Number.isFinite(lesson.beat_align_offset_sec)
        ? lesson.beat_align_offset_sec
        : 0
    metro.setSubdivision(metroSubdivision)
    metro.start({
      beatGrid,
      barTimestamps: barTimestamps.length > 0 ? barTimestamps : undefined,
      tempoBpm,
      beatAlignOffsetSec: alignOff,
      getPlaybackRate: () => rateRef.current,
      getSongPositionSeconds: () => {
        const m = mixerRef.current
        const live = m?.getPositionSecondsNow?.()
        if (typeof live === 'number' && Number.isFinite(live)) return live
        return positionRef.current
      },
      getSongPositionSecondsNow: () => {
        const m = mixerRef.current
        const p = m?.getPositionSecondsNow?.()
        return typeof p === 'number' && Number.isFinite(p) ? p : positionRef.current
      },
      getSongPositionAtContextTime:
        Platform.OS === 'web'
          ? (ctxTime: number) => {
              const m = mixerRef.current
              const p = m?.getSongPositionAtContextTime?.(ctxTime)
              if (typeof p === 'number' && Number.isFinite(p)) return p
              const q = m?.getPositionSecondsNow?.()
              return typeof q === 'number' && Number.isFinite(q) ? q : positionRef.current
            }
          : undefined,
      isPlaying: () => playingRef.current,
      subdivision: metroSubdivision,
      onBeatFlash,
    })
    return () => metro.stop()
  }, [barLineKey, beatGridKey, lesson, metronomeOn, metro, metroSubdivision, onBeatFlash, playing, ready])

  useLoopAudio({
    active: ready && playing && Boolean(loopRegion),
    startSec: loopRegion?.startSec ?? 0,
    endSec: loopRegion?.endSec ?? 0,
    mixerRef,
    onWrappedToLoopStart: (startSec) => {
      setPositionSec(startSec)
      onSeekRef.current?.()
      onSeekSecondsRef.current?.(startSec)
    },
  })

  const toggleStem = (id: string) => {
    if (!lesson?.stems?.[id]) return
    setStemMute((prev) => {
      const next = { ...prev, [id]: !prev[id] }
      const m = mixerRef.current
      if (m && ready) void syncStemGains(m, next)
      return next
    })
  }

  const togglePlay = async () => {
    const m = mixerRef.current
    if (!m || !ready) return
    try {
      if (playing) {
        await m.pause()
        setPlaying(false)
      } else {
        await m.play()
        setPlaying(true)
        logFirstAudioPlay({
          source: lesson?.job_id === DEMO_LESSON_JOB_ID ? 'demo_listen' : 'session_listen',
          job_id: lesson?.job_id ?? null,
        })
      }
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Playback error')
    }
  }

  const onSeekRate = async (value: number) => {
    setRate(value)
    onRateChangeRef.current?.(value)
    const m = mixerRef.current
    if (m && ready) {
      await m.setPlaybackRate(value).catch(() => {})
    }
  }

  const onChip = async (index: number) => {
    if (!lesson) return
    setLessonSectionIndex(index)
    const t = sectionSeekSeconds(lesson, index)
    await seekTransportToSeconds(t)
  }

  if (!lesson) {
    return (
      <Text className="mt-2 font-sans text-sm text-muted-light">
        No song loaded — add one from Home or open a session after analysis so stems can load.
      </Text>
    )
  }

  if (!lesson.stems || Object.keys(lesson.stems).length === 0) {
    const isDrillLick = typeof lesson.job_id === 'string' && lesson.job_id.startsWith('lick-')
    return (
      <Text className="mt-2 font-sans text-sm text-muted-light">
        {isDrillLick
          ? 'This saved lick has no backing stem on file. Save it again from Review after a full analysis, or open a song that includes stems.'
          : 'This song has no stem paths yet. Re-run analysis with a backend that writes stems.'}
      </Text>
    )
  }

  const sections = lesson.sections ?? []
  const fmt = (s: number) => {
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return `${m}:${sec.toString().padStart(2, '0')}`
  }
  const songTitle = lesson.song_title?.trim() || 'Untitled song'
  const sectionTotal = Math.max(sections.length, 1)
  const sectionDisplay = Math.min(lessonSectionIndex + 1, sectionTotal)

  const nextSectionIndex = lessonSectionIndex + 1
  const hasUpNext = nextSectionIndex < sections.length
  const currentSectionLabel =
    sections[lessonSectionIndex] != null
      ? parseSectionRecord(sections[lessonSectionIndex] as Record<string, unknown>).label
      : null

  const sectionLine =
    sections.length > 0
      ? `Section ${sectionDisplay} of ${sections.length}${currentSectionLabel ? `: ${currentSectionLabel}` : ''}`
      : `Section ${sectionDisplay} of ${sectionTotal}`

  const playbackCardClass = SESSION_PLAYBACK_CARD_CLASS

  const baseTempoBpm = lesson.tempo != null && lesson.tempo > 0 ? lesson.tempo : 120
  const effectiveMetroBpm = Math.max(1, Math.round(baseTempoBpm * rate))

  const timelineMax = Math.max(0.01, durationSec)
  const timelineValue = Math.min(Math.max(0, scrubTimelineSec ?? positionSec), durationSec)

  const playLessonCard = lessonPlaybackCardVariant === 'play'
  const showPlayCaptureShell = Boolean(playLessonCard && playCaptureSlot)

  return (
    <View className="mt-3 gap-3">
      {loadError ? (
        <Text className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 font-sans text-sm text-danger">
          {loadError}
        </Text>
      ) : null}

      {loopRegion ? (
        <View className="rounded-xl border border-amber-accent/35 bg-amber-accent/10 px-3 py-2">
          <Text className="font-sans text-xs text-wood-900">
            Loop active: {loopRegion.label ?? 'target bar'} ({fmt(loopRegion.startSec)} - {fmt(loopRegion.endSec)})
          </Text>
          <Pressable
            onPress={() => setLoopRegion(null)}
            className="mt-2 self-start rounded-md border border-wood-600/45 bg-cream-dark/50 px-2.5 py-1.5"
            accessibilityRole="button"
          >
            <Text className="font-sans text-xs text-wood-900">Clear loop</Text>
          </Pressable>
        </View>
      ) : null}

      <View className="flex-col gap-2.5 md:flex-row md:items-stretch">
        {/* Playback + lesson context + timeline + speed + up next */}
        <View className={playbackCardClass}>
          {playLessonCard && playCaptureSlot ? (
            playCaptureSlot({
              songTitle,
              sectionLine,
              loading,
              ready,
              playing,
            })
          ) : (
            <>
              <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
                {playLessonCard ? 'Play capture' : 'Current lesson'}
              </Text>
              {playLessonCard ? (
                <Text className="font-sans text-xs leading-snug text-muted-light">
                  Stems below are your backing track. Start capture when you are ready — Harmoniq scores pitch on each
                  beat.
                </Text>
              ) : null}
              <Text
                className={`font-sans-medium text-wood-900 ${playLessonCard ? 'mt-2 text-sm' : 'text-base'}`}
                numberOfLines={playLessonCard ? 2 : undefined}
              >
                {songTitle}
              </Text>
              <Text className="mt-1 font-sans text-xs text-muted-light">{sectionLine}</Text>

              {playLessonCard ? (
                <PlayCaptureLessonCardBanner
                  loading={loading}
                  ready={ready}
                  playing={playing}
                  recording={captureRecording}
                />
              ) : null}

              {lessonCardInsert != null ? (
                <View className="mt-3 border-t border-wood-600/15 pt-3">{lessonCardInsert}</View>
              ) : null}
            </>
          )}

          <View
            className={`${
              showPlayCaptureShell ? 'mt-4' : lessonCardInsert != null ? 'mt-3' : 'mt-4'
            } flex-row items-center gap-2.5`}
          >
            <View className="w-12 shrink-0 items-center">
              <Pressable
                onPress={() => void togglePlay()}
                disabled={!ready || loading}
                className="h-12 w-12 items-center justify-center rounded-full bg-amber-accent disabled:opacity-40"
                accessibilityRole="button"
                accessibilityLabel={playing ? 'Pause' : 'Play'}
                hitSlop={10}
              >
                {playing ? (
                  <Pause color={colors.wood[900]} size={22} fill={colors.wood[900]} strokeWidth={0} />
                ) : (
                  <Play color={colors.wood[900]} size={22} fill={colors.wood[900]} strokeWidth={0} />
                )}
              </Pressable>
            </View>
            <View className="min-w-0 flex-1 justify-center">
              <View className="mb-1.5 flex-row items-baseline justify-between gap-3 pl-px pr-px">
                <Text className="font-mono text-[13px] leading-none tracking-tight text-wood-900">
                  {loading ? '…' : ready ? fmt(scrubTimelineSec ?? positionSec) : '—'}
                </Text>
                <Text className="font-mono text-[13px] leading-none tracking-tight text-muted-light">
                  {loading ? '' : ready ? fmt(durationSec) : ''}
                </Text>
              </View>
              <View className="-mt-0.5">
                <Slider
                  minimumValue={0}
                  maximumValue={timelineMax}
                  step={0.05}
                  value={ready && durationSec > 0 ? timelineValue : 0}
                  onSlidingStart={(v) => setScrubTimelineSec(v)}
                  onValueChange={(v) => setScrubTimelineSec(v)}
                  onSlidingComplete={(v) => {
                    setScrubTimelineSec(null)
                    void seekTransportToSeconds(v)
                  }}
                  minimumTrackTintColor={colors.amber.accent}
                  maximumTrackTintColor={colors.muted.light}
                  thumbTintColor={colors.amber.light}
                  disabled={!ready || loading || durationSec <= 0}
                />
              </View>
            </View>
          </View>

          {!playLessonCard ? (
            <View className="mt-3 border-t border-wood-600/15 pt-3">
              <View className="mb-2 flex-row items-baseline justify-between gap-3">
                <Text className="font-sans-medium text-sm text-wood-900">Speed</Text>
                <Text className="font-mono text-[13px] tabular-nums tracking-tight text-muted-light">
                  {rate.toFixed(1)}×
                </Text>
              </View>
              <View className="mt-1 flex-row gap-1.5">
                {SPEED_PRESETS.map(({ label, value }) => {
                  const active = Math.abs(rate - value) < RATE_MATCH_EPS
                  return (
                    <Pressable
                      key={label}
                      onPress={() => void onSeekRate(value)}
                      disabled={!ready || loading}
                      className={`flex-1 ${CHOICE_CHIP_BASE} ${active ? CHOICE_CHIP_ON : CHOICE_CHIP_OFF} ${
                        !ready || loading ? 'opacity-40' : ''
                      }`}
                      accessibilityRole="button"
                      accessibilityState={{ selected: active }}
                      accessibilityLabel={`Speed ${label}`}
                    >
                      <Text className={active ? CHOICE_LABEL_MONO_ON : CHOICE_LABEL_MONO_OFF}>{label}</Text>
                    </Pressable>
                  )
                })}
              </View>
            </View>
          ) : null}

          {!playLessonCard && hasUpNext ? (
            <View className="mt-3 border-t border-wood-600/20 pt-3">
              <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Up next</Text>
              <Text className="mt-1 font-sans text-sm text-muted-light">{`Section ${nextSectionIndex + 1}`}</Text>
            </View>
          ) : null}
        </View>

        {/* Metronome */}
        <View className={playbackCardClass}>
          <View className="mb-2 shrink-0 flex-row items-center justify-between gap-2">
            <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Metronome</Text>
            <Switch
              value={metronomeOn}
              onValueChange={setMetronomeOn}
              disabled={!ready || loading}
              trackColor={STEM_SWITCH_TRACK}
              thumbColor={metronomeOn ? STEM_SWITCH_THUMB_ON : STEM_SWITCH_THUMB_OFF}
            />
          </View>

          <View className="min-h-0 flex-1 items-center justify-center">
            <MetronomeArcReadout
              effectiveBpm={effectiveMetroBpm}
              baseTempoBpm={baseTempoBpm}
              flashTick={beatFlashTick}
              lastDownbeat={lastDownbeatFlash}
              metronomeActive={metronomeOn && playing}
              subdivision={metroSubdivision}
              showBpm={false}
            />
          </View>

          <View className="mt-2 shrink-0 border-t border-wood-600/15 pt-3">
            <View className="mb-3 flex-row items-baseline justify-center gap-1.5">
              <Text className="font-serif text-3xl leading-none text-wood-900 tabular-nums">{effectiveMetroBpm}</Text>
              <Text className="pb-1 font-sans text-sm text-muted-light">BPM</Text>
            </View>
            <Text className="mb-2 font-sans-medium text-sm text-wood-900">Subdivide</Text>
            <View className="flex-row flex-wrap gap-1.5">
              {METRO_SUBDIV_OPTIONS.map((opt) => {
                const active = metroSubdivision === opt.value
                return (
                  <AnimatedPressable
                    key={opt.value}
                    haptic="none"
                    disabled={!ready || loading}
                    onPress={() => setMetroSubdivision(opt.value)}
                    className={`flex-1 ${CHOICE_CHIP_BASE} ${active ? CHOICE_CHIP_ON : CHOICE_CHIP_OFF} ${
                      !ready || loading ? 'opacity-40' : ''
                    }`}
                    accessibilityRole="button"
                    accessibilityState={{ selected: active }}
                  >
                    <Text className={active ? CHOICE_LABEL_MONO_ON : CHOICE_LABEL_MONO_OFF}>{opt.label}</Text>
                  </AnimatedPressable>
                )
              })}
            </View>
          </View>
        </View>

        {stemsColumnReplacement != null ? (
          stemsColumnReplacement
        ) : (
          /* Stems + optional sections */
          <View className={playbackCardClass}>
            <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Stems</Text>
            {(() => {
              const warn =
                typeof lesson.stem_isolation_warning === 'string' && lesson.stem_isolation_warning.trim()
                  ? lesson.stem_isolation_warning.trim()
                  : null
              const tabNote =
                !warn &&
                lesson.tabs_unavailable_reason === 'no_isolated_guitar' &&
                lesson.guitar_stem_usable === false
                  ? 'Guitar tab was not generated for this track — the isolated guitar stem was not reliable enough.'
                  : null
              const body = warn ?? tabNote
              if (!body) return null
              return (
                <View className="mb-3 rounded-lg border border-danger/35 bg-danger/10 px-3 py-2">
                  <Text className="font-sans text-xs leading-snug text-wood-900">{body}</Text>
                </View>
              )
            })()}
            {sections.length > 0 ? (
              <View className="mb-3">
                <Text className="mb-2 font-sans-medium text-sm text-wood-900">Sections</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} className="flex-row">
                  <View className="flex-row flex-wrap gap-1.5 pb-1">
                    {sections.map((raw, i) => {
                      const sec = raw as Record<string, unknown>
                      const { label } = parseSectionRecord(sec)
                      const active = i === lessonSectionIndex
                      return (
                        <Pressable
                          key={`${i}-${label}`}
                          onPress={() => void onChip(i)}
                          disabled={!ready || loading}
                          className={`shrink-0 ${CHOICE_CHIP_BASE} ${active ? CHOICE_CHIP_ON : CHOICE_CHIP_OFF} ${
                            !ready || loading ? 'opacity-40' : ''
                          }`}
                          accessibilityRole="button"
                          accessibilityState={{ selected: active }}
                        >
                          <Text className={active ? CHOICE_LABEL_SANS_ON : CHOICE_LABEL_SANS_OFF}>{label}</Text>
                        </Pressable>
                      )
                    })}
                  </View>
                </ScrollView>
              </View>
            ) : null}

            <View className={sections.length > 0 ? 'border-t border-wood-600/15 pt-3' : ''}>
              <Text className="mb-2 font-sans-medium text-sm text-wood-900">Mixer</Text>
              <View className="flex-row flex-wrap gap-x-1 gap-y-1.5">
                {STEM_UI_ORDER.map((id) => {
                  const hasStem = Boolean((lesson.stems as Record<string, string>)?.[id])
                  const Icon = STEM_ICONS[id]
                  const unmuted = hasStem && !stemMute[id]
                  const label = id.charAt(0).toUpperCase() + id.slice(1)
                  const disabled = !ready || loading || !hasStem
                  const tileBusy = hasStem && (!ready || loading)
                  return (
                    <Pressable
                      key={id}
                      onPress={() => toggleStem(id)}
                      disabled={disabled}
                      accessibilityRole="button"
                      accessibilityLabel={`${label} stem, ${unmuted ? 'on' : 'off'}`}
                      accessibilityState={{ disabled }}
                      className={`w-[32%] max-w-[32%] shrink-0 items-center rounded-lg border px-1.5 py-1.5 ${
                        !hasStem
                          ? 'border-wood-600/25 bg-cream-dark/20 opacity-45'
                          : unmuted
                            ? 'border-amber-accent bg-ivory/60'
                            : 'border-wood-600/40 bg-wood-900/5'
                      } ${tileBusy ? 'opacity-45' : ''}`}
                    >
                      <Icon
                        size={20}
                        color={!hasStem ? colors.muted.light : unmuted ? colors.amber.accent : colors.muted.light}
                        strokeWidth={1.75}
                      />
                      <Text
                        className={`mt-1 font-sans text-[10px] leading-tight ${unmuted && hasStem ? 'font-sans-medium text-wood-900' : 'text-muted-light'}`}
                      >
                        {label}
                      </Text>
                    </Pressable>
                  )
                })}
              </View>
            </View>
          </View>
        )}
      </View>
    </View>
  )
})

ListenStemPanel.displayName = 'ListenStemPanel'
