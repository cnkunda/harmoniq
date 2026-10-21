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
  }>()

  const track = useMemo(() => {
    const trackId = readParam(params.trackId)
    return BACKING_TRACKS.find((t) => t.id === trackId) ?? null
  }, [params.trackId])

  const region = useMemo(() => {
    const loopLength = track?.durationMs ?? 24_000
    const rawStart = Number(readParam(params.startMs))
    const rawEnd = Number(readParam(params.endMs))
    if (!Number.isFinite(rawStart) || !Number.isFinite(rawEnd)) return null
    const start = Math.max(0, Math.min(rawStart, loopLength - MIN_REGION_MS))
    const end = Math.max(start + MIN_REGION_MS, Math.min(rawEnd, loopLength))
    return { startMs: start, endMs: end }
  }, [params.endMs, params.startMs, track?.durationMs])

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
    if (!track || !region) return
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
        track.source,
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
  }, [onStatus, region, track])

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

  useEffect(() => {
    if (!track || !region) return
    void startPlayback()
    // Auto-start once per practice target.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [track?.id, region?.startMs, region?.endMs])

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

        {!track || !region ? (
          <View className="mt-8 rounded-2xl border border-wood-700/60 bg-wood-800/50 p-5">
            <Text className="font-sans-medium text-base text-cream">This phrase has no matching loop.</Text>
            <Text className="mt-2 font-sans text-sm leading-relaxed text-cream/75">
              Practice works with bundled classic loops. This jam used an AI backing track, and no classic loop
              shares its key and tempo.
            </Text>
          </View>
        ) : (
          <View className="mt-6 gap-5">
            <View className="items-center rounded-3xl border border-wood-700/60 bg-wood-800/50 px-5 py-8">
              <Text className="font-mono text-xs uppercase tracking-widest text-amber-light">
                {phraseLabel}
              </Text>
              <Text className="mt-2 text-center font-serif text-2xl text-cream">{track.label}</Text>
              <Text className="mt-1 font-sans text-xs text-muted-light">
                {((region.endMs - region.startMs) / 1000).toFixed(1)}s loop · 0.75× speed ·{' '}
                {track.bpm != null ? `${track.bpm} BPM` : 'ambient'}
              </Text>
              <Text className="mt-1 font-sans text-xs text-muted-light">
                {(region.startMs / 1000).toFixed(1)}s – {(region.endMs / 1000).toFixed(1)}s in the loop
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
