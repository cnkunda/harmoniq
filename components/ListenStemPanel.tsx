import Slider from '@react-native-community/slider'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Platform, Pressable, ScrollView, Switch, Text, View } from 'react-native'

import { createBeatMetronome } from '@/src/audio/createBeatMetronome'
import { createStemMixer } from '@/src/audio/Mixer'
import type { BeatMetronome } from '@/src/audio/beatMetronome.types'
import type { StemMixer } from '@/src/audio/mixerTypes'
import colors from '@/src/constants/colors'
import { useLessonStore } from '@/src/stores/lessonStore'
import type { LessonJSON } from '@/src/types'
import type { PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import { lessonStemUrl, parseSectionRecord, sectionSeekSeconds } from '@/src/utils/lessonAudio'

const STEM_UI_ORDER = ['guitar', 'bass', 'drums', 'vocals', 'piano', 'other'] as const

/** Matches design-preview StemMixerDevSection Switch styling. */
const STEM_SWITCH_TRACK = { false: colors.wood[500], true: `${colors.amber.accent}80` } as const
const STEM_SWITCH_THUMB_ON = colors.cream
const STEM_SWITCH_THUMB_OFF = colors.wood[600]

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

function lessonLoadKey(lesson: LessonJSON | null): string {
  if (!lesson?.stems || Object.keys(lesson.stems).length === 0) return ''
  const paths = orderedStemIds(lesson.stems).map((k) => lesson.stems![k] ?? '')
  return `${lesson.job_id ?? 'nj'}|${paths.join('|')}`
}

function clampPlaybackRate(value: number): number {
  if (!Number.isFinite(value)) return 1
  return Math.max(0.5, Math.min(1.25, value))
}

export function ListenStemPanel({
  onPlaybackTick,
  onSeek,
  onSeekSeconds,
  onRateChange,
  initialRate = 1,
  initialMetronomeOn = false,
  autoLoopRegion = null,
  initialStemMuteById,
}: ListenStemPanelProps = {}) {
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)

  const mixerRef = useRef<StemMixer | null>(null)
  const metroRef = useRef<BeatMetronome | null>(null)

  const [ready, setReady] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const [positionSec, setPositionSec] = useState(0)
  const [durationSec, setDurationSec] = useState(0)
  const [rate, setRate] = useState(clampPlaybackRate(initialRate))
  const [metronomeOn, setMetronomeOn] = useState(Boolean(initialMetronomeOn))
  const [stemMute, setStemMute] = useState<Record<string, boolean>>({})
  const [loopRegion, setLoopRegion] = useState<{ startSec: number; endSec: number; label?: string } | null>(autoLoopRegion)

  const positionRef = useRef(0)
  positionRef.current = positionSec

  const playingRef = useRef(playing)
  playingRef.current = playing

  const rateRef = useRef(rate)
  rateRef.current = rate

  const loadKey = lessonLoadKey(lesson)
  const beatGridKey = lesson?.beat_grid?.join(',') ?? ''

  const onPlaybackTickRef = useRef(onPlaybackTick)
  onPlaybackTickRef.current = onPlaybackTick
  const onSeekRef = useRef(onSeek)
  onSeekRef.current = onSeek
  const onSeekSecondsRef = useRef(onSeekSeconds)
  onSeekSecondsRef.current = onSeekSeconds
  const onRateChangeRef = useRef(onRateChange)
  onRateChangeRef.current = onRateChange

  useEffect(() => {
    setRate(clampPlaybackRate(initialRate))
  }, [initialRate])

  useEffect(() => {
    setMetronomeOn(Boolean(initialMetronomeOn))
  }, [initialMetronomeOn])

  useEffect(() => {
    setLoopRegion(autoLoopRegion)
  }, [autoLoopRegion])

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

        metroRef.current?.stop()
        const ctx = mixer.getAudioContext?.() ?? null
        metroRef.current = createBeatMetronome(ctx)
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
      metroRef.current?.stop()
      metroRef.current = null
      mixer.unload().catch(() => {})
      mixerRef.current = null
    }
  }, [initialRate, initialStemMuteById, loadKey, lesson, syncStemGains])

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

    const tick = () => {
      const m = mixerRef.current
      if (!m) return
      void m.getPositionSeconds().then((p) => {
        setPositionSec(p)
        emitTick(p)
      })
    }
    tick()
    const id = setInterval(tick, 200)
    return () => clearInterval(id)
  }, [playing, ready])

  useEffect(() => {
    const m = metroRef.current
    if (!m || !lesson || !ready) return
    if (!metronomeOn || !playing) {
      m.stop()
      return
    }
    const beatGrid = lesson.beat_grid ?? []
    const tempoBpm = lesson.tempo != null && lesson.tempo > 0 ? lesson.tempo : 120
    m.start({
      beatGrid,
      tempoBpm,
      getPlaybackRate: () => rateRef.current,
      getSongPositionSeconds: () => positionRef.current,
      isPlaying: () => playingRef.current,
    })
    return () => m.stop()
  }, [metronomeOn, playing, ready, beatGridKey, lesson?.tempo, rate])

  useEffect(() => {
    if (!ready || !playing || !loopRegion) return
    const { startSec, endSec } = loopRegion
    if (!Number.isFinite(startSec) || !Number.isFinite(endSec) || endSec <= startSec + 0.05) return
    const id = setInterval(() => {
      const m = mixerRef.current
      if (!m || !playingRef.current) return
      void m.getPositionSeconds().then((p) => {
        if (p >= endSec - 0.02) {
          void m.seek(startSec).then(() => {
            setPositionSec(startSec)
            onSeekRef.current?.()
            onSeekSecondsRef.current?.(startSec)
          })
        }
      })
    }, 120)
    return () => clearInterval(id)
  }, [loopRegion, playing, ready])

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
        await m.pause()
        setPlaying(false)
      } else {
        await m.play()
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
    const m = mixerRef.current
    if (!m || !ready) return
    try {
      await m.seek(t)
      setPositionSec(t)
      onSeekRef.current?.()
      onSeekSecondsRef.current?.(t)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Seek failed')
    }
  }

  if (!lesson) {
    return (
      <Text className="mt-2 font-sans text-sm text-muted-brown">
        No lesson in memory — complete Analyze (debug) first, then open the session from there.
      </Text>
    )
  }

  if (!lesson.stems || Object.keys(lesson.stems).length === 0) {
    return (
      <Text className="mt-2 font-sans text-sm text-muted-brown">
        This lesson has no stem paths yet. Re-run analysis with a backend that writes stems.
      </Text>
    )
  }

  const sections = lesson.sections ?? []
  const fmt = (s: number) => {
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  return (
    <View className="mt-4 gap-4">
      {loadError ? (
        <Text className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 font-sans text-sm text-danger">
          {loadError}
        </Text>
      ) : null}

      <View className="flex-row flex-wrap items-center gap-3">
        <Pressable
          onPress={() => void togglePlay()}
          disabled={!ready || loading}
          className="rounded-lg bg-amber-accent/90 px-5 py-2.5 disabled:opacity-40"
          accessibilityRole="button"
        >
          <Text className="font-sans-medium text-wood-900">{playing ? 'Pause' : 'Play'}</Text>
        </Pressable>
        <Text className="font-mono text-xs text-muted-brown">
          {loading ? 'Loading stems…' : ready ? `${fmt(positionSec)} / ${fmt(durationSec)}` : '—'}
        </Text>
      </View>

      {loopRegion ? (
        <View className="rounded-lg border border-amber-accent/35 bg-amber-accent/10 px-3 py-2">
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

      <View>
        <Text className="mb-1 font-sans-medium text-sm text-wood-900">Speed</Text>
        <Slider
          minimumValue={0.5}
          maximumValue={1.25}
          step={0.05}
          value={rate}
          onValueChange={(v) => void onSeekRate(v)}
          minimumTrackTintColor={colors.amber.accent}
          maximumTrackTintColor={colors.wood[600]}
          thumbTintColor={colors.amber.light}
          disabled={!ready || loading}
        />
        <Text className="font-mono text-xs text-muted-brown">{rate.toFixed(2)}×</Text>
      </View>

      <View className="flex-row items-center justify-between">
        <Text className="font-sans-medium text-sm text-wood-900">Metronome</Text>
        <Switch
          value={metronomeOn}
          onValueChange={setMetronomeOn}
          disabled={!ready || loading}
          trackColor={STEM_SWITCH_TRACK}
          thumbColor={metronomeOn ? STEM_SWITCH_THUMB_ON : STEM_SWITCH_THUMB_OFF}
        />
      </View>
      {Platform.OS !== 'web' ? (
        <Text className="font-sans text-[11px] text-muted-brown">
          Metronome uses a short click sample; grid alignment is coarse on native (~40ms poll).
        </Text>
      ) : null}

      {sections.length > 0 ? (
        <View>
          <Text className="mb-2 font-sans-medium text-sm text-wood-900">Sections</Text>
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
                    <Text
                      className={`font-sans text-xs ${active ? 'text-wood-900' : 'text-muted-brown'}`}
                    >
                      {label}
                    </Text>
                  </Pressable>
                )
              })}
            </View>
          </ScrollView>
        </View>
      ) : null}

      <View>
        <Text className="mb-2 font-sans-medium text-sm text-wood-900">Stems</Text>
        <View className="gap-2">
          {orderedStemIds(lesson.stems as Record<string, string>).map((id) => (
            <View key={id} className="flex-row items-center justify-between">
              <Text className="font-sans capitalize text-wood-900">{id}</Text>
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
      </View>
    </View>
  )
}
