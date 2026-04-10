import { Buffer } from 'buffer'
import { Audio } from 'expo-av'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ActivityIndicator, Platform, Pressable, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { ErrorBanner } from '@/components/ErrorBanner'
import { submitScore } from '@/src/api/analyze'
import type { MappedUiError } from '@/src/errors/mapErrorToUi'
import { mapMicPermissionDenied, mapScoreFlowError, toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import { openHarmoniqAppSettings } from '@/src/errors/openHarmoniqAppSettings'
import { createSessionRecorder } from '@/src/audio/recordSession'
import type { RecordedTake } from '@/src/audio/recordSession.types'
import { BACKING_TRACKS } from '@/src/constants/backingTracks'
import { PLACEMENT_PHRASES, PLACEMENT_SKILL_NODES } from '@/src/onboarding/placementPhrases'
import { useOnboardingPlacementStore } from '@/src/stores/onboardingPlacementStore'

/** Same bundled asset as jam/backing constants — avoids a broken `../../../../` path from `app/onboarding/phrase/`. */
const PLACEMENT_REFERENCE_SOURCE = BACKING_TRACKS.find((t) => t.id === 'am-blues-70')!.source

function bytesToBase64(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString('base64')
}

function parsePhraseIndex(raw: string | string[] | undefined): number {
  const s = Array.isArray(raw) ? raw[0] : raw
  const n = parseInt(s ?? '', 10)
  return Number.isFinite(n) && n >= 0 && n < PLACEMENT_PHRASES.length ? n : -1
}

export default function OnboardingPhraseScreen() {
  const router = useRouter()
  const { index: indexParam } = useLocalSearchParams<{ index: string }>()
  const phraseIndex = parsePhraseIndex(indexParam)
  const setPhraseResult = useOnboardingPlacementStore((s) => s.setPhraseResult)

  const recorderRef = useRef(createSessionRecorder())
  const soundRef = useRef<Audio.Sound | null>(null)
  const lastScorableTakeRef = useRef<RecordedTake | null>(null)

  const [refPlaying, setRefPlaying] = useState(false)
  const [soundReady, setSoundReady] = useState(false)
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [phraseError, setPhraseError] = useState<MappedUiError | null>(null)

  const phrase = phraseIndex >= 0 ? PLACEMENT_PHRASES[phraseIndex] : null

  useEffect(() => {
    if (phraseIndex < 0) {
      router.replace('/onboarding')
    }
  }, [phraseIndex, router])

  useEffect(() => {
    let mounted = true
    void (async () => {
      try {
        await Audio.setAudioModeAsync({
          allowsRecordingIOS: true,
          playsInSilentModeIOS: true,
        })
        const { sound } = await Audio.Sound.createAsync(PLACEMENT_REFERENCE_SOURCE, { shouldPlay: false })
        if (mounted) {
          soundRef.current = sound
          sound.setOnPlaybackStatusUpdate((st) => {
            if (st.isLoaded && !st.isPlaying) setRefPlaying(false)
          })
          setSoundReady(true)
        } else void sound.unloadAsync()
      } catch {
        /* reference optional */
      }
    })()
    return () => {
      mounted = false
      setSoundReady(false)
      void soundRef.current?.unloadAsync()
      soundRef.current = null
    }
  }, [])

  const toggleReference = useCallback(async () => {
    const s = soundRef.current
    if (!s) return
    const st = await s.getStatusAsync()
    if (!st.isLoaded) return
    if (st.isPlaying) {
      await s.pauseAsync()
      setRefPlaying(false)
    } else {
      await s.setPositionAsync(0)
      await s.playAsync()
      setRefPlaying(true)
    }
  }, [])

  const startRecord = useCallback(async () => {
    setPhraseError(null)
    try {
      const snd = soundRef.current
      if (snd) {
        await snd.stopAsync().catch(() => {})
        setRefPlaying(false)
      }
      await recorderRef.current.start()
      setRecording(true)
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      if (message === 'MIC_PERMISSION_DENIED') {
        setPhraseError(mapMicPermissionDenied(Platform.OS))
      } else {
        setPhraseError({
          message: 'Could not start recording. Check the mic and try again.',
          variant: 'error',
          actionKind: 'dismiss',
          actionLabel: 'Dismiss',
        })
      }
    }
  }, [])

  const submitPlacementScore = useCallback(
    async (take: RecordedTake) => {
      if (!phrase || phraseIndex < 0) return
      const section = {
        ...phrase.section,
        mode: 'minor',
      }
      const result = await submitScore({
        recording_wav_base64: bytesToBase64(take.audioBytes),
        recording_mime_type: take.mimeType,
        section,
        skill_nodes: [...PLACEMENT_SKILL_NODES],
      })
      lastScorableTakeRef.current = null
      setPhraseResult(phraseIndex, result)
      const next = phraseIndex + 1
      if (next < PLACEMENT_PHRASES.length) {
        router.replace({ pathname: '/onboarding/phrase/[index]', params: { index: String(next) } })
      } else {
        router.replace('/onboarding/results')
      }
    },
    [phrase, phraseIndex, router, setPhraseResult],
  )

  const stopAndScore = useCallback(async () => {
    if (!phrase || phraseIndex < 0) return
    setBusy(true)
    setPhraseError(null)
    try {
      const take = await recorderRef.current.stop()
      setRecording(false)
      if (!take.audioBytes.length) {
        setPhraseError({
          message: 'No audio captured. Try again closer to the mic.',
          variant: 'warning',
          actionKind: 'dismiss',
          actionLabel: 'Dismiss',
        })
        return
      }
      lastScorableTakeRef.current = take
      await submitPlacementScore(take)
    } catch (e) {
      setPhraseError(mapScoreFlowError(e))
    } finally {
      setBusy(false)
    }
  }, [phrase, phraseIndex, submitPlacementScore])

  if (!phrase || phraseIndex < 0) {
    return (
      <SafeAreaView className="flex-1 items-center justify-center bg-wood-900">
        <ActivityIndicator color="#E8A54B" />
      </SafeAreaView>
    )
  }

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <View className="flex-1 px-6 py-6">
        <Text className="font-mono text-xs text-muted-brown">
          Phrase {phraseIndex + 1} / {PLACEMENT_PHRASES.length}
        </Text>
        <Text className="mt-2 font-serif text-2xl text-cream">{phrase.title}</Text>
        <Text className="mt-3 font-sans text-sm leading-6 text-muted-brown">{phrase.instruction}</Text>

        <View className="mt-6 flex-row flex-wrap gap-2">
          <Pressable
            onPress={() => void toggleReference()}
            disabled={!soundReady}
            className="rounded-lg border border-wood-600/50 bg-wood-800/80 px-4 py-2 disabled:opacity-40"
            accessibilityRole="button"
          >
            <Text className="font-sans-medium text-cream">{refPlaying ? 'Pause reference' : 'Play reference'}</Text>
          </Pressable>
        </View>

        <View className="mt-8 flex-row flex-wrap gap-2">
          <Pressable
            onPress={() => void startRecord()}
            disabled={recording || busy}
            className="rounded-lg bg-amber-accent px-4 py-3 disabled:opacity-40"
            accessibilityRole="button"
          >
            <Text className="font-sans-medium text-wood-900">{recording ? 'Recording…' : 'Record take'}</Text>
          </Pressable>
          <Pressable
            onPress={() => void stopAndScore()}
            disabled={!recording || busy}
            className="rounded-lg border border-amber-accent/60 px-4 py-3 disabled:opacity-40"
            accessibilityRole="button"
          >
            <Text className="font-sans-medium text-amber-light">{busy ? 'Scoring…' : 'Stop & score'}</Text>
          </Pressable>
        </View>

        {phraseError ? (
          <ErrorBanner
            className="mt-4"
            {...toErrorBannerProps(phraseError, {
              onRetry: () => {
                const take = lastScorableTakeRef.current
                if (!take?.audioBytes.length) {
                  setPhraseError(null)
                  return
                }
                setPhraseError(null)
                setBusy(true)
                void submitPlacementScore(take)
                  .catch((e) => setPhraseError(mapScoreFlowError(e)))
                  .finally(() => setBusy(false))
              },
              onDismiss: () => setPhraseError(null),
              onOpenSettings: () => {
                void openHarmoniqAppSettings()
                setPhraseError(null)
              },
              onContinue: () => setPhraseError(null),
            })}
          />
        ) : null}

        <Pressable onPress={() => router.back()} className="mt-10 self-start py-2" accessibilityRole="button">
          <Text className="font-sans text-sm text-muted-brown">Back</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  )
}
