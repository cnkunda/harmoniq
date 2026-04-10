import { useRouter } from 'expo-router'
import { Audio } from 'expo-av'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Platform, ScrollView, Text, View } from 'react-native'
import Animated, {
  cancelAnimation,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { ErrorBanner } from '@/components/ErrorBanner'
import { toast } from '@/components/ToastConfig'
import { WoodGradient } from '@/components/WoodGradient'
import { submitJamScore } from '@/src/api/analyze'
import { mapBrowserMicBlockedForJam, toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import { BACKING_TRACKS, type BackingTrackId } from '@/src/constants/backingTracks'
import { insertJamSnapshotRow } from '@/src/db/client'
import { createPitchClassHistogram } from '@/src/jam/pitchClassHistogram'
import { usePitchStream } from '@/src/pitch/usePitchStream'

export default function JamScreen() {
  const router = useRouter()
  const { start: startPitch, stop: stopPitch } = usePitchStream()

  const [isJamming, setIsJamming] = useState(false)
  const [selectedTrack, setSelectedTrack] = useState<BackingTrackId>(BACKING_TRACKS[0].id)
  const [scaleLabel, setScaleLabel] = useState('—')
  const [webMicBlocked, setWebMicBlocked] = useState(false)
  const [micBannerKey, setMicBannerKey] = useState(0)
  const [busy, setBusy] = useState(false)

  const pulse = useSharedValue(1)
  const ringStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pulse.value }],
    opacity: 0.5 + (pulse.value - 1) * 3,
  }))

  const soundRef = useRef<Audio.Sound | null>(null)
  const histogramRef = useRef(createPitchClassHistogram())
  const jamStartedAtRef = useRef<number | null>(null)

  const stopPulse = useCallback(() => {
    cancelAnimation(pulse)
    pulse.value = withTiming(1, { duration: 200 })
  }, [pulse])

  const startPulse = useCallback(() => {
    pulse.value = 1
    pulse.value = withRepeat(withTiming(1.12, { duration: 900 }), -1, true)
  }, [pulse])

  useEffect(() => {
    return () => {
      cancelAnimation(pulse)
      pulse.value = 1
      void stopPitch()
      const s = soundRef.current
      if (s) {
        void s.stopAsync().catch(() => {})
        void s.unloadAsync().catch(() => {})
        soundRef.current = null
      }
    }
  }, [pulse, stopPitch])

  const beginJamAfterMic = useCallback(async () => {
    const track = BACKING_TRACKS.find((t) => t.id === selectedTrack) ?? BACKING_TRACKS[0]
    await Audio.setAudioModeAsync({
      allowsRecordingIOS: true,
      playsInSilentModeIOS: true,
      staysActiveInBackground: false,
      shouldDuckAndroid: true,
      playThroughEarpieceAndroid: false,
    })
    const { sound } = await Audio.Sound.createAsync(track.source, { isLooping: true, shouldPlay: false })
    soundRef.current = sound
    await sound.setVolumeAsync(1)
    await sound.playAsync()
    jamStartedAtRef.current = Date.now()
    setIsJamming(true)
    startPulse()
  }, [selectedTrack, startPulse])

  const attemptStartJam = useCallback(async () => {
    if (busy || isJamming) return
    setBusy(true)
    setWebMicBlocked(false)
    histogramRef.current = createPitchClassHistogram()
    setScaleLabel('—')

    try {
      await startPitch((reading) => {
        histogramRef.current.add(reading)
        setScaleLabel(histogramRef.current.getBestLabel())
      })
    } catch (e) {
      if (Platform.OS === 'web') {
        setWebMicBlocked(true)
        setMicBannerKey((k) => k + 1)
        setBusy(false)
        return
      }
      const msg = e instanceof Error ? e.message : 'Could not open microphone'
      toast.error(msg)
      setBusy(false)
      return
    }

    try {
      await beginJamAfterMic()
    } catch (e) {
      await stopPitch()
      const msg = e instanceof Error ? e.message : 'Could not start backing track'
      toast.error(msg)
      stopPulse()
      setBusy(false)
      return
    }

    setBusy(false)
  }, [beginJamAfterMic, busy, isJamming, startPitch, stopPitch, stopPulse])

  const stopAndSave = useCallback(async () => {
    if (!isJamming || busy) return
    setBusy(true)
    stopPulse()

    const started = jamStartedAtRef.current
    const durationSec = started != null ? (Date.now() - started) / 1000 : 0
    jamStartedAtRef.current = null

    await stopPitch()

    const snd = soundRef.current
    soundRef.current = null
    if (snd) {
      try {
        await snd.stopAsync()
        await snd.unloadAsync()
      } catch {
        /* ignore */
      }
    }

    const hist = histogramRef.current
    const clientMap = hist.toScalePositionMap(durationSec)
    const inferred = hist.getBestLabel()
    const durationSeconds = Math.max(0, Math.floor(durationSec))

    let coachSummary: string
    let mergedMap: Record<string, number>

    try {
      const res = await submitJamScore({
        duration_seconds: durationSeconds,
        scale_position_map: clientMap,
        inferred_scale_label: inferred === '—' ? null : inferred,
        recording_wav_base64: '',
      })
      coachSummary = res.coach_summary
      mergedMap = { ...res.scale_position_map }
    } catch {
      coachSummary =
        'Could not reach the practice server. Your jam length and pitch map were still saved on this device.'
      mergedMap = { ...clientMap }
    }

    try {
      await insertJamSnapshotRow({
        id: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        date: new Date().toISOString(),
        duration_seconds: durationSeconds,
        scale_position_map: Object.keys(mergedMap).length > 0 ? mergedMap : clientMap,
        recurring_gestures: [],
        coach_summary: coachSummary,
      })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not save jam snapshot')
      setIsJamming(false)
      setScaleLabel('—')
      setBusy(false)
      return
    }

    setIsJamming(false)
    setScaleLabel('—')
    setBusy(false)
    toast.success('Jam saved.')
  }, [busy, isJamming, stopPitch, stopPulse])

  const retryMic = useCallback(() => {
    setWebMicBlocked(false)
    setMicBannerKey((k) => k + 1)
    void attemptStartJam()
  }, [attemptStartJam])

  return (
    <WoodGradient className="flex-1">
      <SafeAreaView className="flex-1" edges={['top', 'left', 'right']}>
        <ScrollView
          className="flex-1 px-5"
          contentContainerStyle={{ flexGrow: 1, justifyContent: 'space-between', paddingBottom: 24 }}
          showsVerticalScrollIndicator={false}
        >
          <View className="mt-6 mb-4">
            <Text className="mb-1 font-serif text-3xl text-cream">Jam Mode</Text>
            <Text className="font-sans text-sm text-muted-brown">No task. No score. Just play.</Text>
          </View>

          {webMicBlocked && Platform.OS === 'web' ? (
            <ErrorBanner
              key={`mic-${micBannerKey}`}
              dismissible={false}
              className="mb-4"
              {...toErrorBannerProps(mapBrowserMicBlockedForJam(), {
                onRetry: () => retryMic(),
                onDismiss: () => setWebMicBlocked(false),
                onOpenSettings: () => retryMic(),
                onContinue: () => setWebMicBlocked(false),
              })}
            />
          ) : null}

          {!isJamming && (
            <View className="mb-6 gap-2">
              <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wider text-muted-brown">
                Backing track
              </Text>
              {BACKING_TRACKS.map((track) => (
                <AnimatedPressable
                  key={track.id}
                  onPress={() => setSelectedTrack(track.id)}
                  haptic="light"
                  disabled={busy}
                  className={`flex-row items-center justify-between rounded-xl border p-4 ${
                    selectedTrack === track.id
                      ? 'border-amber-accent/40 bg-amber-accent/10'
                      : 'border-wood-700/50 bg-wood-800/40'
                  }`}
                >
                  <Text
                    className={`font-sans text-sm ${selectedTrack === track.id ? 'text-amber-light' : 'text-cream'}`}
                  >
                    {track.label}
                  </Text>
                  {track.bpm != null ? (
                    <Text className="font-mono text-xs text-muted-brown">{track.bpm} BPM</Text>
                  ) : (
                    <Text className="font-mono text-xs text-muted-brown">ambient</Text>
                  )}
                </AnimatedPressable>
              ))}
            </View>
          )}

          {isJamming && (
            <View className="min-h-[220px] flex-1 items-center justify-center gap-6">
              <Animated.View
                style={ringStyle}
                className="h-36 w-36 items-center justify-center rounded-full border-2 border-amber-accent/60"
              >
                <View className="h-28 w-28 items-center justify-center rounded-full border border-amber-accent/30 bg-amber-accent/10">
                  <Text className="text-center font-mono text-lg text-amber-accent" numberOfLines={2}>
                    {scaleLabel}
                  </Text>
                </View>
              </Animated.View>
              <Text className="font-sans text-sm text-muted-brown">Listening…</Text>
            </View>
          )}

          <View className="gap-3 pb-4">
            {isJamming ? (
              <AnimatedPressable
                onPress={() => void stopAndSave()}
                haptic="medium"
                disabled={busy}
                className="items-center rounded-xl border border-wood-600 bg-wood-700 py-4 disabled:opacity-50"
              >
                <Text className="font-sans-medium text-cream">{busy ? 'Saving…' : 'Stop & Save'}</Text>
              </AnimatedPressable>
            ) : (
              <AnimatedPressable
                onPress={() => void attemptStartJam()}
                haptic="medium"
                disabled={busy}
                className="items-center rounded-xl bg-amber-accent py-4 disabled:opacity-50"
              >
                <Text className="font-sans-medium text-base text-wood-900">
                  {busy ? 'Starting…' : 'Start Jamming'}
                </Text>
              </AnimatedPressable>
            )}
            <AnimatedPressable
              onPress={() => router.back()}
              haptic="light"
              className="items-center rounded-xl border border-wood-600/50 py-3"
            >
              <Text className="font-sans-medium text-sm text-cream">Back</Text>
            </AnimatedPressable>
          </View>
        </ScrollView>
      </SafeAreaView>
    </WoodGradient>
  )
}
