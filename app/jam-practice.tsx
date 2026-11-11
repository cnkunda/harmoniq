import { Audio, type AVPlaybackStatus } from 'expo-av'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ActivityIndicator, Text, View } from 'react-native'
import { Pause, Play, RotateCcw } from 'lucide-react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { toast } from '@/components/ToastConfig'
import { WoodGradient } from '@/components/WoodGradient'
import { BACKING_TRACKS } from '@/src/constants/backingTracks'
import { requestJamBacking } from '@/src/api/jam'
import { prepareJamBackingPlayable } from '@/src/jam/jamBackingPlayable'
import { colors } from '@/src/constants/colors'
import { globalAudioManager } from '@/src/audio/GlobalAudioManager'

const PRACTICE_RATE = 0.75
const MIN_REGION_MS = 300

type PlaybackPhase = 'idle' | 'loading' | 'playing' | 'paused'

function readParam(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value[0] ?? null
  return value ?? null
}

export default function JamPracticeScreen() {
  const router = useRouter()
  const params = useLocalSearchParams<{
    trackId?: string
    startMs?: string
    endMs?: string
    phraseIndex?: string
    source?: string
    key?: string
    bpm?: string
    progression?: string
    prompt?: string
  }>()

  const isAi = readParam(params.source) === 'ai' || readParam(params.trackId) === 'ai-instrumental'
  const track = useMemo(() => {
    const trackId = readParam(params.trackId)
    return BACKING_TRACKS.find((t) => t.id === trackId) ?? null
  }, [params.trackId])

  const [aiBed, setAiBed] = useState<{
    uri: string
    release: () => void
    durationMs: number
    bpm: number | null
    label: string
  } | null>(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)
  const aiBedRef = useRef<typeof aiBed>(null)
  aiBedRef.current = aiBed

  useEffect(() => {
    if (!isAi || aiBed) return
    let cancelled = false
    setAiLoading(true)
    setAiError(null)
    const key = readParam(params.key) ?? 'A minor'
    const rawBpm = Number(readParam(params.bpm))
    const bpm = Number.isFinite(rawBpm) && rawBpm > 0 ? Math.round(rawBpm) : null
    const progression = (readParam(params.progression) ?? '')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    const rawEnd = Number(readParam(params.endMs))
    const durationSecs = Math.max(16, Math.min(64, Math.ceil((Number.isFinite(rawEnd) ? rawEnd : 16000) / 1000)))
    void requestJamBacking({
      musical_key: key,
      bpm,
      style_hint: readParam(params.prompt) ?? undefined,
      chord_progression: progression,
      duration_secs: durationSecs,
    })
      .then(async (res) => {
        const prepared = await prepareJamBackingPlayable(res.audio_base64, res.mime_type)
        if (cancelled) {
          prepared.release()
          return
        }
        setAiBed({
          uri: prepared.uri,
          release: prepared.release,
          durationMs: typeof res.duration_ms === 'number' && res.duration_ms > 0 ? res.duration_ms : durationSecs * 1000,
          bpm: typeof res.bpm === 'number' && res.bpm > 0 ? Math.round(res.bpm) : bpm,
          label: `AI practice bed · ${res.key_label ?? key}`,
        })
      })
      .catch((e) => {
        if (!cancelled) setAiError(e instanceof Error ? e.message : 'Could not generate a practice bed')
      })
      .finally(() => {
        if (!cancelled) setAiLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [aiBed, isAi, params.bpm, params.endMs, params.key, params.prompt, params.progression])

  useEffect(() => {
    return () => {
      aiBedRef.current?.release()
    }
  }, [])

  const durationMs = isAi ? aiBed?.durationMs ?? null : track?.durationMs ?? 24_000
  const region = useMemo(() => {
    if (!durationMs || durationMs <= MIN_REGION_MS) return null
    const rawStart = Number(readParam(params.startMs))
    const rawEnd = Number(readParam(params.endMs))
    if (!Number.isFinite(rawStart) || !Number.isFinite(rawEnd)) return null
    const start = Math.max(0, Math.min(rawStart, durationMs - MIN_REGION_MS))
    const end = Math.max(start + MIN_REGION_MS, Math.min(rawEnd, durationMs))
    return { startMs: start, endMs: end }
  }, [durationMs, params.endMs, params.startMs])

  const phraseIndex = Number(readParam(params.phraseIndex))
  const phraseLabel = Number.isFinite(phraseIndex) ? `Phrase ${Math.round(phraseIndex) + 1}` : 'Phrase'

  const soundRef = useRef<Audio.Sound | null>(null)
  const wrapInFlightRef = useRef(false)
  const mountedRef = useRef(true)
  const [phase, setPhase] = useState<PlaybackPhase>('idle')
  const [error, setError] = useState<string | null>(null)

  const unloadSound = useCallback(async () => {
    const sound = soundRef.current
    soundRef.current = null
    if (!sound) return
    sound.setOnPlaybackStatusUpdate(null)
    await globalAudioManager.unregisterInstance('jam-practice-audio')
    try {
      await sound.stopAsync()
      await sound.unloadAsync()
    } catch (e) {
      console.warn('[JamPractice] cleanup failed', e)
    }
  }, [])

  const onStatus = useCallback(
    (status: AVPlaybackStatus) => {
      if (!status.isLoaded || !region) return
      if (mountedRef.current) {
        setPhase(status.isPlaying ? 'playing' : 'paused')
      }
      if (!status.isPlaying || status.positionMillis < region.endMs - 15) return
      if (wrapInFlightRef.current) return
      wrapInFlightRef.current = true
      void soundRef.current
        ?.setPositionAsync(region.startMs)
        .catch((e) => console.warn('[JamPractice] loop seek failed', e))
        .finally(() => {
          wrapInFlightRef.current = false
        })
    },
    [region],
  )

  const startPlayback = useCallback(async () => {
    const source = isAi ? (aiBed ? { uri: aiBed.uri } : null) : (track ? track.source : null)
    if (!source || !region) return
    setError(null)
    if (soundRef.current) {
      try {
        await soundRef.current.playAsync()
        setPhase('playing')
      } catch (e) {
        const message = e instanceof Error ? e.message : 'Could not resume playback'
        setError(message)
      }
      return
    }

    setPhase('loading')
    try {
      await globalAudioManager.resetToPlaybackMode()
      const { sound } = await Audio.Sound.createAsync(
        source,
        {
          shouldPlay: true,
          isLooping: false,
          positionMillis: region.startMs,
          volume: 1,
        },
      )
      soundRef.current = sound
      sound.setOnPlaybackStatusUpdate(onStatus)
      globalAudioManager.registerInstance('jam-practice-audio', 'expo-sound', sound, async () => {
        sound.setOnPlaybackStatusUpdate(null)
        await sound.unloadAsync()
      })
      try {
        await sound.setRateAsync(PRACTICE_RATE, true)
      } catch (e) {
        console.warn('[JamPractice] slow rate unavailable, continuing at normal speed', e)
      }
      if (mountedRef.current) setPhase('playing')
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Could not start the practice loop'
      setError(message)
      setPhase('idle')
      toast.error(message)
    }
  }, [aiBed, isAi, onStatus, region, track])

  const togglePlayback = useCallback(() => {
    const sound = soundRef.current
    if (!sound) {
      void startPlayback()
      return
    }
    sound
      .getStatusAsync()
      .then((status) => {
        if (!status.isLoaded) return
        if (status.isPlaying) {
          return sound.pauseAsync().then(() => setPhase('paused'))
        }
        return sound.playAsync().then(() => setPhase('playing'))
      })
      .catch((e) => {
        const message = e instanceof Error ? e.message : 'Could not control playback'
        setError(message)
      })
  }, [startPlayback])

  const restart = useCallback(() => {
    if (!region) return
    const sound = soundRef.current
    if (!sound) {
      void startPlayback()
      return
    }
    void sound
      .setPositionAsync(region.startMs)
      .then(() => sound.playAsync())
      .then(() => setPhase('playing'))
      .catch((e) => {
        const message = e instanceof Error ? e.message : 'Could not restart the loop'
        setError(message)
      })
  }, [region, startPlayback])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      void unloadSound()
    }
  }, [unloadSound])

  const readyToPractice = Boolean(region) && (isAi ? Boolean(aiBed) : Boolean(track))
  useEffect(() => {
    if (!readyToPractice || !region) return
    void startPlayback()
    // Auto-start once per practice target.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [track?.id, region?.startMs, region?.endMs, aiBed?.uri, readyToPractice])

  return (
    <WoodGradient className="flex-1">
      <SafeAreaView className="flex-1 px-5" edges={['top', 'left', 'right']}>
        <View className="mt-3 flex-row items-center justify-between">
          <Text className="font-serif text-3xl text-cream">Practice phrase</Text>
          <AnimatedPressable
            onPress={() => router.back()}
            haptic="light"
            className="min-h-[44px] justify-center px-2"
            accessibilityRole="button"
            accessibilityLabel="Close phrase practice"
          >
            <Text className="font-sans-medium text-sm text-muted-light">Close</Text>
          </AnimatedPressable>
        </View>

        {isAi && aiLoading ? (
          <View className="mt-8 items-center rounded-2xl border border-wood-700/60 bg-wood-800/50 p-5">
            <ActivityIndicator color={colors.amber.accent} />
            <Text className="mt-3 font-sans-medium text-base text-cream">Generating practice bed…</Text>
            <Text className="mt-1 font-sans text-xs text-muted-light">
              Recreating the jam backing for this phrase. This can take a minute or two.
            </Text>
          </View>
        ) : isAi && aiError ? (
          <View className="mt-8 rounded-2xl border border-danger/40 bg-danger/10 p-5">
            <Text className="font-sans-medium text-base text-cream">Could not generate the practice bed.</Text>
            <Text className="mt-2 font-sans text-sm leading-relaxed text-cream/75">{aiError}</Text>
          </View>
        ) : !readyToPractice ? (
          <View className="mt-8 rounded-2xl border border-wood-700/60 bg-wood-800/50 p-5">
            <Text className="font-sans-medium text-base text-cream">This phrase has no matching loop.</Text>
            <Text className="mt-2 font-sans text-sm leading-relaxed text-cream/75">
              Choose a bundled loop or record a new jam with an AI backing bed to practice this phrase.
            </Text>
          </View>
        ) : (
          <View className="mt-6 gap-5">
            <View className="items-center rounded-3xl border border-wood-700/60 bg-wood-800/50 px-5 py-8">
              <Text className="font-mono text-xs uppercase tracking-widest text-amber-light">
                {phraseLabel}
              </Text>
              <Text className="mt-2 text-center font-serif text-2xl text-cream">
                {isAi ? aiBed?.label ?? 'AI practice bed' : track?.label ?? 'Bundled loop'}
              </Text>
              <Text className="mt-1 font-sans text-xs text-muted-light">
                {((region!.endMs - region!.startMs) / 1000).toFixed(1)}s loop · 0.75× speed ·{' '}
                {(isAi ? aiBed?.bpm : track?.bpm) != null
                  ? `${isAi ? aiBed?.bpm : track?.bpm} BPM`
                  : 'ambient'}
              </Text>
              <Text className="mt-1 font-sans text-xs text-muted-light">
                {(region!.startMs / 1000).toFixed(1)}s – {(region!.endMs / 1000).toFixed(1)}s in the loop
              </Text>

              <View className="mt-7 flex-row items-center gap-4">
                <AnimatedPressable
                  onPress={restart}
                  haptic="light"
                  className="min-h-[52px] min-w-[52px] items-center justify-center rounded-full border border-wood-600/70"
                  accessibilityRole="button"
                  accessibilityLabel="Restart phrase loop"
                >
                  <RotateCcw color={colors.cream} size={20} />
                </AnimatedPressable>
                <AnimatedPressable
                  onPress={togglePlayback}
                  haptic="medium"
                  disabled={phase === 'loading'}
                  className="min-h-[76px] min-w-[76px] items-center justify-center rounded-full bg-amber-accent disabled:opacity-60"
                  accessibilityRole="button"
                  accessibilityLabel={phase === 'playing' ? 'Pause phrase loop' : 'Play phrase loop'}
                >
                  {phase === 'loading' ? (
                    <ActivityIndicator color={colors.wood[900]} />
                  ) : phase === 'playing' ? (
                    <Pause color={colors.wood[900]} size={28} />
                  ) : (
                    <Play color={colors.wood[900]} size={28} />
                  )}
                </AnimatedPressable>
                <View className="min-w-[52px]" />
              </View>
              <Text className="mt-4 font-sans text-xs text-muted-light">
                {phase === 'playing' ? 'Looping…' : phase === 'loading' ? 'Starting…' : 'Paused'}
              </Text>
            </View>

            <View className="rounded-2xl border border-wood-700/60 bg-wood-800/40 p-4">
              <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">
                How to use this
              </Text>
              <Text className="mt-2 font-sans text-sm leading-relaxed text-cream/80">
                Play along with the slowed loop until the phrase feels easy. Keep the same fingering and let the
                chord changes guide your line.
              </Text>
            </View>

            {error ? (
              <Text className="font-sans text-sm text-danger">{error}</Text>
            ) : null}
          </View>
        )}
      </SafeAreaView>
    </WoodGradient>
  )
}
