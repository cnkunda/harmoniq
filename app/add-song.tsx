import { Check, X } from 'lucide-react-native'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ActivityIndicator, Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native'
import Animated, {
    cancelAnimation,
    useAnimatedStyle,
    useSharedValue,
    withRepeat,
    withSequence,
    withTiming,
} from 'react-native-reanimated'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AudioDropzone } from '@/components/AudioDropzone'
import { ErrorBanner } from '@/components/ErrorBanner'
import { WoodGradient } from '@/components/WoodGradient'
import { toast } from '@/components/ToastConfig'
import {
    ANALYZE_MAX_PROCESSING_WALL_MS,
    AnalyzePollCancelledError,
    buildPlayerProfileFromSkillNodes,
    loadLearningContextFromPrefs,
    parseTasteProfileJson,
    pollAnalyzeJobCancelable,
    submitAnalyzeJob,
} from '@/src/api/analyze'
import { searchTabs, type TabSearchHit } from '@/src/api/tabs'
import colors from '@/src/constants/colors'
import { sessionEntryHrefWithMoodCheck } from '@/src/constants/sessionFlow'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
import type { MappedUiError } from '@/src/errors/mapErrorToUi'
import { mapAnalyzeFlowError, toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import { openHarmoniqAppSettings } from '@/src/errors/openHarmoniqAppSettings'
import { getAppPref } from '@/src/db/client'
import { PREF_TASTE_PROFILE_JSON } from '@/src/db/schema'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSkillStore } from '@/src/stores/skillStore'
import type { AnalyzeJob, AnalyzeJobStatus } from '@/src/types'
import { useRouter, type Href } from 'expo-router'

type AddSongState = 'idle' | 'analyzing' | 'done' | 'error'

type ImportTab = 'upload' | 'youtube' | 'search'

function formatElapsedClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${r.toString().padStart(2, '0')}`
}

export default function AddSongScreen() {
  const router = useRouter()
  const saveLesson = useLessonStore((s) => s.saveLesson)
  const lesson = useLessonStore((s) => s.lesson)
  const skillNodes = useSkillStore((s) => s.nodes)
  const loadSkillNodes = useSkillStore((s) => s.loadFromDb)
  const [url, setUrl] = useState('')
  const [uiState, setUiState] = useState<AddSongState>('idle')
  const [statusText, setStatusText] = useState('Waiting to start analysis…')
  const progressWidth = useSharedValue(0)
  const [analyzeError, setAnalyzeError] = useState<MappedUiError | null>(null)
  const startedAtRef = useRef(0)
  const cancelRef = useRef<(() => void) | null>(null)
  const aliveRef = useRef(true)
  const lastAnalyzeWasUploadRef = useRef(false)
  const [uploadDisplayTitle, setUploadDisplayTitle] = useState('')
  const [uploadDisplayArtist, setUploadDisplayArtist] = useState('')
  const [tabQuery, setTabQuery] = useState('')
  const [tabSearchBusy, setTabSearchBusy] = useState(false)
  const [tabHits, setTabHits] = useState<TabSearchHit[]>([])
  const [tabSearchError, setTabSearchError] = useState<string | null>(null)
  const [importTab, setImportTab] = useState<ImportTab>(Platform.OS === 'web' ? 'upload' : 'youtube')
  /** `null` = server has not reported numeric progress yet (indeterminate). */
  const [progressPercent, setProgressPercent] = useState<number | null>(null)
  const [elapsedTick, setElapsedTick] = useState(0)
  const processingStartedClockRef = useRef<number | null>(null)
  const [pendingUploadFile, setPendingUploadFile] = useState<Blob | null>(null)
  const [pendingUploadFilename, setPendingUploadFilename] = useState('')

  const elapsedAnalyzingSeconds = useMemo(() => {
    if (uiState !== 'analyzing') return 0
    const startSec = processingStartedClockRef.current ?? startedAtRef.current / 1000
    return Math.max(0, Date.now() / 1000 - startSec)
  }, [elapsedTick, uiState])

  const importTabOptions = useMemo(() => {
    const ordered: { id: ImportTab; label: string }[] = [
      { id: 'upload', label: 'Upload' },
      { id: 'youtube', label: 'YouTube' },
      { id: 'search', label: 'Search' },
    ]
    if (Platform.OS !== 'web') return ordered.filter((t) => t.id !== 'upload')
    return ordered
  }, [])

  const checkScale = useSharedValue(0.6)
  const checkOpacity = useSharedValue(0)
  const checkStyle = useAnimatedStyle(() => ({
    transform: [{ scale: checkScale.value }],
    opacity: checkOpacity.value,
  }))

  const progressBarStyle = useAnimatedStyle(() => ({
    width: `${Math.round(progressWidth.value * 100)}%`,
    minWidth: 4,
    height: '100%',
    borderRadius: 9999,
    backgroundColor: colors.amber.accent,
  }))

  const canStartFromUrl = useMemo(() => url.trim().length > 0 && uiState !== 'analyzing', [uiState, url])

  const canAnalyzePendingFile = useMemo(
    () => pendingUploadFile != null && uiState !== 'analyzing',
    [pendingUploadFile, uiState],
  )

  const cancelInFlight = useCallback(() => {
    cancelRef.current?.()
    cancelRef.current = null
  }, [])

  useEffect(() => {
    void loadSkillNodes()
  }, [loadSkillNodes])

  useEffect(() => {
    return () => {
      aliveRef.current = false
      cancelInFlight()
    }
  }, [cancelInFlight])

  useEffect(() => {
    if (uiState !== 'analyzing') return
    const id = setInterval(() => setElapsedTick((n) => n + 1), 500)
    return () => clearInterval(id)
  }, [uiState])

  useEffect(() => {
    if (importTab !== 'upload') {
      setPendingUploadFile(null)
      setPendingUploadFilename('')
    }
  }, [importTab])

  useEffect(() => {
    if (uiState !== 'analyzing') {
      cancelAnimation(progressWidth)
      return
    }
    if (progressPercent != null) return
    cancelAnimation(progressWidth)
    progressWidth.value = withRepeat(
      withSequence(
        withTiming(0.24, { duration: 900 }),
        withTiming(0.1, { duration: 900 }),
      ),
      -1,
      true,
    )
  }, [uiState, progressPercent, progressWidth])

  const runAnalyze = useCallback(
    async (input: { youtube_url?: string; file?: Blob; filename?: string }) => {
      lastAnalyzeWasUploadRef.current = Boolean(input.file)
      setAnalyzeError(null)
      setUiState('analyzing')
      setStatusText('Submitting audio for analysis…')
      progressWidth.value = 0
      setProgressPercent(null)
      processingStartedClockRef.current = null
      startedAtRef.current = Date.now()
      try {
        const [tasteRaw, learningCtx] = await Promise.all([
          getAppPref(PREF_TASTE_PROFILE_JSON),
          loadLearningContextFromPrefs(),
        ])
        const taste = parseTasteProfileJson(tasteRaw)
        const player_profile = buildPlayerProfileFromSkillNodes(skillNodes, taste, learningCtx)
        const jobId = await submitAnalyzeJob(
          player_profile != null ? { ...input, player_profile } : input,
        )
        if (!aliveRef.current) return
        if (input.file) {
          setPendingUploadFile(null)
          setPendingUploadFilename('')
        }
        setStatusText(`Job queued (${jobId.slice(0, 8)}…)`)
        const poll = pollAnalyzeJobCancelable(
          jobId,
          (job: AnalyzeJob) => {
            if (!aliveRef.current) return
            if (
              typeof job.processing_started_at === 'number' &&
              Number.isFinite(job.processing_started_at) &&
              job.processing_started_at > 0
            ) {
              processingStartedClockRef.current = job.processing_started_at
            } else if (processingStartedClockRef.current === null) {
              processingStartedClockRef.current = startedAtRef.current / 1000
            }
            const serverP =
              job.status === 'processing' && typeof job.progress === 'number' && Number.isFinite(job.progress)
                ? Math.max(0, Math.min(1, job.progress))
                : null
            if (job.status === 'complete') {
              cancelAnimation(progressWidth)
              progressWidth.value = withTiming(1, { duration: 240 })
              setProgressPercent(100)
            } else if (serverP != null) {
              cancelAnimation(progressWidth)
              progressWidth.value = withTiming(serverP, { duration: 240 })
              setProgressPercent(Math.round(serverP * 100))
            } else {
              setProgressPercent(null)
            }
            const stage =
              job.status === 'processing' && typeof job.stage_label === 'string' && job.stage_label.trim()
                ? job.stage_label.trim()
                : null
            const pretty: Record<AnalyzeJobStatus, string> = {
              processing: 'Working on your track…',
              complete: 'Finishing lesson payload…',
              failed: 'Analysis failed.',
            }
            setStatusText(stage ?? pretty[job.status] ?? `Status: ${job.status}`)
          },
          1100,
          {
            wallClockStartedAtMs: startedAtRef.current,
            maxProcessingWallMs: ANALYZE_MAX_PROCESSING_WALL_MS,
            onRecoverablePollError: () => {
              if (!aliveRef.current) return
              setStatusText('Connection issue — retrying status check…')
            },
          },
        )
        cancelRef.current = poll.cancel
        const lesson = await poll.promise
        if (!aliveRef.current) return
        const elapsed = Date.now() - startedAtRef.current
        const minWait = Math.max(0, 3000 - elapsed)
        if (minWait > 0) await new Promise((resolve) => setTimeout(resolve, minWait))
        if (!aliveRef.current) return
        saveLesson(lesson)
        if (input.file) {
          const rawName = typeof input.filename === 'string' && input.filename.trim() ? input.filename.trim() : 'upload'
          const baseTitle = rawName.replace(/\.[^.]+$/, '').trim() || 'Uploaded track'
          setUploadDisplayTitle(lesson.song_title?.trim() || baseTitle)
          setUploadDisplayArtist(typeof lesson.artist === 'string' ? lesson.artist.trim() : '')
        }
        setUiState('done')
        checkScale.value = withTiming(1, { duration: 280 })
        checkOpacity.value = withTiming(1, { duration: 220 })
        const songName = lesson.song_title?.trim() || 'Song'
        toast.success(`${songName} is ready.`)
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
    [checkOpacity, checkScale, progressWidth, saveLesson, skillNodes],
  )

  const onClose = () => {
    aliveRef.current = false
    cancelInFlight()
    if (router.canGoBack()) router.back()
    else router.replace('/')
  }

  const sectionCount = lesson?.sections?.length ?? 0
  const title = lesson?.song_title?.trim() || '(no title)'

  const continueToSession = useCallback(() => {
    if (!lesson) return
    if (lastAnalyzeWasUploadRef.current) {
      const t = uploadDisplayTitle.trim() || lesson.song_title?.trim() || 'Uploaded track'
      const a = uploadDisplayArtist.trim()
      saveLesson({
        ...lesson,
        song_title: t,
        artist: a.length > 0 ? a : lesson.artist,
      })
    }
    void sessionEntryHrefWithMoodCheck(useSessionPrefsStore.getState().skipTuneStep).then((href) =>
      router.push(href as Href),
    )
  }, [lesson, router, saveLesson, uploadDisplayArtist, uploadDisplayTitle])

  const subtitle =
    Platform.OS === 'web'
      ? 'Paste a YouTube URL, search the catalog, or upload an audio file.'
      : 'Paste a YouTube URL or search the catalog. File upload is available on web.'

  const pillsDisabled = uiState === 'analyzing'

  return (
    <WoodGradient variant="background" className="flex-1">
      <SafeAreaView className="flex-1" edges={['top', 'left', 'right', 'bottom']}>
        <ScrollView
          className="flex-1"
          contentContainerStyle={{
            flexGrow: 1,
            paddingBottom: 40,
            justifyContent: 'center',
          }}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View className="relative w-full max-w-2xl self-center px-8 py-8">
            <Pressable
              onPress={onClose}
              className="absolute right-0 top-0 z-10 min-h-[44px] min-w-[44px] items-center justify-center rounded-lg active:opacity-70"
              accessibilityRole="button"
              accessibilityLabel="Close add song"
              hitSlop={8}
            >
              <X color={colors.muted.brown} size={22} strokeWidth={2} />
            </Pressable>
            <Text
              className="px-12 text-center font-serif text-2xl text-cream"
              accessibilityRole="header"
            >
              Add Song
            </Text>
            <Text className="mt-4 max-w-lg self-center text-center font-sans text-sm leading-6 text-muted-brown">
              {subtitle}
            </Text>

            <View className="mt-10 w-full rounded-2xl border border-wood-700/50 bg-wood-800/40 p-8 shadow-soft-wood">
              <Text className="mb-4 text-center font-sans-medium text-[11px] uppercase tracking-[0.12em] text-muted-brown">
                Import source
              </Text>
              <View className="flex-row flex-wrap items-end justify-center gap-3">
                {importTabOptions.map((opt) => {
                  const selected = importTab === opt.id
                  const isSearch = opt.id === 'search'
                  return (
                    <View key={opt.id} className={isSearch ? 'items-center' : undefined}>
                      {isSearch ? (
                        <View className="mb-1 rounded-full bg-wood-700 px-2 py-0.5">
                          <Text className="font-sans-medium text-[10px] uppercase tracking-wide text-amber-light">
                            Preview
                          </Text>
                        </View>
                      ) : null}
                      <Pressable
                        onPress={() => setImportTab(opt.id)}
                        disabled={pillsDisabled}
                        accessibilityRole="tab"
                        accessibilityState={{ selected, disabled: pillsDisabled }}
                        accessibilityLabel={isSearch ? `${opt.label}, preview catalog` : opt.label}
                        className={`min-h-[44px] justify-center rounded-full px-5 ${selected ? 'bg-wood-700' : 'border border-wood-600/70 bg-wood-900/30'} ${pillsDisabled ? 'opacity-50' : ''}`}
                      >
                        <Text
                          className={`text-center font-sans-medium text-sm ${selected ? 'text-amber-light' : 'text-muted-brown'}`}
                        >
                          {opt.label}
                        </Text>
                      </Pressable>
                    </View>
                  )
                })}
              </View>

              <View className="mt-6 border-t border-wood-600/35 pt-7">
                {importTab === 'upload' && Platform.OS === 'web' ? (
                  <View className="gap-4">
                    <Text className="text-center font-sans-medium text-xs uppercase tracking-wide text-amber-light">
                      Audio file
                    </Text>
                    <Text className="text-center font-sans text-xs leading-5 text-muted-brown">
                      Drag and drop or click to choose MP3, WAV, or M4A. Tap Analyze file when you&apos;re ready.
                    </Text>
                    <AudioDropzone
                      onFile={(file) => {
                        if (uiState === 'analyzing') return
                        setPendingUploadFile(file)
                        setPendingUploadFilename(file instanceof File ? file.name : 'upload.mp3')
                      }}
                    />
                    {pendingUploadFilename ? (
                      <Text className="text-center font-sans text-sm leading-5 text-cream" numberOfLines={2}>
                        <Text className="text-muted-brown">Selected </Text>
                        <Text className="font-sans-medium text-cream">{pendingUploadFilename}</Text>
                      </Text>
                    ) : null}
                    <Pressable
                      onPress={() => {
                        if (!pendingUploadFile || uiState === 'analyzing') return
                        void runAnalyze({
                          file: pendingUploadFile,
                          filename: pendingUploadFilename || 'upload.mp3',
                        })
                      }}
                      disabled={!canAnalyzePendingFile}
                      className="min-h-[48px] justify-center rounded-xl bg-amber-accent px-4 py-3 disabled:opacity-40"
                      accessibilityRole="button"
                      accessibilityLabel="Analyze selected audio file"
                    >
                      <Text className="text-center font-sans-medium text-base text-wood-900">Analyze file</Text>
                    </Pressable>
                  </View>
                ) : null}

                {importTab === 'youtube' ? (
                  <View className="gap-4">
                    <Text className="text-center font-sans-medium text-xs uppercase tracking-wide text-amber-light">
                      YouTube URL
                    </Text>
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
                      className="min-h-[48px] rounded-xl border border-wood-500/80 bg-ivory px-4 py-3 font-sans text-sm text-wood-900"
                    />
                    <Pressable
                      onPress={() => void runAnalyze({ youtube_url: url.trim() })}
                      disabled={!canStartFromUrl}
                      className="min-h-[48px] justify-center rounded-xl bg-amber-accent px-4 py-3 disabled:opacity-40"
                      accessibilityRole="button"
                      accessibilityLabel="Analyze YouTube URL"
                    >
                      <Text className="text-center font-sans-medium text-base text-wood-900">Analyze URL</Text>
                    </Pressable>
                  </View>
                ) : null}

                {importTab === 'search' ? (
                  <View className="gap-3">
                    <Text className="text-center font-sans-medium text-xs uppercase tracking-wide text-amber-light">
                      Tab catalog
                    </Text>
                    <Text className="text-center font-sans text-xs leading-5 text-muted-brown">
                      Server-side stub only — no files are downloaded. A licensed catalog API can replace this later.
                    </Text>
                    <View className="mt-1 flex-row gap-3">
                      <TextInput
                        value={tabQuery}
                        onChangeText={setTabQuery}
                        placeholder="Song or artist…"
                        placeholderTextColor={colors.muted.brown}
                        editable={!tabSearchBusy && uiState !== 'analyzing'}
                        className="min-h-12 flex-1 rounded-xl border border-wood-600 bg-wood-900 px-4 py-3 font-sans text-sm text-cream"
                      />
                      <Pressable
                        onPress={() => {
                          setTabSearchError(null)
                          setTabSearchBusy(true)
                          void searchTabs(tabQuery)
                            .then((res) => setTabHits(res.hits))
                            .catch((e) =>
                              setTabSearchError(e instanceof Error ? e.message : 'Search failed. Is the API running?'),
                            )
                            .finally(() => setTabSearchBusy(false))
                        }}
                        disabled={tabSearchBusy || tabQuery.trim().length === 0 || uiState === 'analyzing'}
                        className="min-h-12 min-w-[88px] justify-center rounded-xl bg-wood-700 px-4 disabled:opacity-40"
                        accessibilityRole="button"
                        accessibilityLabel="Search tab catalog"
                      >
                        <Text className="text-center font-sans-medium text-sm text-amber-light">
                          {tabSearchBusy ? '…' : 'Search'}
                        </Text>
                      </Pressable>
                    </View>
                    {tabSearchError ? (
                      <Text
                        className="mt-1 text-center font-sans text-xs leading-5 text-danger"
                        accessibilityLiveRegion="polite"
                      >
                        {tabSearchError}
                      </Text>
                    ) : null}
                    {tabHits.length > 0 ? (
                      <View className="mt-4 gap-2">
                        {tabHits.map((h) => (
                          <View
                            key={h.id}
                            className="rounded-xl border border-wood-600/50 bg-wood-900/60 px-4 py-3"
                          >
                            <Text className="font-sans-medium text-sm text-cream">{h.title}</Text>
                            {h.artist ? (
                              <Text className="mt-1 font-sans text-xs text-muted-brown">{h.artist}</Text>
                            ) : null}
                            <Text className="mt-2 font-sans text-[10px] uppercase tracking-wide text-muted-brown">
                              {h.source} · {h.id}
                            </Text>
                          </View>
                        ))}
                      </View>
                    ) : null}
                  </View>
                ) : null}
              </View>
            </View>

        {uiState === 'analyzing' ? (
          <View className="mt-8 w-full gap-4 rounded-2xl border border-wood-700/40 bg-wood-800/30 p-6">
            <View className="flex-row items-center justify-center gap-2">
              <ActivityIndicator color={colors.amber.accent} />
              <Text className="font-sans-medium text-sm text-cream">Analyzing…</Text>
            </View>
            <Text
              className="text-center font-sans-medium text-sm leading-6 text-cream"
              accessibilityLiveRegion="polite"
            >
              {statusText}
            </Text>
            <Text className="text-center font-mono text-xs text-amber-light/90">
              Elapsed {formatElapsedClock(elapsedAnalyzingSeconds)}
            </Text>
            <View className="flex-row items-center gap-3">
              <View className="h-2.5 flex-1 overflow-hidden rounded-full bg-wood-800">
                <Animated.View style={progressBarStyle} />
              </View>
              <Text
                className="min-w-[52px] text-right font-sans-medium tabular-nums text-xs text-amber-light"
                accessibilityLabel={
                  progressPercent != null ? `Progress ${progressPercent} percent` : 'Progress indeterminate'
                }
              >
                {progressPercent != null ? `${progressPercent}%` : '—'}
              </Text>
            </View>
            <Text className="text-center font-sans text-[11px] leading-4 text-muted-brown">
              Usually 1–4 minutes. The bar fills when the practice server reports real stages — long separation or
              transcription steps can take a few minutes without moving the percentage.
            </Text>
          </View>
        ) : null}

        {uiState === 'done' ? (
          <View className="mt-8 items-center rounded-2xl border border-success/30 bg-success/10 px-6 py-6">
            <Animated.View style={checkStyle}>
              <Check color={colors.success} size={28} strokeWidth={2.4} />
            </Animated.View>
            <Text className="mt-3 text-center font-sans-medium text-sm text-cream">Song ready</Text>
            <Text className="mt-2 max-w-sm text-center font-sans text-xs leading-5 text-muted-brown">
              Review details below, then continue when you&apos;re ready.
            </Text>
          </View>
        ) : null}

        {uiState === 'done' && lesson ? (
          <View className="mt-6 rounded-2xl border border-wood-600 bg-wood-800 p-6">
            <Text className="text-center font-sans-medium text-sm text-amber-light">Lesson result</Text>
            {lastAnalyzeWasUploadRef.current ? (
              <View className="mt-4 gap-4">
                <Text className="text-center font-sans text-xs leading-5 text-muted-brown">
                  File uploads don&apos;t include embedded artist or title. Add them so your library stays organized.
                </Text>
                <View>
                  <Text className="mb-1.5 font-sans-medium text-xs uppercase tracking-wide text-amber-light/90">
                    Song title
                  </Text>
                  <TextInput
                    value={uploadDisplayTitle}
                    onChangeText={setUploadDisplayTitle}
                    placeholder="Song title"
                    placeholderTextColor={colors.muted.brown}
                    className="min-h-[44px] rounded-xl border border-wood-600 bg-wood-900 px-4 py-3 font-sans text-sm text-cream"
                  />
                </View>
                <View>
                  <Text className="mb-1.5 font-sans-medium text-xs uppercase tracking-wide text-amber-light/90">
                    Artist
                  </Text>
                  <TextInput
                    value={uploadDisplayArtist}
                    onChangeText={setUploadDisplayArtist}
                    placeholder="Artist (optional)"
                    placeholderTextColor={colors.muted.brown}
                    className="min-h-[44px] rounded-xl border border-wood-600 bg-wood-900 px-4 py-3 font-sans text-sm text-cream"
                  />
                </View>
              </View>
            ) : (
              <Text className="mt-4 text-center font-sans text-sm text-cream">
                Title: <Text className="font-sans-medium">{title}</Text>
              </Text>
            )}
            <Text className="mt-3 text-center font-sans text-sm text-cream">
              Sections: <Text className="font-sans-medium">{sectionCount}</Text>
            </Text>
            <Pressable
              onPress={continueToSession}
              className="mt-6 min-h-[48px] justify-center rounded-xl bg-amber-accent px-4 py-3"
              accessibilityRole="button"
            >
              <Text className="text-center font-sans-medium text-base text-wood-900">Continue to session</Text>
            </Pressable>
            <Pressable
              onPress={() => router.replace('/')}
              className="mt-3 min-h-[48px] justify-center rounded-xl border border-wood-600/60 bg-wood-900/50 px-4 py-3"
              accessibilityRole="button"
            >
              <Text className="text-center font-sans-medium text-base text-cream">Back to Home</Text>
            </Pressable>
          </View>
        ) : null}

        {uiState === 'error' && analyzeError ? (
          <ErrorBanner
            className="mt-6 w-full"
            onDismissed={() => {
              setAnalyzeError(null)
              setUiState('idle')
            }}
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
        </ScrollView>
      </SafeAreaView>
    </WoodGradient>
  )
}
