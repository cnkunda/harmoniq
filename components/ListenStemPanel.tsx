import Slider from '@react-native-community/slider'
import { useIsFocused } from '@react-navigation/native'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { Platform, Pressable, ScrollView, Switch, Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { MetronomeArcReadout } from '@/components/MetronomeArcReadout'
import type { MetronomeSubdivision } from '@/src/audio/metronomeShared'
import { createStemMixer } from '@/src/audio/Mixer'
import type { StemMixer } from '@/src/audio/mixerTypes'
import { useLoopAudio } from '@/src/audio/useLoopAudio'
import { useMetronome } from '@/src/audio/useMetronome'
import colors from '@/src/constants/colors'
import type { PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import { useLessonStore } from '@/src/stores/lessonStore'
import type { LessonJSON } from '@/src/types'
import { lessonStemUrl, parseSectionRecord, sectionSeekSeconds } from '@/src/utils/lessonAudio'
import { Pause, Play } from 'lucide-react-native'

const STEM_UI_ORDER = ['guitar', 'bass', 'drums', 'vocals', 'piano', 'other'] as const

/** Toggles (metronome, stems): amber “on”, wood track off — matches playback accent controls. */
const STEM_SWITCH_TRACK = { false: colors.wood[500], true: `${colors.amber.accent}80` } as const
const STEM_SWITCH_THUMB_ON = colors.cream
const STEM_SWITCH_THUMB_OFF = colors.wood[600]

const METRO_SUBDIV_OPTIONS: { value: MetronomeSubdivision; label: string }[] = [
  { value: 1, label: '1/4' },
  { value: 2, label: '1/8' },
  { value: 4, label: '1/16' },
]

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
  return Math.max(0.5, Math.min(1.25, value))
}

export const ListenStemPanel = forwardRef<ListenStemPanelHandle, ListenStemPanelProps>(
  function ListenStemPanel(
    {
      onPlaybackTick,
      onSeek,
      onSeekSeconds,
      onRateChange,
      initialRate = 1,
      initialMetronomeOn = false,
      autoLoopRegion = null,
      initialStemMuteById,
    },
    ref,
  ) {
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)
  const isScreenFocused = useIsFocused()

  const mixerRef = useRef<StemMixer | null>(null)
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

  const onBeatFlash = useCallback((info: { isDownbeat: boolean }) => {
    setLastDownbeatFlash(info.isDownbeat)
    setBeatFlashTick((n) => n + 1)
    // #region agent log
    fetch('http://127.0.0.1:7847/ingest/304bce8c-5898-4e69-ad2e-982e56245f77', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '046f07' },
      body: JSON.stringify({
        sessionId: '046f07',
        runId: 'run1',
        hypothesisId: 'H1_H2',
        location: 'components/ListenStemPanel.tsx:onBeatFlash',
        message: 'metronome beat flash',
        data: { isDownbeat: info.isDownbeat, positionRef: positionRef.current, rateRef: rateRef.current },
        timestamp: Date.now(),
      }),
    }).catch(() => {})
    // #endregion
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
        const defs = ids.map((id) => ({
          id,
          label: id,
          uri: lessonStemUrl((lesson.stems as Record<string, string>)[id]!),
        }))
        await mixer.load(defs)
        if (cancelled) {
          await mixer.unload().catch(() => {})
          return
        }
        const initMute: Record<string, boolean> = {}
        for (const id of ids) initMute[id] = Boolean(initialStemMuteById?.[id])
        setStemMute(initMute)
        await syncStemGains(mixer, initMute)
        setDurationSec(mixer.getDurationSeconds())
        const idx = useLessonStore.getState().lessonSectionIndex
        const t0 = sectionSeekSeconds(lesson, idx)
        const seededRate = clampPlaybackRate(initialRate)
        await mixer.setPlaybackRate(seededRate).catch(() => {})
        await mixer.seek(t0)
        setPositionSec(t0)
        setReady(true)
        onRateChangeRef.current?.(seededRate)

        metro.stop()
        const ctx = mixer.getAudioContext?.() ?? null
        metro.bindAudioContext(ctx)
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : 'Could not load stems.')
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
    }
  }, [initialRate, initialStemMuteById, loadKey, lesson, metro, syncStemGains])

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

    const pollMs = metronomeOn ? 50 : 200

    const tick = () => {
      const m = mixerRef.current
      if (!m) return
      if (m.getPositionSecondsNow) {
        const p = m.getPositionSecondsNow()
        setPositionSec(p)
        emitTick(p)
        return
      }
      void m.getPositionSeconds().then((p) => {
        setPositionSec(p)
        emitTick(p)
      })
    }
    tick()
    const id = setInterval(tick, pollMs)
    return () => clearInterval(id)
  }, [metronomeOn, playing, ready])

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
    // #region agent log
    fetch('http://127.0.0.1:7847/ingest/304bce8c-5898-4e69-ad2e-982e56245f77', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '046f07' },
      body: JSON.stringify({
        sessionId: '046f07',
        runId: 'run1',
        hypothesisId: 'H1_H3',
        location: 'components/ListenStemPanel.tsx:metro.start',
        message: 'starting metronome',
        data: {
          playing,
          metronomeOn,
          posRef: positionRef.current,
          posNow: mixerRef.current?.getPositionSecondsNow?.() ?? null,
          rate: rateRef.current,
          alignOff,
          beatGridLen: beatGrid.length,
          beatGrid0: beatGrid[0] ?? null,
          beatGrid1: beatGrid[1] ?? null,
          bar0: barTimestamps[0] ?? null,
          sectionIndex: lessonSectionIndex,
        },
        timestamp: Date.now(),
      }),
    }).catch(() => {})
    // #endregion
    metro.setSubdivision(metroSubdivision)
    metro.start({
      beatGrid,
      barTimestamps: barTimestamps.length > 0 ? barTimestamps : undefined,
      tempoBpm,
      beatAlignOffsetSec: alignOff,
      getPlaybackRate: () => rateRef.current,
      getSongPositionSeconds: () => positionRef.current,
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
  }, [
    barLineKey,
    beatGridKey,
    lesson,
    metronomeOn,
    metro,
    metroSubdivision,
    onBeatFlash,
    playing,
    ready,
    rate,
  ])

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
        // #region agent log
        fetch('http://127.0.0.1:7847/ingest/304bce8c-5898-4e69-ad2e-982e56245f77', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '046f07' },
          body: JSON.stringify({
            sessionId: '046f07',
            runId: 'run1',
            hypothesisId: 'H1',
            location: 'components/ListenStemPanel.tsx:togglePlay.pause',
            message: 'pause requested',
            data: { posRef: positionRef.current, posNow: m.getPositionSecondsNow?.() ?? null, rate: rateRef.current },
            timestamp: Date.now(),
          }),
        }).catch(() => {})
        // #endregion
        await m.pause()
        setPlaying(false)
      } else {
        // #region agent log
        fetch('http://127.0.0.1:7847/ingest/304bce8c-5898-4e69-ad2e-982e56245f77', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '046f07' },
          body: JSON.stringify({
            sessionId: '046f07',
            runId: 'run1',
            hypothesisId: 'H1_H2',
            location: 'components/ListenStemPanel.tsx:togglePlay.play.before',
            message: 'play requested',
            data: { posRef: positionRef.current, posNow: m.getPositionSecondsNow?.() ?? null, rate: rateRef.current },
            timestamp: Date.now(),
          }),
        }).catch(() => {})
        // #endregion
        await m.play()
        // #region agent log
        fetch('http://127.0.0.1:7847/ingest/304bce8c-5898-4e69-ad2e-982e56245f77', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '046f07' },
          body: JSON.stringify({
            sessionId: '046f07',
            runId: 'run1',
            hypothesisId: 'H1_H2',
            location: 'components/ListenStemPanel.tsx:togglePlay.play.after',
            message: 'play resolved',
            data: { posRef: positionRef.current, posNow: m.getPositionSecondsNow?.() ?? null, rate: rateRef.current },
            timestamp: Date.now(),
          }),
        }).catch(() => {})
        // #endregion
        setPlaying(true)
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
      <Text className="mt-2 font-sans text-sm text-muted-brown">
        No lesson in memory — add a song from Home or open a session after analysis so stems can load.
      </Text>
    )
  }

  if (!lesson.stems || Object.keys(lesson.stems).length === 0) {
    const isDrillLick = typeof lesson.job_id === 'string' && lesson.job_id.startsWith('lick-')
    return (
      <Text className="mt-2 font-sans text-sm text-muted-brown">
        {isDrillLick
          ? 'This saved lick has no backing stem on file. Save it again from Review after a full analyzed lesson, or open a song that includes stems.'
          : 'This lesson has no stem paths yet. Re-run analysis with a backend that writes stems.'}
      </Text>
    )
  }

  const sections = lesson.sections ?? []
  const fmt = (s: number) => {
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  /** Cream panel, wood border — `flex-col` + `md:flex-1` so row stretch yields equal card heights. */
  const playbackCardClass =
    'flex flex-col rounded-xl border border-wood-600/40 bg-cream-dark/50 px-4 pb-4 pt-3.5 md:min-h-0 md:flex-1 md:min-w-[200px]'

  const baseTempoBpm = lesson.tempo != null && lesson.tempo > 0 ? lesson.tempo : 120
  const effectiveMetroBpm = Math.max(1, Math.round(baseTempoBpm * rate))

  const timelineMax = Math.max(0.01, durationSec)
  const timelineValue = Math.min(Math.max(0, scrubTimelineSec ?? positionSec), durationSec)

  return (
    <View className="mt-4 gap-4">
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

      <View className="flex-col gap-3 md:flex-row md:items-stretch">
        {/* Playback + timeline + speed */}
        <View className={playbackCardClass}>
          <Text className="mb-3 font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
            Playback
          </Text>

          <View className="flex-row items-center gap-4">
            <View className="w-14 shrink-0 items-center">
              <Pressable
                onPress={() => void togglePlay()}
                disabled={!ready || loading}
                className="h-14 w-14 items-center justify-center rounded-full bg-amber-accent disabled:opacity-40"
                accessibilityRole="button"
                accessibilityLabel={playing ? 'Pause' : 'Play'}
                hitSlop={10}
              >
                {playing ? (
                  <Pause color={colors.wood[900]} size={24} fill={colors.wood[900]} strokeWidth={0} />
                ) : (
                  <Play color={colors.wood[900]} size={24} fill={colors.wood[900]} strokeWidth={0} />
                )}
              </Pressable>
            </View>
            <View className="min-w-0 flex-1 justify-center">
              <View className="mb-2 flex-row items-baseline justify-between gap-3 pl-px pr-px">
                <Text className="font-mono text-[13px] leading-none tracking-tight text-wood-900">
                  {loading ? '…' : ready ? fmt(scrubTimelineSec ?? positionSec) : '—'}
                </Text>
                <Text className="font-mono text-[13px] leading-none tracking-tight text-muted-brown">
                  {loading ? '' : ready ? `/ ${fmt(durationSec)}` : ''}
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
                  maximumTrackTintColor={colors.muted.brown}
                  thumbTintColor={colors.amber.light}
                  disabled={!ready || loading || durationSec <= 0}
                />
              </View>
            </View>
          </View>

          <View className="mt-4 border-t border-wood-600/15 pt-3.5">
            <View className="mb-2 flex-row items-baseline justify-between gap-3">
              <Text className="font-sans-medium text-sm text-wood-900">Speed</Text>
              <Text className="font-mono text-[13px] tabular-nums tracking-tight text-muted-brown">
                {rate.toFixed(2)}×
              </Text>
            </View>
            <Slider
              minimumValue={0.5}
              maximumValue={1.25}
              step={0.05}
              value={rate}
              onValueChange={(v) => void onSeekRate(v)}
              minimumTrackTintColor={colors.amber.accent}
              maximumTrackTintColor={colors.muted.brown}
              thumbTintColor={colors.amber.light}
              disabled={!ready || loading}
            />
          </View>
        </View>

        {/* Metronome — same padding rhythm as playback; compact body keeps card height closer to pre-arc layout */}
        <View className={playbackCardClass}>
          <View className="mb-3 flex-row items-center justify-between gap-2">
            <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Metronome</Text>
            <Switch
              value={metronomeOn}
              onValueChange={setMetronomeOn}
              disabled={!ready || loading}
              trackColor={STEM_SWITCH_TRACK}
              thumbColor={metronomeOn ? STEM_SWITCH_THUMB_ON : STEM_SWITCH_THUMB_OFF}
            />
          </View>

          <MetronomeArcReadout
            effectiveBpm={effectiveMetroBpm}
            baseTempoBpm={baseTempoBpm}
            flashTick={beatFlashTick}
            lastDownbeat={lastDownbeatFlash}
            metronomeActive={metronomeOn && playing}
          />

          <View className="mt-4 border-t border-wood-600/15 pt-3.5">
            <Text className="mb-2 font-sans-medium text-sm text-wood-900">Subdivide</Text>
            <View className="flex-row flex-wrap gap-2">
              {METRO_SUBDIV_OPTIONS.map((opt) => {
                const active = metroSubdivision === opt.value
                return (
                  <AnimatedPressable
                    key={opt.value}
                    haptic="none"
                    disabled={!ready || loading}
                    onPress={() => setMetroSubdivision(opt.value)}
                    className={`min-w-0 flex-1 items-center rounded-md border px-2.5 py-1.5 ${
                      active ? 'border-amber-accent bg-amber-accent/25' : 'border-wood-600/50 bg-cream-dark/30'
                    } ${!ready || loading ? 'opacity-40' : ''}`}
                    accessibilityRole="button"
                    accessibilityState={{ selected: active }}
                  >
                    <Text className={`font-mono text-[11px] ${active ? 'text-wood-900' : 'text-muted-brown'}`}>
                      {opt.label}
                    </Text>
                  </AnimatedPressable>
                )
              })}
            </View>
          </View>
        </View>

        {/* Stems */}
        <View className={playbackCardClass}>
          <Text className="mb-3 font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Stems</Text>
          <ScrollView
            nestedScrollEnabled
            className="max-h-52 min-h-0 md:max-h-none md:flex-1"
            showsVerticalScrollIndicator
            keyboardShouldPersistTaps="handled"
          >
            <View className="gap-2 pb-1">
              {orderedStemIds(lesson.stems as Record<string, string>).map((id) => (
                <View key={id} className="flex-row items-center justify-between gap-2">
                  <Text className="flex-1 font-sans capitalize text-wood-900">{id}</Text>
                  <Switch
                    value={!stemMute[id]}
                    onValueChange={() => toggleStem(id)}
                    disabled={!ready || loading}
                    trackColor={STEM_SWITCH_TRACK}
                    thumbColor={stemMute[id] ? STEM_SWITCH_THUMB_OFF : STEM_SWITCH_THUMB_ON}
                  />
                </View>
              ))}
            </View>
          </ScrollView>
        </View>
      </View>

      {sections.length > 0 ? (
        <View className="rounded-xl border border-wood-600/40 bg-cream-dark/50 p-4">
          <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Sections</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} className="flex-row">
            <View className="flex-row flex-wrap gap-2 pb-1">
              {sections.map((raw, i) => {
                const sec = raw as Record<string, unknown>
                const { label } = parseSectionRecord(sec)
                const active = i === lessonSectionIndex
                return (
                  <Pressable
                    key={`${i}-${label}`}
                    onPress={() => void onChip(i)}
                    disabled={!ready || loading}
                    className={`rounded-full border px-3 py-1.5 ${
                      active ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/45 bg-cream-dark/40'
                    }`}
                    accessibilityRole="button"
                    accessibilityState={{ selected: active }}
                  >
                    <Text className={`font-sans text-xs ${active ? 'text-wood-900' : 'text-muted-brown'}`}>
                      {label}
                    </Text>
                  </Pressable>
                )
              })}
            </View>
          </ScrollView>
        </View>
      ) : null}
    </View>
  )
})

ListenStemPanel.displayName = 'ListenStemPanel'
