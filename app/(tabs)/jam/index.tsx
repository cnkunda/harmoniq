import { Asset } from 'expo-asset'
import { Audio, type AVPlaybackStatus } from 'expo-av'
import { useLocalSearchParams, useRouter, type Href } from 'expo-router'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ActivityIndicator, Platform, ScrollView, Text, TextInput, View } from 'react-native'
import Animated, {
    cancelAnimation,
    useAnimatedStyle,
    useSharedValue,
    withRepeat,
    withTiming,
} from 'react-native-reanimated'
import { SafeAreaView } from 'react-native-safe-area-context'
import { History } from 'lucide-react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { Button } from '@/components/Button'
import { ErrorBanner } from '@/components/ErrorBanner'
import { FretboardDiagram } from '@/components/FretboardDiagram'
import { JamSummaryModal, type JamSummaryStatus } from '@/components/JamSummaryModal'
import { TabViewport } from '@/components/TabViewport'
import { toast } from '@/components/ToastConfig'
import { WoodGradient } from '@/components/WoodGradient'
import {
    ApiError,
    buildPlayerProfileFromSkillNodes,
    loadLearningContextFromPrefs,
    parseTasteProfileJson,
    submitJamScore,
} from '@/src/api/analyze'
import {
  createJamBackingJob,
  getJamBackingJob,
  JAM_BACKING_JOB_POLL_MS,
  resolveJamBackingSource,
  type JamBackingResponseBody,
  type JamBackingSourceInfo,
  type JamPersonaChoice,
  type JamPhraseMetrics,
  type JamSummaryBundle,
} from '@/src/api/jam'
import { emit } from '@/src/analytics/eventBus'
import { BACKING_TRACKS, type BackingTrackDefinition, type BackingTrackId } from '@/src/constants/backingTracks'
import { getAllSkillNodes, getAppPref, insertJamSnapshotRow } from '@/src/db/client'
import { PREF_TASTE_PROFILE_JSON } from '@/src/db/schema'
import { mapBrowserMicBlockedForJam, toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import { prepareJamBackingPlayable } from '@/src/jam/jamBackingPlayable'
import { coachFromPhraseFeatures } from '@/src/jam/jamPhraseCoach'
import { phraseToFeatures } from '@/src/jam/jamPhraseFeatures'
import { createJamPhraseSegmenter } from '@/src/jam/jamPhraseSegmenter'
import { JAM_REFERENCE_TAB_GP5_BASE64 } from '@/src/jam/jamReferenceTabGp5Base64'
import { buildJamPracticeHref, resolveJamPracticeTrack } from '@/src/jam/jamPracticeTrack'
import { pickSuggestedClassicFromWeakAreas } from '@/src/jam/jamSuggestedClassic'
import {
  loadJamPersonaChoice,
  requestJamSummary,
  runJamSummary,
  saveJamPersonaChoice,
} from '@/src/jam/jamSummaryRunner'
import { normalizeExternalAudioSrcForTabHarness } from '@/src/jam/normalizeJamTabAudioUri'
import { deriveLessonBed, type LessonBed } from '@/src/jam/lessonBed'
import { PROGRESSION_PRESETS, parseProgressionInput } from '@/src/jam/progression'
import { createPitchClassHistogram, type BestScaleMatch } from '@/src/jam/pitchClassHistogram'
import { usePitchStream } from '@/src/pitch/usePitchStream'
import { completePracticePlanSlot } from '@/src/session/planProgress'
import { useFretboardTuner } from '@/src/session/useFretboardTuner'
import { useDnaStore } from '@/src/stores/dnaStore'
import { useTabContentInset } from '@/src/layout/useTabContentInset'
import { useLessonStore } from '@/src/stores/lessonStore'
import { usePlanStore } from '@/src/stores/planStore'
import {
    buildFretboardShareUrl,
    readFretboardShareStateFromLocation,
    type FretboardOverlayMode,
} from '@/src/utils/fretboardShareState'
import type { AlphaTabSurfaceRef } from '@/types/tabMessage'
import { colors } from '@/src/constants/colors'

const SCALE_UI_INTERVAL_MS = 2000
const AI_INSTRUMENTAL_TRACK_ID = 'ai-instrumental'
const KEY_ROOTS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const
const JAM_STYLES = ['blues', 'jazz', 'fingerpicking', 'rock', 'ambient'] as const
const JAM_BPM_PRESETS = [60, 70, 80, 90, 100, 120] as const
const JAM_DURATION_PRESETS = [16, 32, 48] as const
type InferenceConfidence = 'low' | 'medium' | 'high'
type BackingMode = 'classic' | 'ai'

function confidenceFromMatchScore(score: number): InferenceConfidence {
  if (score >= 0.72) return 'high'
  if (score >= 0.5) return 'medium'
  return 'low'
}

export default function JamScreen() {
  const tabInset = useTabContentInset()
  const router = useRouter()
  const { start: startPitch, stop: stopPitch } = usePitchStream()

  const [isJamming, setIsJamming] = useState(false)
  const [backingMode, setBackingMode] = useState<BackingMode>('classic')
  const [aiBackingSource, setAiBackingSource] = useState<JamBackingSourceInfo | null>(null)
  const [aiBackingPending, setAiBackingPending] = useState(false)
  const [aiKeyRoot, setAiKeyRoot] = useState<string>('A')
  const [aiKeyMode, setAiKeyMode] = useState<'major' | 'minor'>('minor')
  const [aiBpm, setAiBpm] = useState(70)
  const [aiStyle, setAiStyle] = useState<string>('blues')
  const [aiDurationSec, setAiDurationSec] = useState(16)
  const [progressionText, setProgressionText] = useState('')
  const [lessonBed, setLessonBed] = useState<LessonBed | null>(null)
  const [classicTrackId, setClassicTrackId] = useState<BackingTrackId>(BACKING_TRACKS[0].id)
  const [weakAreas, setWeakAreas] = useState<readonly string[]>([])
  const [scaleLabel, setScaleLabel] = useState('—')
  const [scalePitchClasses, setScalePitchClasses] = useState<readonly number[] | null>(null)
  const [scaleRootPitchClass, setScaleRootPitchClass] = useState<number | null>(null)
  const [topScales, setTopScales] = useState<BestScaleMatch[]>([])
  const [overlayMode, setOverlayMode] = useState<FretboardOverlayMode>('off')
  const [selectedNote, setSelectedNote] = useState<{ string?: number; fret?: number; midi?: number } | null>(null)
  const [fretPulseKey, setFretPulseKey] = useState(0)
  const [scaleUiGeneration, setScaleUiGeneration] = useState(0)
  const [jamTabReady, setJamTabReady] = useState(false)
  /** AlphaTab external-media URL (web blob/local asset URL; native file URL for WebView harness). */
  const [jamTabExternalAudioSrc, setJamTabExternalAudioSrc] = useState<string | null>(null)
  const [webMicBlocked, setWebMicBlocked] = useState(false)
  const [micBannerKey, setMicBannerKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [personaChoice, setPersonaChoice] = useState<JamPersonaChoice>('encouraging')
  const [summaryModal, setSummaryModal] = useState<{
    status: JamSummaryStatus
    bundle: JamSummaryBundle | null
    coachSummary: string
    phrases: JamPhraseMetrics[]
    track: BackingTrackDefinition | null
  } | null>(null)
  const [lastJamDiagnostics, setLastJamDiagnostics] = useState<{
    inferredScale: string | null
    confidence: 'low' | 'medium' | 'high'
    tags: string[]
    summaryBundle: JamSummaryBundle | null
  } | null>(null)

  const pulse = useSharedValue(1)
  const ringStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pulse.value }],
    opacity: 0.5 + (pulse.value - 1) * 3,
  }))

  const soundRef = useRef<Audio.Sound | null>(null)
  const jamAiPlaybackReleaseRef = useRef<(() => void) | null>(null)
  const jamBackingJobRef = useRef<string | null>(null)
  const aiBackingMetaRef = useRef<{
    source: 'classic' | 'ai'
    key: string
    bpm: number | null
    progression: string[]
    prompt: string | null
    provider: string | null
    durationMs: number | null
  } | null>(null)
  const jamBackingPollRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastAiPromptRef = useRef<string | null>(null)
  const histogramRef = useRef(createPitchClassHistogram())
  const jamBackingPositionRef = useRef(0)
  const jamBpmRef = useRef<number | null>(null)
  const phraseSegmenterRef = useRef<ReturnType<typeof createJamPhraseSegmenter> | null>(null)
  const accumulatedPhrasesRef = useRef<JamPhraseMetrics[]>([])
  const prevPhraseEndMsRef = useRef<number | null>(null)
  const [phraseCoachLines, setPhraseCoachLines] = useState({ observation: '', suggestion: '' })
  /** Monotonic phrase segmentation clock (starts when mic opens). */
  const jamPhraseClockStartRef = useRef<number | null>(null)
  const jamStartedAtRef = useRef<number | null>(null)
  const jamStemTabRef = useRef<AlphaTabSurfaceRef>(null)
  const jamLastStemPlayingRef = useRef(false)
  const lastScaleUiAtRef = useRef(0)
  const lastScaleTintRef = useRef<{ rootMidi: number; intervals: readonly number[] } | null>(null)
  const summaryRunIdRef = useRef(0)
  const classicTrackDef = BACKING_TRACKS.find((t) => t.id === classicTrackId) ?? BACKING_TRACKS[0]
  const lessonForBed = useLessonStore((s) => s.lesson)
  const lessonSectionIndexForBed = useLessonStore((s) => s.lessonSectionIndex)
  const jamParams = useLocalSearchParams<{
    fromLesson?: string
    sectionIndex?: string
    targetRate?: string
    loopBars?: string
  }>()

  useEffect(() => {
    if (jamParams.fromLesson !== '1' || !lessonForBed) return
    const raw = Number(jamParams.sectionIndex ?? lessonSectionIndexForBed)
    const idx = Number.isFinite(raw) ? Math.max(0, Math.trunc(raw)) : lessonSectionIndexForBed
    const bed = deriveLessonBed(lessonForBed as never, idx)
    setLessonBed(bed)
    setAiKeyRoot(bed.keyRoot)
    setAiKeyMode(bed.keyMode)
    if (bed.bpm != null) setAiBpm(bed.bpm)
    setProgressionText(bed.progression.join(' '))
    setBackingMode('ai')
  }, [jamParams.fromLesson, jamParams.sectionIndex, lessonForBed, lessonSectionIndexForBed])

  const aiProgression = useMemo(() => parseProgressionInput(progressionText), [progressionText])
  const jamDisplayKey = backingMode === 'ai' ? `${aiKeyRoot} ${aiKeyMode}` : classicTrackDef.key
  const jamDisplayBpm = backingMode === 'ai' ? aiBpm : classicTrackDef.bpm
  jamBpmRef.current = jamDisplayBpm ?? null
  const activeJamTrackSource =
    backingMode === 'ai'
      ? aiBackingPending
        ? 'Generating · bundled loop playing'
        : aiBackingSource?.usedFallback
          ? `Bundled fallback${aiBackingSource.fallbackTrack ? ` · ${aiBackingSource.fallbackTrack}` : ''}`
          : `AI instrumental · ${aiBackingSource?.provider ?? 'server'}`
      : 'Offline loop (bundled)'
  const { state: tunerState, toggleTuner, startCalibration } = useFretboardTuner()

  const currentPlan = usePlanStore((s) => s.currentPlan)
  const currentSlotIndex = usePlanStore((s) => s.currentSlotIndex)
  /** Final plan step is often `free_jam`; SessionChromeBar only covers `/session/*`, so we surface completion here. */
  const activePlanJamSlot = useMemo(() => {
    const slots = currentPlan?.slots
    if (!slots?.length) return null
    const slot = slots[currentSlotIndex]
    return slot?.slot_type === 'free_jam' ? slot : null
  }, [currentPlan?.slots, currentSlotIndex])
  const isFinalPlanStep = currentSlotIndex === (currentPlan?.slots?.length ?? 0) - 1

  useEffect(() => {
    const seg = createJamPhraseSegmenter({
      onPhraseClosed: (phrase) => {
        const f = phraseToFeatures(phrase, jamBpmRef.current)
        const lines = coachFromPhraseFeatures(phrase, f)
        if (!lines.observation && !lines.suggestion) return
        setPhraseCoachLines(lines)
        const pcs = phrase.notes.map((n) => {
          const pc = ((n.midi % 12) + 12) % 12
          return ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][pc]!
        })
        const uniquePcs = [...new Set(pcs)]
        const beatOffsetSec = f.meanBeatOffsetSec
        accumulatedPhrasesRef.current.push({
          duration_ms: Math.max(0, phrase.endTime - phrase.startTime),
          notes_per_second: f.notesPerSecond,
          unique_pitch_classes: f.uniquePitchClasses,
          midi_span: f.midiSpan,
          contour: f.contour,
          beat_offset_mean: beatOffsetSec != null ? beatOffsetSec * 1000 : undefined,
          beat_offset_std:
            f.beatOffsetVarianceSec2 != null ? Math.sqrt(f.beatOffsetVarianceSec2) * 1000 : undefined,
          home_pitch_class: uniquePcs[0] ?? null,
          note_count: phrase.notes.length,
          intonation_cents: f.meanAbsCents,
          start_ms: phrase.startTime,
          end_ms: phrase.endTime,
          backing_start_ms: f.backingStartMs,
          backing_end_ms: f.backingEndMs,
          transition_from: accumulatedPhrasesRef.current.length > 0
            ? accumulatedPhrasesRef.current[accumulatedPhrasesRef.current.length - 1]!.home_pitch_class ?? null
            : null,
          transition_gap_ms:
            prevPhraseEndMsRef.current != null
              ? phrase.startTime - prevPhraseEndMsRef.current
              : undefined,
        })
        prevPhraseEndMsRef.current = phrase.endTime
      },
    })
    phraseSegmenterRef.current = seg
    return () => {
      seg.reset()
      phraseSegmenterRef.current = null
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    void Promise.all([
      getAllSkillNodes(),
      getAppPref(PREF_TASTE_PROFILE_JSON),
      loadLearningContextFromPrefs(),
    ]).then(([nodes, tasteRaw, learningCtx]) => {
      if (cancelled) return
      const taste = parseTasteProfileJson(tasteRaw)
      const profile = buildPlayerProfileFromSkillNodes(nodes, taste, learningCtx)
      const wa = profile?.weak_areas ?? []
      setWeakAreas(wa)
      setClassicTrackId(pickSuggestedClassicFromWeakAreas(wa))
    })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    loadJamPersonaChoice()
      .then((choice) => {
        if (!cancelled) setPersonaChoice(choice)
      })
      .catch((e) => console.warn('[Jam] could not load summary persona', e))
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const shared = readFretboardShareStateFromLocation()
    if (!shared) return
    setOverlayMode(shared.overlay)
    setScalePitchClasses(shared.scalePitchClasses ?? null)
    setScaleRootPitchClass(shared.rootPitchClass ?? null)
    if (shared.selected) {
      setSelectedNote({ string: shared.selected.string, fret: shared.selected.fret })
      setFretPulseKey((k) => k + 1)
    }
  }, [])

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
      summaryRunIdRef.current += 1
      cancelAnimation(pulse)
      pulse.value = 1
      void stopPitch()
      const s = soundRef.current
      if (s) {
        s.setOnPlaybackStatusUpdate(null)
        void s.stopAsync().catch(() => {})
        void s.unloadAsync().catch(() => {})
        soundRef.current = null
      }
      jamAiPlaybackReleaseRef.current?.()
      jamAiPlaybackReleaseRef.current = null
      setJamTabExternalAudioSrc(null)
      jamBackingJobRef.current = null
      if (jamBackingPollRef.current != null) clearTimeout(jamBackingPollRef.current)
    }
  }, [pulse, stopPitch])

  useEffect(() => {
    if (!isJamming || !jamTabReady) return
    const tab = jamStemTabRef.current
    const cmd = lastScaleTintRef.current
    if (cmd) {
      tab?.highlightScaleDegrees(cmd.rootMidi, [...cmd.intervals])
    } else {
      tab?.clearScaleHighlight()
    }
  }, [isJamming, jamTabReady, scaleUiGeneration])

  const syncJamTabFromPlaybackStatus = useCallback((status: AVPlaybackStatus) => {
    if (!status.isLoaded) return
    const tab = jamStemTabRef.current
    tab?.syncPlaybackTimelineMs((status.positionMillis ?? 0) + 50)
    const playing = Boolean(status.isPlaying)
    if (playing !== jamLastStemPlayingRef.current) {
      jamLastStemPlayingRef.current = playing
      tab?.setStemPlaybackActive(playing)
    }
  }, [])

  const handleJamPlaybackStatus = useCallback(
    (status: AVPlaybackStatus) => {
      if (status.isLoaded) {
        jamBackingPositionRef.current = status.positionMillis ?? 0
      }
      syncJamTabFromPlaybackStatus(status)
    },
    [syncJamTabFromPlaybackStatus],
  )

  const onJamTabError = useCallback((msg: string) => {
    toast.error(msg)
  }, [])

  const onJamTabReady = useCallback(() => {
    setJamTabReady(true)
    const snd = soundRef.current
    if (!snd) return
    void snd.getStatusAsync().then((st) => {
      if (!st.isLoaded) return
      syncJamTabFromPlaybackStatus(st)
    })
  }, [syncJamTabFromPlaybackStatus])

  const cancelJamBackingPolling = useCallback(() => {
    jamBackingJobRef.current = null
    if (jamBackingPollRef.current != null) {
      clearTimeout(jamBackingPollRef.current)
      jamBackingPollRef.current = null
    }
  }, [])

  const hotSwapJamBacking = useCallback(
    async (res: JamBackingResponseBody) => {
      const prepared = await prepareJamBackingPlayable(res.audio_base64, res.mime_type)
      const old = soundRef.current
      const oldPos = jamBackingPositionRef.current
      const { sound: next } = await Audio.Sound.createAsync(
        { uri: prepared.uri },
        { isLooping: true, shouldPlay: false, volume: 0 },
      )
      next.setOnPlaybackStatusUpdate(handleJamPlaybackStatus)
      try {
        const cap = typeof res.duration_ms === 'number' && res.duration_ms > 0 ? res.duration_ms : oldPos
        await next.setPositionAsync(Math.max(0, Math.min(oldPos, cap)))
      } catch {
        /* start from 0 when position restore is unavailable */
      }
      await next.playAsync()
      if (old) {
        for (let i = 1; i <= 6; i += 1) {
          const v = i / 6
          await old.setVolumeAsync(1 - v).catch(() => {})
          await next.setVolumeAsync(v).catch(() => {})
          await new Promise((resolve) => setTimeout(resolve, 100))
        }
        old.setOnPlaybackStatusUpdate(null)
        await old.stopAsync().catch(() => {})
        await old.unloadAsync().catch(() => {})
      }
      jamAiPlaybackReleaseRef.current?.()
      jamAiPlaybackReleaseRef.current = prepared.release
      soundRef.current = next
      setJamTabExternalAudioSrc(normalizeExternalAudioSrcForTabHarness(prepared.uri))
    },
    [handleJamPlaybackStatus],
  )

  const pollJamBackingJob = useCallback(
    async (jobId: string) => {
      const startedAt = Date.now()
      while (jamBackingJobRef.current === jobId && Date.now() - startedAt < 8 * 60 * 1000) {
        await new Promise((resolve) => setTimeout(resolve, JAM_BACKING_JOB_POLL_MS))
        if (jamBackingJobRef.current !== jobId) return
        try {
          const job = await getJamBackingJob(jobId)
          if (job.status === 'complete' && job.result) {
            await hotSwapJamBacking(job.result)
            lastAiPromptRef.current = job.result.prompt_used
            const info = resolveJamBackingSource(job.result)
            aiBackingMetaRef.current = {
              source: info.usedFallback ? 'classic' : 'ai',
              key: `${aiKeyRoot} ${aiKeyMode}`,
              bpm: aiBpm,
              progression: [...aiProgression],
              prompt: job.result.prompt_used,
              provider: info.provider,
              durationMs: job.result.duration_ms ?? null,
            }
            setAiBackingSource(info)
            setAiBackingPending(false)
            return
          }
          if (job.status === 'failed') {
            setAiBackingPending(false)
            aiBackingMetaRef.current = {
              source: 'classic',
              key: `${aiKeyRoot} ${aiKeyMode}`,
              bpm: aiBpm,
              progression: [...aiProgression],
              prompt: null,
              provider: 'bundled',
              durationMs: null,
            }
            setAiBackingSource({ provider: 'bundled', usedFallback: true, fallbackTrack: null })
            toast.info('AI bed unavailable — staying on the bundled loop.')
            return
          }
        } catch {
          /* transient poll failure; keep trying until the deadline */
        }
      }
      setAiBackingPending(false)
    },
    [hotSwapJamBacking],
  )

  useEffect(() => {
    if (!isJamming) {
      setJamTabReady(false)
      jamLastStemPlayingRef.current = false
      jamAiPlaybackReleaseRef.current?.()
      jamAiPlaybackReleaseRef.current = null
      cancelJamBackingPolling()
      setAiBackingPending(false)
    }
  }, [cancelJamBackingPolling, isJamming])

  const beginJamAfterMic = useCallback(async () => {
    await Audio.setAudioModeAsync({
      allowsRecordingIOS: true,
      playsInSilentModeIOS: true,
      staysActiveInBackground: false,
      shouldDuckAndroid: true,
      playThroughEarpieceAndroid: false,
    })

    const pendingUriCleanup: (() => void)[] = []
    let source: number | { uri: string }
    let tabHarnessAudioSrc: string | null = null
    if (backingMode === 'ai') {
      // Start instantly on the bundled loop; the generated bed hot-swaps in when ready.
      const asset = Asset.fromModule(classicTrackDef.source)
      await asset.downloadAsync()
      const resolved = asset.localUri ?? asset.uri
      if (!resolved) {
        throw new Error('Could not resolve classic backing URL for tab sync.')
      }
      tabHarnessAudioSrc = normalizeExternalAudioSrcForTabHarness(resolved)
      source = Platform.OS === 'web' ? { uri: resolved } : classicTrackDef.source
      lastAiPromptRef.current = null
      aiBackingMetaRef.current = {
        source: 'ai',
        key: `${aiKeyRoot} ${aiKeyMode}`,
        bpm: aiBpm,
        progression: [...aiProgression],
        prompt: null,
        provider: null,
        durationMs: null,
      }
      cancelJamBackingPolling()
      setAiBackingSource({ provider: 'bundled', usedFallback: true, fallbackTrack: null })
      setAiBackingPending(true)
    } else {
      lastAiPromptRef.current = null
      aiBackingMetaRef.current = {
        source: 'classic',
        key: classicTrackDef.key,
        bpm: classicTrackDef.bpm ?? null,
        progression: [],
        prompt: null,
        provider: 'bundled',
        durationMs: null,
      }
      setAiBackingSource(null)
      const asset = Asset.fromModule(classicTrackDef.source)
      await asset.downloadAsync()
      const resolved = asset.localUri ?? asset.uri
      if (!resolved) {
        throw new Error('Could not resolve classic backing URL for tab sync.')
      }
      tabHarnessAudioSrc = normalizeExternalAudioSrcForTabHarness(resolved)
      source = Platform.OS === 'web' ? { uri: resolved } : classicTrackDef.source
    }

    if (tabHarnessAudioSrc) {
      setJamTabExternalAudioSrc(tabHarnessAudioSrc)
    }

    try {
      const { sound } = await Audio.Sound.createAsync(source, { isLooping: true, shouldPlay: false })
      jamAiPlaybackReleaseRef.current = pendingUriCleanup.length > 0 ? pendingUriCleanup[0]! : null
      pendingUriCleanup.length = 0
      soundRef.current = sound
      jamLastStemPlayingRef.current = false
      sound.setOnPlaybackStatusUpdate(handleJamPlaybackStatus)
      await sound.setVolumeAsync(1)
      await sound.playAsync()
      jamStartedAtRef.current = Date.now()
      setIsJamming(true)
      startPulse()
      if (backingMode === 'ai') {
        try {
          const created = await createJamBackingJob({
            musical_key: `${aiKeyRoot} ${aiKeyMode}`,
            bpm: aiBpm,
            style_hint: aiStyle,
            duration_secs: aiDurationSec,
            chord_progression: aiProgression,
            weak_areas: [...weakAreas],
          })
          jamBackingJobRef.current = created.job_id
          void pollJamBackingJob(created.job_id)
        } catch {
          setAiBackingPending(false)
          toast.info('AI bed unavailable — using the bundled loop.')
        }
      }
    } catch (err) {
      setJamTabExternalAudioSrc(null)
      for (const fn of pendingUriCleanup) {
        fn()
      }
      pendingUriCleanup.length = 0
      throw err
    }
  }, [
    aiBpm,
    aiDurationSec,
    aiKeyMode,
    aiKeyRoot,
    aiProgression,
    aiStyle,
    backingMode,
    cancelJamBackingPolling,
    classicTrackDef.source,
    handleJamPlaybackStatus,
    pollJamBackingJob,
    startPulse,
    weakAreas,
  ])

  const attemptStartJam = useCallback(async () => {
    if (busy || isJamming) return
    summaryRunIdRef.current += 1
    setSummaryModal(null)
    setBusy(true)
    setWebMicBlocked(false)
    phraseSegmenterRef.current?.reset()
    accumulatedPhrasesRef.current = []
    prevPhraseEndMsRef.current = null
    setPhraseCoachLines({ observation: '', suggestion: '' })
    jamPhraseClockStartRef.current = Date.now()
    histogramRef.current = createPitchClassHistogram()
    setScaleLabel('—')
    setScalePitchClasses(null)
    setScaleRootPitchClass(null)
    setTopScales([])
    lastScaleUiAtRef.current = 0
    lastScaleTintRef.current = null
    jamStemTabRef.current?.clearScaleHighlight()

    try {
      await startPitch((reading) => {
        const phraseT0 = jamPhraseClockStartRef.current
        if (phraseT0 != null) {
          phraseSegmenterRef.current?.push(reading, Date.now() - phraseT0, jamBackingPositionRef.current)
        }
        histogramRef.current.add(reading)
        const now = Date.now()
        if (now - lastScaleUiAtRef.current < SCALE_UI_INTERVAL_MS) return
        lastScaleUiAtRef.current = now
        const scale = histogramRef.current.getBestScale()
        const candidates = histogramRef.current.getBestScales(3)
        const label = scale ? scale.label : histogramRef.current.getBestLabel()
        setScaleLabel(label)
        setTopScales(candidates)
        setScalePitchClasses(scale?.pitchClasses ?? null)
        setScaleRootPitchClass(scale ? ((Math.round(scale.rootMidi) % 12) + 12) % 12 : null)
        if (scale) {
          lastScaleTintRef.current = { rootMidi: scale.rootMidi, intervals: scale.intervals }
        } else {
          lastScaleTintRef.current = null
        }
        setScaleUiGeneration((g) => g + 1)
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
      setJamTabExternalAudioSrc(null)
      jamAiPlaybackReleaseRef.current?.()
      jamAiPlaybackReleaseRef.current = null
      cancelJamBackingPolling()
      setAiBackingPending(false)
      lastAiPromptRef.current = null
      if (e instanceof ApiError) {
        if (e.status === 503) {
          toast.error(
            'AI backing needs a music-generation provider on the practice server. Choose a classic loop or install/configure a provider.',
          )
        } else {
          toast.error(e.message || 'Could not generate backing track')
        }
      } else {
        const msg = e instanceof Error ? e.message : 'Could not start backing track'
        toast.error(msg)
      }
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
    const phraseT0 = jamPhraseClockStartRef.current
    if (phraseT0 != null) {
      phraseSegmenterRef.current?.flush(Date.now() - phraseT0)
    }
    jamPhraseClockStartRef.current = null
    jamStartedAtRef.current = null

    await stopPitch()
    cancelJamBackingPolling()
    setAiBackingPending(false)

    const snd = soundRef.current
    soundRef.current = null
    if (snd) {
      try {
        snd.setOnPlaybackStatusUpdate(null)
        await snd.stopAsync()
        await snd.unloadAsync()
      } catch (e) {
        console.warn('[Jam] stem stop failed:', e)
      }
    }
    jamLastStemPlayingRef.current = false
    jamStemTabRef.current?.setStemPlaybackActive(false)
    setJamTabExternalAudioSrc(null)

    const hist = histogramRef.current
    const pitchClassWeightMap = hist.toScalePositionMap(durationSec)
    const bestScale = hist.getBestScale()
    const inferred = bestScale ? bestScale.label : hist.getBestLabel()
    const inferredMode = bestScale?.inferred_mode ?? null
    const inferenceConfidence = bestScale ? confidenceFromMatchScore(bestScale.matchScore) : ('low' as const)
    const localTags: string[] = []
    if (durationSec < 10) localTags.push('signal_short_window')
    if (Object.keys(pitchClassWeightMap).length < 3 && durationSec >= 10) localTags.push('map_sparse')
    if (bestScale && inferenceConfidence === 'high') localTags.push('high_confidence_scale_match')
    histogramRef.current = createPitchClassHistogram()
    setScalePitchClasses(null)
    setScaleRootPitchClass(null)
    lastScaleTintRef.current = null
    lastScaleUiAtRef.current = 0
    jamStemTabRef.current?.clearScaleHighlight()
    const durationSeconds = Math.max(0, Math.floor(durationSec))

    let coachSummary: string
    let mergedPitchMap: Record<string, number>
    let mergedPositionMap: Record<string, number>
    let reliabilityTags: string[] = [...localTags]
    let reliabilityConfidence: 'low' | 'medium' | 'high' = inferenceConfidence
    let reliabilitySignalQuality: number | null = null

    const trackIdForSave = backingMode === 'ai' ? AI_INSTRUMENTAL_TRACK_ID : classicTrackDef.id
    const promptSnap = lastAiPromptRef.current
    const trackLabelForSave =
      backingMode === 'ai'
        ? `AI · ${promptSnap ? `${promptSnap.slice(0, 100)}${promptSnap.length > 100 ? '…' : ''}` : 'instrumental'}`
        : classicTrackDef.label

    try {
      const res = await submitJamScore({
        duration_seconds: durationSeconds,
        pitch_class_weight_map: pitchClassWeightMap,
        position_weight_map: {},
        scale_position_map: pitchClassWeightMap,
        inferred_scale_label: inferred === '—' ? null : inferred,
        inference_confidence: inferenceConfidence,
        inferred_mode: inferredMode,
        track_id: trackIdForSave,
        track_label: trackLabelForSave,
        track_key: jamDisplayKey,
        track_bpm: jamDisplayBpm,
        recording_wav_base64: '',
      })
      coachSummary = res.coach_summary
      mergedPitchMap = {
        ...(res.pitch_class_weight_map ?? {}),
        ...((res.scale_position_map ?? {}) as Record<string, number>),
      }
      mergedPositionMap = { ...(res.position_weight_map ?? {}) }
      reliabilityTags = Array.from(new Set([...(res.reliability_tags ?? []), ...localTags]))
      reliabilityConfidence = res.reliability?.confidence ?? inferenceConfidence
      reliabilitySignalQuality =
        typeof res.reliability?.signal_quality === 'number' && Number.isFinite(res.reliability.signal_quality)
          ? res.reliability.signal_quality
          : null
    } catch {
      coachSummary =
        'Could not reach the practice server. Your jam length and pitch map were still saved on this device.'
      mergedPitchMap = { ...pitchClassWeightMap }
      mergedPositionMap = {}
    }

    const phrases = accumulatedPhrasesRef.current
    accumulatedPhrasesRef.current = []
    prevPhraseEndMsRef.current = null
    const hasPhrases = phrases.length > 0
    const phrasesJson = hasPhrases ? JSON.stringify(phrases) : null
    const summaryStatus: JamSummaryStatus = hasPhrases ? 'pending' : 'skipped'
    const snapshotId = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
    const practiceTrack = resolveJamPracticeTrack({
      trackId: trackIdForSave,
      trackKey: jamDisplayKey,
      trackBpm: jamDisplayBpm,
    })

    try {
      await insertJamSnapshotRow({
        id: snapshotId,
        date: new Date().toISOString(),
        duration_seconds: durationSeconds,
        scale_position_map: Object.keys(mergedPitchMap).length > 0 ? mergedPitchMap : pitchClassWeightMap,
        pitch_class_weight_map: Object.keys(mergedPitchMap).length > 0 ? mergedPitchMap : pitchClassWeightMap,
        position_weight_map: mergedPositionMap,
        inferred_scale_label: inferred === '—' ? null : inferred,
        inferred_mode: inferredMode,
        inference_confidence: inferenceConfidence,
        track_id: trackIdForSave,
        track_label: trackLabelForSave,
        track_key: jamDisplayKey,
        track_bpm: jamDisplayBpm,
        backing_source: aiBackingMetaRef.current?.source ?? (backingMode === 'ai' ? 'ai' : 'classic'),
        backing_key: aiBackingMetaRef.current?.key ?? jamDisplayKey,
        backing_bpm: aiBackingMetaRef.current?.bpm ?? jamDisplayBpm,
        backing_progression: aiBackingMetaRef.current?.progression ?? [],
        backing_prompt: aiBackingMetaRef.current?.prompt ?? lastAiPromptRef.current,
        backing_provider: aiBackingMetaRef.current?.provider ?? null,
        backing_duration_ms: aiBackingMetaRef.current?.durationMs ?? null,
        reliability_tags: reliabilityTags,
        reliability_confidence: reliabilityConfidence,
        reliability_signal_quality: reliabilitySignalQuality,
        recurring_gestures: [],
        coach_summary: coachSummary,
        summary_bundle_json: null,
        phrases_json: phrasesJson,
        summary_status: summaryStatus,
      })
      emit({
        type: 'jam_complete',
        payload: {
          duration_sec: durationSeconds,
          track_id: trackIdForSave,
          track_label: trackLabelForSave,
          inferred_scale_label: inferred === '—' ? null : inferred,
        },
      })
      void useDnaStore.getState().refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not save jam snapshot')
      setIsJamming(false)
      setScaleLabel('—')
      setScalePitchClasses(null)
      setScaleRootPitchClass(null)
      setBusy(false)
      return
    }

    setIsJamming(false)
    setScaleLabel('—')
    setScalePitchClasses(null)
    setScaleRootPitchClass(null)
    setTopScales([])
    setLastJamDiagnostics({
      inferredScale: inferred === '—' ? null : inferred,
      confidence: reliabilityConfidence,
      tags: reliabilityTags,
      summaryBundle: null,
    })
    setSummaryModal({
      status: summaryStatus,
      bundle: null,
      coachSummary,
      phrases,
      track: practiceTrack,
    })
    setBusy(false)
    toast.success('Jam saved.')
    lastAiPromptRef.current = null

    if (hasPhrases) {
      const runId = ++summaryRunIdRef.current
      const request = requestJamSummary({
        duration_seconds: durationSeconds,
        pitch_class_weight_map: mergedPitchMap,
        inferred_scale_label: inferred === '—' ? null : inferred,
        inference_confidence: inferenceConfidence,
        track_id: trackIdForSave,
        track_label: trackLabelForSave,
        track_key: jamDisplayKey,
        track_bpm: jamDisplayBpm,
        phrases,
        personaChoice,
        weak_areas: weakAreas,
      })
      void runJamSummary(snapshotId, request, coachSummary)
        .then((bundle) => {
          if (runId !== summaryRunIdRef.current) return
          setSummaryModal((prev) =>
            prev
              ? {
                  ...prev,
                  status: 'ready',
                  bundle,
                  coachSummary: bundle.coach_summary || prev.coachSummary,
                }
              : prev,
          )
          setLastJamDiagnostics((prev) => (prev ? { ...prev, summaryBundle: bundle } : prev))
        })
        .catch(() => {
          if (runId !== summaryRunIdRef.current) return
          setSummaryModal((prev) => (prev ? { ...prev, status: 'failed' } : prev))
        })
    }
  }, [
    backingMode,
    busy,
    classicTrackDef.id,
    classicTrackDef.label,
    isJamming,
    jamDisplayBpm,
    jamDisplayKey,
    personaChoice,
    stopPitch,
    stopPulse,
    weakAreas,
  ])

  const retryMic = useCallback(() => {
    setWebMicBlocked(false)
    setMicBannerKey((k) => k + 1)
    void attemptStartJam()
  }, [attemptStartJam])

  const copyShareLink = useCallback(() => {
    if (typeof window === 'undefined') {
      toast.error('Share links are available on web.')
      return
    }
    const url = buildFretboardShareUrl({
      version: 1,
      overlay: overlayMode,
      selected:
        selectedNote?.string != null && selectedNote?.fret != null
          ? { string: Math.round(selectedNote.string), fret: Math.max(0, Math.round(selectedNote.fret)) }
          : null,
      scalePitchClasses: scalePitchClasses ? [...scalePitchClasses] : null,
      rootPitchClass: scaleRootPitchClass,
    })
    if (!url) {
      toast.error('Could not build share link.')
      return
    }
    const writer = globalThis.navigator?.clipboard?.writeText?.bind(globalThis.navigator.clipboard)
    if (!writer) {
      toast.error('Clipboard not available in this browser.')
      return
    }
    void writer(url).then(
      () => toast.success('Jam share link copied.'),
      () => toast.error('Clipboard access blocked.'),
    )
  }, [overlayMode, scalePitchClasses, scaleRootPitchClass, selectedNote])

  const changePersona = useCallback((choice: JamPersonaChoice) => {
    setPersonaChoice(choice)
    void saveJamPersonaChoice(choice).catch((e) => {
      console.warn('[Jam] could not save summary persona', e)
      toast.error('Could not save the summary style on this device.')
    })
  }, [])

  const practicePhrase = useCallback(
    (phraseIndex: number, startMs: number | null | undefined, endMs: number | null | undefined) => {
      const track = summaryModal?.track
      if (!track || startMs == null || endMs == null || endMs <= startMs) {
        toast.error('This phrase has no matching backing loop.')
        return
      }
      setSummaryModal(null)
      router.push(
        buildJamPracticeHref({
          trackId: track.id,
          startMs,
          endMs,
          phraseIndex,
        }),
      )
    },
    [router, summaryModal?.track],
  )

  const toggleFretboardTuner = useCallback(() => {
    void toggleTuner().catch((e) => {
      const message = e instanceof Error ? e.message : String(e)
      toast.error(message === 'MIC_PERMISSION_DENIED' ? 'Microphone permission is required for tuning.' : message)
    })
  }, [toggleTuner])

  return (
    <WoodGradient className="flex-1">
      <SafeAreaView className="flex-1" edges={['top', 'left', 'right']}>
        <ScrollView
          className="flex-1 px-5"
          contentContainerStyle={{ flexGrow: 1, paddingBottom: tabInset }}
          showsVerticalScrollIndicator={false}
        >
          <View className="mt-3 mb-2">
            <View className="flex-row items-start justify-between">
              <View className="flex-1 pr-3">
                <Text className="mb-0.5 font-serif text-3xl text-cream">Jam Mode</Text>
                <Text className="font-sans-medium text-sm text-cream">{classicTrackDef.label}</Text>
                <Text className="mt-0.5 font-sans text-xs text-cream/80">
                  {activeJamTrackSource}
                  {jamDisplayBpm != null ? ` · ${jamDisplayBpm} BPM` : ' · ambient'}
                  {jamDisplayKey ? ` · ${jamDisplayKey}` : ''}
                </Text>
                {weakAreas.length > 0 ? (
                  <Text className="mt-1 font-sans text-xs text-amber-light/90">
                    Focus: {weakAreas.join(', ')}
                  </Text>
                ) : null}
              </View>
              <Button
                label="History"
                variant="secondary"
                size="sm"
                icon={<History color={colors.amber.light} size={16} />}
                haptic="light"
                onPress={() => router.push('/(tabs)/jam/history' as Href)}
                accessibilityLabel="Open jam history"
              />
            </View>

            <View className="mt-3 rounded-xl border border-wood-700/45 bg-wood-800/40 px-3 py-2.5">
              <Text className="font-sans-medium text-xs uppercase tracking-wider text-muted-brown">
                Summary style
              </Text>
              <View className="mt-2 flex-row gap-2">
                <Button
                  label="Encouraging coach"
                  variant={personaChoice === 'encouraging' ? 'primary' : 'secondary'}
                  size="sm"
                  haptic="light"
                  onPress={() => changePersona('encouraging')}
                  accessibilityLabel="Encouraging coach summary style"
                  containerClassName="flex-1"
                />
                <Button
                  label="Technical analyst"
                  variant={personaChoice === 'technical' ? 'primary' : 'secondary'}
                  size="sm"
                  haptic="light"
                  onPress={() => changePersona('technical')}
                  accessibilityLabel="Technical analyst summary style"
                  containerClassName="flex-1"
                />
              </View>
            </View>
          </View>

          {activePlanJamSlot != null && currentPlan?.slots?.length ? (
            <View className="mb-2 rounded-xl border border-amber-accent/40 bg-amber-accent/12 px-3 py-2">
              <Text className="font-sans-medium text-sm text-cream">
                Practice plan · {currentSlotIndex + 1} of {currentPlan.slots.length}
                {activePlanJamSlot.title?.trim() ? ` · ${activePlanJamSlot.title.trim()}` : ''}
              </Text>
              <Text className="mt-1 font-sans text-xs leading-snug text-muted-light">
                {isFinalPlanStep
                  ? 'This is the last section in your plan. When you are done jamming, complete the session to clear the plan and go home.'
                  : 'When you are done jamming, continue to the next section in your plan.'}
              </Text>
              <AnimatedPressable haptic="light"
                onPress={() => {
                  void completePracticePlanSlot({
                    router,
                    deps: {
                      saveLesson: useLessonStore.getState().saveLesson,
                      setLessonSectionIndex: useLessonStore.getState().setLessonSectionIndex,
                    },
                    slotIndex: currentSlotIndex,
                    performance: null,
                  }).catch((e: unknown) => {
                    toast.error(e instanceof Error ? e.message : 'Could not continue the practice plan.')
                  })
                }}
                className="mt-3 min-h-[48px] justify-center rounded-xl bg-amber-accent px-4 py-3"
                accessibilityRole="button"
                accessibilityLabel={isFinalPlanStep ? 'Complete practice session and return home' : 'Go to next section in practice plan'}
              >
                <Text className="text-center font-sans-medium text-base text-wood-900">
                  {isFinalPlanStep ? 'Complete session' : 'Next section'}
                </Text>
              </AnimatedPressable>
            </View>
          ) : null}

          {lessonBed ? (
            <View className="mb-3 rounded-xl border border-amber-accent/35 bg-amber-accent/10 px-3 py-2">
              <View className="flex-row items-start justify-between gap-3">
                <View className="flex-1">
                  <Text className="font-sans-medium text-sm text-cream">
                    Lesson bed · {lessonBed.songTitle}
                    {lessonBed.sectionLabel ? ` · ${lessonBed.sectionLabel}` : ''}
                  </Text>
                  <Text className="mt-0.5 font-sans text-xs text-muted-light">
                    Key, tempo and progression prefilled from your song.
                    {jamParams.targetRate ? ` Target speed ${Math.round(Number(jamParams.targetRate) * 100)}%.` : ''}
                    {jamParams.loopBars ? ` Loop ${jamParams.loopBars} bars.` : ''}
                    {' '}Adjust below, then start jamming.
                  </Text>
                </View>
                <AnimatedPressable
                  onPress={() => setLessonBed(null)}
                  haptic="light"
                  className="rounded-lg border border-wood-600/40 bg-wood-900/40 px-2.5 py-1.5"
                  accessibilityRole="button"
                  accessibilityLabel="Clear lesson bed context"
                >
                  <Text className="font-sans text-[10px] text-muted-light">Clear</Text>
                </AnimatedPressable>
              </View>
            </View>
          ) : null}

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
            <View className="mb-3 gap-3">
              {/* Backing Source Section */}
              <View className="gap-1">
                <Text className="font-sans-medium text-xs uppercase tracking-wider text-amber-light">
                  Backing Source
                </Text>
                <View className="mt-1 gap-2">
                  <AnimatedPressable
                    onPress={() => setBackingMode('classic')}
                    haptic="light"
                    disabled={busy}
                    className={`flex-row items-center justify-between rounded-xl border p-4 ${
                      backingMode === 'classic'
                        ? 'border-amber-accent/40 bg-amber-accent/10'
                        : 'border-wood-700/50 bg-wood-800/40'
                    }`}
                  >
                    <View className="flex-1 pr-2">
                      <Text className={`font-sans text-sm ${backingMode === 'classic' ? 'text-amber-light' : 'text-cream'}`}>
                        Offline loop (bundled MP3)
                      </Text>
                      <Text className="mt-0.5 font-sans text-xs text-muted-light">
                        Works fully offline — no practice server required
                      </Text>
                    </View>
                  </AnimatedPressable>
                  <AnimatedPressable
                    onPress={() => setBackingMode('ai')}
                    haptic="light"
                    disabled={busy}
                    className={`flex-row items-center justify-between rounded-xl border p-4 ${
                      backingMode === 'ai'
                        ? 'border-amber-accent/40 bg-amber-accent/10'
                        : 'border-wood-700/50 bg-wood-800/40'
                    }`}
                  >
                    <View className="flex-1 pr-2">
                      <Text className={`font-sans text-sm ${backingMode === 'ai' ? 'text-amber-light' : 'text-cream'}`}>
                        AI instrumental (server)
                      </Text>
                      <Text className="mt-0.5 font-sans text-xs text-muted-light">
                        Generates a fresh bed from the key, tempo, style and progression you choose below
                      </Text>
                    </View>
                    {busy && backingMode === 'ai' ? <ActivityIndicator color={colors.amber.light} /> : null}
                  </AnimatedPressable>
                </View>
              </View>

              {/* Loop Style Section */}
              <View className="gap-1">
                <Text className="font-sans-medium text-xs uppercase tracking-wider text-amber-light">
                  Loop Style
                </Text>
                <Text className="font-sans text-xs text-muted-brown">
                  {backingMode === 'ai'
                    ? 'AI template from key / BPM'
                    : 'Bundled MP3 loop'}
                </Text>
                <View className="mt-1 gap-2">
                  {BACKING_TRACKS.map((track) => {
                    const templateActive = backingMode === 'ai' && classicTrackId === track.id
                    const classicActive = backingMode === 'classic' && classicTrackId === track.id
                    return (
                      <AnimatedPressable
                        key={track.id}
                        onPress={() => setClassicTrackId(track.id)}
                        haptic="light"
                        disabled={busy}
                        className={`flex-row items-center justify-between rounded-xl border p-4 ${
                          classicActive
                            ? 'border-amber-accent/40 bg-amber-accent/10'
                            : templateActive
                              ? 'border-cream/25 bg-wood-800/60'
                              : 'border-wood-700/50 bg-wood-800/40'
                        }`}
                      >
                        <View className="flex-1 pr-2">
                          <Text
                            className={`font-sans text-sm ${classicActive || templateActive ? 'text-amber-light' : 'text-cream'}`}
                          >
                            {track.label}
                          </Text>
                          {templateActive && backingMode === 'ai' ? (
                            <Text className="mt-0.5 font-sans text-xs text-muted-light">AI template · key / tempo</Text>
                          ) : null}
                        </View>
                        {track.bpm != null ? (
                          <Text className="font-mono text-xs text-muted-light">{track.bpm} BPM</Text>
                        ) : (
                          <Text className="font-mono text-xs text-muted-light">ambient</Text>
                        )}
                      </AnimatedPressable>
                    )
                  })}
                </View>
              </View>

              {backingMode === 'ai' ? (
                <View className="gap-1">
                  <Text className="font-sans-medium text-xs uppercase tracking-wider text-amber-light">
                    Bed settings
                  </Text>
                  <Text className="font-sans text-xs text-muted-brown">
                    Drives the generated bed: key, tempo, style, length, progression.
                  </Text>
                  <View className="mt-1 gap-3 rounded-xl border border-wood-700/50 bg-wood-800/40 p-3">
                    <View>
                      <Text className="mb-1.5 font-sans-medium text-sm text-cream">Key</Text>
                      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                        <View className="flex-row gap-1.5">
                          {KEY_ROOTS.map((root) => {
                            const active = aiKeyRoot === root
                            return (
                              <AnimatedPressable
                                key={`key-${root}`}
                                onPress={() => setAiKeyRoot(root)}
                                haptic="light"
                                disabled={busy}
                                className={`rounded-lg border px-3 py-2 ${
                                  active ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/40 bg-wood-900/40'
                                }`}
                                accessibilityRole="button"
                                accessibilityState={{ selected: active }}
                                accessibilityLabel={`Key root ${root}`}
                              >
                                <Text className={`font-mono text-xs ${active ? 'text-cream' : 'text-muted-light'}`}>{root}</Text>
                              </AnimatedPressable>
                            )
                          })}
                        </View>
                      </ScrollView>
                      <View className="mt-1.5 flex-row gap-1.5">
                        {(['major', 'minor'] as const).map((mode) => {
                          const active = aiKeyMode === mode
                          return (
                            <AnimatedPressable
                              key={`mode-${mode}`}
                              onPress={() => setAiKeyMode(mode)}
                              haptic="light"
                              disabled={busy}
                              className={`flex-1 rounded-lg border px-3 py-2 ${
                                active ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/40 bg-wood-900/40'
                              }`}
                              accessibilityRole="button"
                              accessibilityState={{ selected: active }}
                              accessibilityLabel={`${mode} mode`}
                            >
                              <Text className={`text-center font-sans text-xs capitalize ${active ? 'text-cream' : 'text-muted-light'}`}>
                                {mode}
                              </Text>
                            </AnimatedPressable>
                          )
                        })}
                      </View>
                    </View>

                    <View>
                      <Text className="mb-1.5 font-sans-medium text-sm text-cream">Tempo</Text>
                      <View className="flex-row flex-wrap gap-1.5">
                        {JAM_BPM_PRESETS.map((bpm) => {
                          const active = aiBpm === bpm
                          return (
                            <AnimatedPressable
                              key={`bpm-${bpm}`}
                              onPress={() => setAiBpm(bpm)}
                              haptic="light"
                              disabled={busy}
                              className={`rounded-lg border px-3 py-2 ${
                                active ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/40 bg-wood-900/40'
                              }`}
                              accessibilityRole="button"
                              accessibilityState={{ selected: active }}
                              accessibilityLabel={`${bpm} beats per minute`}
                            >
                              <Text className={`font-mono text-xs ${active ? 'text-cream' : 'text-muted-light'}`}>{bpm}</Text>
                            </AnimatedPressable>
                          )
                        })}
                      </View>
                    </View>

                    <View>
                      <Text className="mb-1.5 font-sans-medium text-sm text-cream">Style</Text>
                      <View className="flex-row flex-wrap gap-1.5">
                        {JAM_STYLES.map((style) => {
                          const active = aiStyle === style
                          return (
                            <AnimatedPressable
                              key={`style-${style}`}
                              onPress={() => setAiStyle(style)}
                              haptic="light"
                              disabled={busy}
                              className={`rounded-lg border px-3 py-2 ${
                                active ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/40 bg-wood-900/40'
                              }`}
                              accessibilityRole="button"
                              accessibilityState={{ selected: active }}
                              accessibilityLabel={`${style} style`}
                            >
                              <Text className={`font-sans text-xs capitalize ${active ? 'text-cream' : 'text-muted-light'}`}>{style}</Text>
                            </AnimatedPressable>
                          )
                        })}
                      </View>
                    </View>

                    <View>
                      <Text className="mb-1.5 font-sans-medium text-sm text-cream">Length</Text>
                      <View className="flex-row gap-1.5">
                        {JAM_DURATION_PRESETS.map((secs) => {
                          const active = aiDurationSec === secs
                          return (
                            <AnimatedPressable
                              key={`dur-${secs}`}
                              onPress={() => setAiDurationSec(secs)}
                              haptic="light"
                              disabled={busy}
                              className={`flex-1 rounded-lg border px-3 py-2 ${
                                active ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/40 bg-wood-900/40'
                              }`}
                              accessibilityRole="button"
                              accessibilityState={{ selected: active }}
                              accessibilityLabel={`${secs} seconds`}
                            >
                              <Text className={`text-center font-mono text-xs ${active ? 'text-cream' : 'text-muted-light'}`}>{secs}s</Text>
                            </AnimatedPressable>
                          )
                        })}
                      </View>
                    </View>

                    <View>
                      <Text className="mb-1.5 font-sans-medium text-sm text-cream">Progression (optional)</Text>
                      <TextInput
                        value={progressionText}
                        onChangeText={setProgressionText}
                        editable={!busy}
                        placeholder="Am F C G"
                        placeholderTextColor={colors.muted.brown}
                        className="rounded-lg border border-wood-600/40 bg-wood-900/40 px-3 py-2 font-mono text-sm text-cream"
                        accessibilityLabel="Chord progression input"
                      />
                      <View className="mt-1.5 flex-row flex-wrap gap-1.5">
                        {PROGRESSION_PRESETS.map((preset) => (
                          <AnimatedPressable
                            key={`prog-${preset.label}`}
                            onPress={() => setProgressionText(preset.text)}
                            haptic="light"
                            disabled={busy}
                            className="rounded-lg border border-wood-600/40 bg-wood-900/40 px-2.5 py-1.5"
                            accessibilityRole="button"
                            accessibilityLabel={`Use ${preset.label} progression`}
                          >
                            <Text className="font-sans text-[10px] text-muted-light">{preset.label}</Text>
                          </AnimatedPressable>
                        ))}
                        {progressionText ? (
                          <AnimatedPressable
                            onPress={() => setProgressionText('')}
                            haptic="light"
                            disabled={busy}
                            className="rounded-lg border border-danger/40 bg-danger/10 px-2.5 py-1.5"
                            accessibilityRole="button"
                            accessibilityLabel="Clear progression"
                          >
                            <Text className="font-sans text-[10px] text-danger">Clear</Text>
                          </AnimatedPressable>
                        ) : null}
                      </View>
                      {aiProgression.length > 0 ? (
                        <View className="mt-1.5 flex-row flex-wrap gap-1">
                          {aiProgression.map((chord, index) => (
                            <View
                              key={`parsed-${chord}-${index}`}
                              className="rounded border border-amber-accent/30 bg-amber-accent/10 px-2 py-0.5"
                            >
                              <Text className="font-mono text-[10px] text-amber-light">{chord}</Text>
                            </View>
                          ))}
                        </View>
                      ) : progressionText.trim() ? (
                        <Text className="mt-1 font-sans text-[10px] text-danger">
                          No valid chords recognized yet.
                        </Text>
                      ) : null}
                    </View>
                  </View>
                </View>
              ) : null}
            </View>
          )}

          {!isJamming && lastJamDiagnostics ? (
            <View className="mb-3 rounded-xl border border-wood-700/45 bg-wood-800/45 px-4 py-3">
              <Text className="font-sans-medium text-xs uppercase tracking-wide text-muted-brown">Last jam diagnostics</Text>
              <Text className="mt-1 font-sans text-sm text-cream">
                {lastJamDiagnostics.inferredScale ?? 'No clear scale detected'} · confidence {lastJamDiagnostics.confidence}
              </Text>
              <Text className="mt-1 font-sans text-xs text-muted-light">
                {lastJamDiagnostics.tags.length > 0
                  ? `tags: ${lastJamDiagnostics.tags.join(', ')}`
                  : 'tags: stable signal, usable map'}
              </Text>
              {lastJamDiagnostics.summaryBundle ? (
                <View className="mt-3 border-t border-wood-700/40 pt-3">
                  {lastJamDiagnostics.summaryBundle.coach_summary ? (
                    <Text className="font-sans text-sm leading-relaxed text-cream/80">
                      {lastJamDiagnostics.summaryBundle.coach_summary}
                    </Text>
                  ) : null}
                  {lastJamDiagnostics.summaryBundle.coach_strengths.length > 0 ? (
                    <Text className="mt-1 font-sans text-xs text-amber-light/80">
                      Strengths: {lastJamDiagnostics.summaryBundle.coach_strengths.join(', ')}
                    </Text>
                  ) : null}
                  {lastJamDiagnostics.summaryBundle.coach_focus_areas.length > 0 ? (
                    <Text className="mt-1 font-sans text-xs text-muted-light">
                      Focus: {lastJamDiagnostics.summaryBundle.coach_focus_areas.join(', ')}
                    </Text>
                  ) : null}
                  {lastJamDiagnostics.summaryBundle.coach_next_step ? (
                    <Text className="mt-1 font-sans text-xs text-amber-light/70">
                      Next: {lastJamDiagnostics.summaryBundle.coach_next_step}
                    </Text>
                  ) : null}
                  {lastJamDiagnostics.summaryBundle.vocabulary_patterns.length > 0 ? (
                    <Text className="mt-1 font-sans text-xs text-muted-light">
                      Patterns: {lastJamDiagnostics.summaryBundle.vocabulary_patterns.map((p) => p.description).join('; ')}
                    </Text>
                  ) : null}
                  <Text className="mt-1 font-sans text-xs text-muted-light/70">
                    {lastJamDiagnostics.summaryBundle.phrase_count} phrases · {lastJamDiagnostics.summaryBundle.total_notes} notes · diversity {(lastJamDiagnostics.summaryBundle.vocabulary_diversity * 100).toFixed(0)}%
                  </Text>
                </View>
              ) : null}
            </View>
          ) : null}

          {isJamming && (
            <View className="min-h-[220px] flex-1 gap-5">
              <View className="items-center gap-2">
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
                <Text className="font-sans text-sm text-muted-brown">Listening… scale hint updates every ~2s</Text>
                {topScales.length > 0 ? (
                  <View className="mt-2 w-full max-w-[280px] gap-1.5">
                    {topScales.slice(0, 3).map((s, idx) => {
                      const barWidth = topScales[0].matchScore > 0
                        ? (s.matchScore / topScales[0].matchScore) * 100
                        : 0
                      const isTop = idx === 0
                      return (
                        <View key={s.inferred_mode ?? idx} className="flex-row items-center gap-2">
                          <Text
                            className={`w-28 font-sans text-xs ${
                              isTop ? 'font-medium text-amber-light' : 'text-cream/70'
                            }`}
                            numberOfLines={1}
                          >
                            {s.label}
                          </Text>
                          <View className="h-2 flex-1 rounded-full bg-wood-700/60">
                            <View
                              className="h-full rounded-full bg-amber-accent"
                              style={{ width: `${barWidth}%` }}
                            />
                          </View>
                          <Text className="w-10 text-right font-mono text-[10px] text-muted-brown">
                            {Math.round(s.matchScore * 100)}%
                          </Text>
                        </View>
                      )
                    })}
                    {topScales[0]?.matchScore != null && topScales[0].matchScore < 0.5 ? (
                      <Text className="mt-1 text-center font-sans text-xs italic text-amber-light/80">
                        Mixed mode — no clear scale center detected
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {phraseCoachLines.observation || phraseCoachLines.suggestion ? (
                  <View className="mt-1 max-w-[320px] gap-1 px-2">
                    {phraseCoachLines.observation ? (
                      <Text className="text-center font-sans text-sm leading-snug text-amber-light/95">
                        {phraseCoachLines.observation}
                      </Text>
                    ) : null}
                    {phraseCoachLines.suggestion ? (
                      <Text className="text-center font-sans text-sm leading-snug text-muted-light">
                        {phraseCoachLines.suggestion}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
              </View>
              <FretboardDiagram
                keyLabel="Jam"
                positionLabel={scaleLabel}
                capoText="Emerald outline = detected scale pitch classes"
                selectedNote={selectedNote}
                pulseKey={fretPulseKey}
                scalePitchClasses={scalePitchClasses}
                overlayMode={overlayMode}
                showOverlayControls
                onOverlayModeChange={setOverlayMode}
                showCopyShare
                onCopyShareLink={copyShareLink}
                degreeRootPitchClass={scaleRootPitchClass}
                enableKeyboardInput
                showTuneControl
                tuneActive={tunerState.active}
                tuneCalibrating={tunerState.calibrating}
                onToggleTune={toggleFretboardTuner}
                onCalibrateTune={startCalibration}
                tunerState={tunerState}
                onSelectNote={(note) => {
                  setSelectedNote(note)
                  setFretPulseKey((k) => k + 1)
                }}
              />
              {/* Reference Score - only visible while jamming */}
              <View className="mb-4 gap-2">
                <Text className="font-sans-medium text-xs uppercase tracking-wider text-amber-light">Reference score</Text>
                <Text className="font-sans text-xs text-cream/80">
                  Highlights follow your detected scale while the backing plays. Cursor syncs to the jam track.
                </Text>
                <View className="mt-4 h-[340px] w-full">
                  <TabViewport
                    ref={jamStemTabRef}
                    gp5Base64={JAM_REFERENCE_TAB_GP5_BASE64}
                    audioSrc={jamTabExternalAudioSrc}
                    renderPreset="study"
                    runtimeDiagnosticsEnabled={false}
                    songTitle="Jam reference"
                    songArtist={classicTrackDef.label}
                    onReady={onJamTabReady}
                    onError={onJamTabError}
                    style={{ flex: 1, height: '100%', width: '100%' }}
                  />
                </View>
              </View>
          </View>
          )}

          <View className="gap-2 pb-4">
            {isJamming ? (
              <Button
                label={busy ? 'Saving…' : 'Stop & Save'}
                variant="secondary"
                haptic="medium"
                onPress={() => void stopAndSave()}
                disabled={busy}
                loading={busy}
                fullWidth
              />
            ) : (
              <Button
                label={busy ? 'Starting…' : 'Start Jamming'}
                haptic="medium"
                onPress={() => void attemptStartJam()}
                disabled={busy}
                loading={busy}
                fullWidth
              />
            )}
            <Button
              label="Back"
              variant="secondary"
              haptic="light"
              onPress={() => router.back()}
              fullWidth
            />
          </View>
        </ScrollView>
      </SafeAreaView>
      <JamSummaryModal
        visible={summaryModal != null}
        status={summaryModal?.status ?? 'skipped'}
        bundle={summaryModal?.bundle ?? null}
        coachSummary={summaryModal?.coachSummary ?? ''}
        phrases={summaryModal?.phrases ?? []}
        track={summaryModal?.track ?? null}
        onClose={() => setSummaryModal(null)}
        onPracticePhrase={(feedback, metrics) =>
          practicePhrase(feedback.phrase_index, metrics.backing_start_ms, metrics.backing_end_ms)
        }
      />
    </WoodGradient>
  )
}
