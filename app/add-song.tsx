import { Check, X } from 'lucide-react-native'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ActivityIndicator, Platform, Pressable, Text, TextInput, View } from 'react-native'
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AudioDropzone } from '@/components/AudioDropzone'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingSkeleton } from '@/components/LoadingSkeleton'
import { AnalyzePollCancelledError, pollAnalyzeJobCancelable, submitAnalyzeJob } from '@/src/api/analyze'
import colors from '@/src/constants/colors'
import type { MappedUiError } from '@/src/errors/mapErrorToUi'
import { mapAnalyzeFlowError, toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import { openHarmoniqAppSettings } from '@/src/errors/openHarmoniqAppSettings'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useRouter } from 'expo-router'
import { toast } from '@/components/ToastConfig'
import type { AnalyzeJobStatus } from '@/src/types'

type AddSongState = 'idle' | 'analyzing' | 'done' | 'error'

export default function AddSongScreen() {
  const router = useRouter()
  const saveLesson = useLessonStore((s) => s.saveLesson)
  const [url, setUrl] = useState('')
  const [uiState, setUiState] = useState<AddSongState>('idle')
  const [statusText, setStatusText] = useState('Waiting to start analysis…')
  const [analyzeError, setAnalyzeError] = useState<MappedUiError | null>(null)
  const startedAtRef = useRef(0)
  const cancelRef = useRef<(() => void) | null>(null)
  const aliveRef = useRef(true)
  const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const checkScale = useSharedValue(0.6)
  const checkOpacity = useSharedValue(0)
  const checkStyle = useAnimatedStyle(() => ({
    transform: [{ scale: checkScale.value }],
    opacity: checkOpacity.value,
  }))

  const canStartFromUrl = useMemo(() => url.trim().length > 0 && uiState !== 'analyzing', [uiState, url])

  const cancelInFlight = useCallback(() => {
    cancelRef.current?.()
    cancelRef.current = null
  }, [])

  useEffect(() => {
    return () => {
      aliveRef.current = false
      cancelInFlight()
      if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current)
    }
  }, [cancelInFlight])

  const runAnalyze = useCallback(
    async (input: { youtube_url?: string; file?: Blob; filename?: string }) => {
      setAnalyzeError(null)
      setUiState('analyzing')
      setStatusText('Submitting audio for analysis…')
      startedAtRef.current = Date.now()
      try {
        const jobId = await submitAnalyzeJob(input)
        if (!aliveRef.current) return
        setStatusText(`Job queued (${jobId.slice(0, 8)}…)`)
        const poll = pollAnalyzeJobCancelable(jobId, (job) => {
          if (!aliveRef.current) return
          const pretty: Record<AnalyzeJobStatus, string> = {
            processing: 'Analyzing structure and timing…',
            complete: 'Finishing lesson payload…',
            failed: 'Analysis failed.',
          }
          setStatusText(pretty[job.status] ?? `Status: ${job.status}`)
        })
        cancelRef.current = poll.cancel
        const lesson = await poll.promise
        if (!aliveRef.current) return
        const elapsed = Date.now() - startedAtRef.current
        const minWait = Math.max(0, 3000 - elapsed)
        if (minWait > 0) await new Promise((resolve) => setTimeout(resolve, minWait))
        if (!aliveRef.current) return
        saveLesson(lesson)
        setUiState('done')
        checkScale.value = withTiming(1, { duration: 280 })
        checkOpacity.value = withTiming(1, { duration: 220 })
        const songName = lesson.song_title?.trim() || 'Song'
        toast.success(`${songName} is ready.`)
        redirectTimerRef.current = setTimeout(() => {
          router.replace('/')
        }, 1000)
      } catch (error) {
        if (error instanceof AnalyzePollCancelledError) return
        if (!aliveRef.current) return
        setUiState('error')
        const elapsedMs = Date.now() - startedAtRef.current
        setAnalyzeError(
          mapAnalyzeFlowError(error, {
            usedYoutubeUrl: Boolean(input.youtube_url?.trim()),
            elapsedMs,
          }),
        )
      } finally {
        cancelRef.current = null
      }
    },
    [checkOpacity, checkScale, router, saveLesson],
  )

  const onClose = () => {
    aliveRef.current = false
    cancelInFlight()
    if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current)
    if (router.canGoBack()) router.back()
    else router.replace('/')
  }

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <View className="flex-1 px-6 py-6">
        <View className="flex-row items-center justify-between">
          <Text className="font-serif text-2xl text-cream">Add Song</Text>
          <Pressable onPress={onClose} accessibilityRole="button" accessibilityLabel="Close add song">
            <X color={colors.muted.brown} size={20} />
          </Pressable>
        </View>
        <Text className="mt-2 font-sans text-sm leading-6 text-muted-brown">
          Paste a YouTube URL or upload audio (web) to generate a lesson.
        </Text>

        <View className="mt-6 gap-2">
          <Text className="font-sans-medium text-sm text-cream">YouTube URL</Text>
          <TextInput
            value={url}
            onChangeText={setUrl}
            onSubmitEditing={() => {
              if (canStartFromUrl) void runAnalyze({ youtube_url: url.trim() })
            }}
            placeholder="https://www.youtube.com/watch?v=..."
            placeholderTextColor={colors.muted.brown}
            keyboardType="url"
            autoCapitalize="none"
            autoCorrect={false}
            editable={uiState !== 'analyzing'}
            className="rounded-xl border border-wood-600 bg-wood-800 px-4 py-3 font-sans text-sm text-cream"
          />
          <Pressable
            onPress={() => void runAnalyze({ youtube_url: url.trim() })}
            disabled={!canStartFromUrl}
            className="mt-1 rounded-lg bg-amber-accent px-4 py-3 disabled:opacity-40"
            accessibilityRole="button"
          >
            <Text className="text-center font-sans-medium text-wood-900">Analyze URL</Text>
          </Pressable>
        </View>

        {Platform.OS === 'web' ? (
          <View className="mt-8">
            <Text className="mb-2 font-sans-medium text-sm text-cream">Upload audio file (web)</Text>
            <AudioDropzone
              onFile={(file) => {
                if (uiState === 'analyzing') return
                void runAnalyze({
                  file,
                  filename: file instanceof File ? file.name : 'upload.mp3',
                })
              }}
            />
          </View>
        ) : null}

        {uiState === 'analyzing' ? (
          <View className="mt-8 gap-3">
            <View className="flex-row items-center gap-2">
              <ActivityIndicator color={colors.amber.accent} />
              <Text className="font-sans-medium text-sm text-cream">Analyzing…</Text>
            </View>
            <Text className="font-sans text-xs text-muted-brown">{statusText}</Text>
            <LoadingSkeleton width="100%" height={16} borderRadius={8} />
            <LoadingSkeleton width="78%" height={16} borderRadius={8} />
            <LoadingSkeleton width="100%" height={72} borderRadius={12} />
          </View>
        ) : null}

        {uiState === 'done' ? (
          <View className="mt-8 items-center rounded-xl border border-success/30 bg-success/10 px-4 py-5">
            <Animated.View style={checkStyle}>
              <Check color={colors.success} size={28} strokeWidth={2.4} />
            </Animated.View>
            <Text className="mt-2 font-sans-medium text-sm text-cream">Song ready.</Text>
            <Text className="mt-1 font-sans text-xs text-muted-brown">Taking you back to Home…</Text>
          </View>
        ) : null}

        {uiState === 'error' && analyzeError ? (
          <ErrorBanner
            className="mt-6"
            {...toErrorBannerProps(analyzeError, {
              onRetry: () => {
                setAnalyzeError(null)
                setUiState('idle')
              },
              onDismiss: () => {
                setAnalyzeError(null)
                setUiState('idle')
              },
              onOpenSettings: () => {
                void openHarmoniqAppSettings()
                setAnalyzeError(null)
                setUiState('idle')
              },
              onContinue: () => {
                setAnalyzeError(null)
                setUiState('idle')
              },
            })}
          />
        ) : null}
      </View>
    </SafeAreaView>
  )
}
