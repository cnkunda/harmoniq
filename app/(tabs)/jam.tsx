import { useRouter } from 'expo-router'
import { Audio, type AVPlaybackStatus } from 'expo-av'
import { Asset } from 'expo-asset'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ActivityIndicator, Platform, ScrollView, Text, View } from 'react-native'
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
import { FretboardDiagram } from '@/components/FretboardDiagram'
import { SessionStemAndTab, type SessionStemAndTabHandle } from '@/components/SessionStemAndTab'
import { toast } from '@/components/ToastConfig'
import { WoodGradient } from '@/components/WoodGradient'
import { ApiError, buildPlayerProfileFromSkillNodes, submitJamScore } from '@/src/api/analyze'
import { requestJamBacking } from '@/src/api/jam'
import { mapBrowserMicBlockedForJam, toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import { BACKING_TRACKS, type BackingTrackId } from '@/src/constants/backingTracks'
import { getAllSkillNodes, insertJamSnapshotRow } from '@/src/db/client'
import { coachFromPhraseFeatures } from '@/src/jam/jamPhraseCoach'
import { phraseToFeatures } from '@/src/jam/jamPhraseFeatures'
import { createJamPhraseSegmenter } from '@/src/jam/jamPhraseSegmenter'
import { prepareJamBackingPlayable } from '@/src/jam/jamBackingPlayable'
import { JAM_REFERENCE_TAB_GP5_BASE64 } from '@/src/jam/jamReferenceTabGp5Base64'
import { pickSuggestedClassicFromWeakAreas } from '@/src/jam/jamSuggestedClassic'
import { createPitchClassHistogram } from '@/src/jam/pitchClassHistogram'
import { usePitchStream } from '@/src/pitch/usePitchStream'
import { useFretboardTuner } from '@/src/session/useFretboardTuner'
import {
  buildFretboardShareUrl,
  readFretboardShareStateFromLocation,
  type FretboardOverlayMode,
} from '@/src/utils/fretboardShareState'

const SCALE_UI_INTERVAL_MS = 2000
const AI_INSTRUMENTAL_TRACK_ID = 'ai-instrumental'
type InferenceConfidence = 'low' | 'medium' | 'high'
type BackingMode = 'classic' | 'ai'

function confidenceFromMatchScore(score: number): InferenceConfidence {
  if (score >= 0.72) return 'high'
  if (score >= 0.5) return 'medium'
  return 'low'
}

export default function JamScreen() {
  const router = useRouter()
  const { start: startPitch, stop: stopPitch } = usePitchStream()

  const [isJamming, setIsJamming] = useState(false)
  const [backingMode, setBackingMode] = useState<BackingMode>('classic')
  const [classicTrackId, setClassicTrackId] = useState<BackingTrackId>(BACKING_TRACKS[0].id)
  const [weakAreas, setWeakAreas] = useState<readonly string[]>([])
  const [scaleLabel, setScaleLabel] = useState('—')
  const [scalePitchClasses, setScalePitchClasses] = useState<readonly number[] | null>(null)
  const [scaleRootPitchClass, setScaleRootPitchClass] = useState<number | null>(null)
  const [overlayMode, setOverlayMode] = useState<FretboardOverlayMode>('off')
  const [selectedNote, setSelectedNote] = useState<{ string?: number; fret?: number; midi?: number } | null>(null)
  const [fretPulseKey, setFretPulseKey] = useState(0)
  const [scaleUiGeneration, setScaleUiGeneration] = useState(0)
  const [jamTabReady, setJamTabReady] = useState(false)
  /** Web AlphaTab external-media player: same backing URI as expo-av so duration/buffers are valid. */
  const [jamWebTabAudioSrc, setJamWebTabAudioSrc] = useState<string | null>(null)
  const [webMicBlocked, setWebMicBlocked] = useState(false)
  const [micBannerKey, setMicBannerKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [lastJamDiagnostics, setLastJamDiagnostics] = useState<{
    inferredScale: string | null
    confidence: 'low' | 'medium' | 'high'
    tags: string[]
  } | null>(null)

  const pulse = useSharedValue(1)
  const ringStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pulse.value }],
    opacity: 0.5 + (pulse.value - 1) * 3,
  }))

  const soundRef = useRef<Audio.Sound | null>(null)
  const jamAiPlaybackReleaseRef = useRef<(() => void) | null>(null)
  const lastAiPromptRef = useRef<string | null>(null)
  // #region agent log
  const jamSeamLogRef = useRef<{ started: boolean; nearEnd: boolean; wrapped: boolean }>({
    started: false,
    nearEnd: false,
    wrapped: false,
  })
  // #endregion
  const histogramRef = useRef(createPitchClassHistogram())
  const jamBackingPositionRef = useRef(0)
  const jamBpmRef = useRef<number | null>(null)
  const phraseSegmenterRef = useRef<ReturnType<typeof createJamPhraseSegmenter> | null>(null)
  const [phraseCoachLines, setPhraseCoachLines] = useState({ observation: '', suggestion: '' })
  /** Monotonic phrase segmentation clock (starts when mic opens). */
  const jamPhraseClockStartRef = useRef<number | null>(null)
  const jamStartedAtRef = useRef<number | null>(null)
  const jamStemTabRef = useRef<SessionStemAndTabHandle>(null)
  const jamLastStemPlayingRef = useRef(false)
  const lastScaleUiAtRef = useRef(0)
  const lastScaleTintRef = useRef<{ rootMidi: number; intervals: readonly number[] } | null>(null)
  const classicTrackDef = BACKING_TRACKS.find((t) => t.id === classicTrackId) ?? BACKING_TRACKS[0]
  jamBpmRef.current = classicTrackDef.bpm ?? null
  const { state: tunerState, toggleTuner, startCalibration } = useFretboardTuner()

  useEffect(() => {
    const seg = createJamPhraseSegmenter({
      onPhraseClosed: (phrase) => {
        const f = phraseToFeatures(phrase, jamBpmRef.current)
        const lines = coachFromPhraseFeatures(phrase, f)
        if (!lines.observation && !lines.suggestion) return
        setPhraseCoachLines(lines)
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
    void getAllSkillNodes().then((nodes) => {
      if (cancelled) return
      const profile = buildPlayerProfileFromSkillNodes(nodes)
      const wa = profile?.weak_areas ?? []
      setWeakAreas(wa)
      setClassicTrackId(pickSuggestedClassicFromWeakAreas(wa))
    })
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
    }
  }, [pulse, stopPitch])

  useEffect(() => {
    if (!isJamming) {
      setJamTabReady(false)
      jamLastStemPlayingRef.current = false
      setJamWebTabAudioSrc(null)
      jamAiPlaybackReleaseRef.current?.()
      jamAiPlaybackReleaseRef.current = null
    }
  }, [isJamming])

  // #region agent log
  useEffect(() => {
    if (Platform.OS !== 'web' || !isJamming) return
    fetch('http://127.0.0.1:7847/ingest/304bce8c-5898-4e69-ad2e-982e56245f77', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': 'f059aa' },
      body: JSON.stringify({
        sessionId: 'f059aa',
        runId: 'pre-fix',
        hypothesisId: 'H2',
        location: 'jam.tsx:jam-active',
        message: 'Jam web tab backing state',
        data: {
          backingMode,
          jamWebTabAudioSrcLen: jamWebTabAudioSrc?.length ?? 0,
          jamWebTabAudioPrefix: jamWebTabAudioSrc ? jamWebTabAudioSrc.slice(0, 32) : '',
        },
        timestamp: Date.now(),
      }),
    }).catch(() => {})
  }, [isJamming, backingMode, jamWebTabAudioSrc])
  // #endregion

  useEffect(() => {
    if (Platform.OS !== 'web' || !isJamming || !jamTabReady) return
    const tab = jamStemTabRef.current?.getTabSurface()
    const cmd = lastScaleTintRef.current
    if (cmd) {
      tab?.highlightScaleDegrees(cmd.rootMidi, [...cmd.intervals])
    } else {
      tab?.clearScaleHighlight()
    }
  }, [isJamming, jamTabReady, scaleUiGeneration])

  const syncJamTabFromPlaybackStatus = useCallback((status: AVPlaybackStatus) => {
    if (Platform.OS !== 'web' || !status.isLoaded) return
    const tab = jamStemTabRef.current?.getTabSurface()
    tab?.syncPlaybackTimelineMs(status.positionMillis ?? 0)
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
        if (Platform.OS === 'web') {
          const dur = status.durationMillis ?? 0
          const pos = status.positionMillis ?? 0
          const seam = jamSeamLogRef.current
          // #region agent log
          if (!seam.started) {
            seam.started = true
            fetch('http://127.0.0.1:7847/ingest/304bce8c-5898-4e69-ad2e-982e56245f77', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': 'f059aa' },
              body: JSON.stringify({
                sessionId: 'f059aa',
                runId: 'pre-fix',
                hypothesisId: 'H6',
                location: 'jam.tsx:status-start',
                message: 'First playback status',
                data: { durationMillis: dur, positionMillis: pos, isLooping: status.isLooping },
                timestamp: Date.now(),
              }),
            }).catch(() => {})
          }
          if (!seam.nearEnd && dur > 0 && pos >= Math.max(0, dur - 120)) {
            seam.nearEnd = true
            fetch('http://127.0.0.1:7847/ingest/304bce8c-5898-4e69-ad2e-982e56245f77', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': 'f059aa' },
              body: JSON.stringify({
                sessionId: 'f059aa',
                runId: 'pre-fix',
                hypothesisId: 'H6',
                location: 'jam.tsx:status-near-end',
                message: 'Approaching loop seam',
                data: { durationMillis: dur, positionMillis: pos },
                timestamp: Date.now(),
              }),
            }).catch(() => {})
          }
          if (seam.nearEnd && !seam.wrapped && pos < 120) {
            seam.wrapped = true
            fetch('http://127.0.0.1:7847/ingest/304bce8c-5898-4e69-ad2e-982e56245f77', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': 'f059aa' },
              body: JSON.stringify({
                sessionId: 'f059aa',
                runId: 'pre-fix',
                hypothesisId: 'H6',
                location: 'jam.tsx:status-wrapped',
                message: 'Loop wrapped to start',
                data: { positionMillis: pos },
                timestamp: Date.now(),
              }),
            }).catch(() => {})
          }
          // #endregion
        }
      }
      syncJamTabFromPlaybackStatus(status)
    },
    [syncJamTabFromPlaybackStatus],
  )

  const onJamTabReady = useCallback(() => {
    setJamTabReady(true)
    if (Platform.OS !== 'web') return
    const snd = soundRef.current
    if (!snd) return
    void snd.getStatusAsync().then((st) => {
      if (!st.isLoaded) return
      syncJamTabFromPlaybackStatus(st)
    })
  }, [syncJamTabFromPlaybackStatus])

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
    let webTabBackingUri: string | null = null
    if (backingMode === 'ai') {
      const res = await requestJamBacking({
        musical_key: classicTrackDef.key,
        bpm: classicTrackDef.bpm,
        weak_areas: [...weakAreas],
      })
      lastAiPromptRef.current = res.prompt_used
      const prepared = await prepareJamBackingPlayable(res.audio_base64, res.mime_type)
      pendingUriCleanup.push(prepared.release)
      source = { uri: prepared.uri }
      if (Platform.OS === 'web') webTabBackingUri = prepared.uri
    } else {
      lastAiPromptRef.current = null
      source = classicTrackDef.source
      if (Platform.OS === 'web') {
        const asset = Asset.fromModule(classicTrackDef.source)
        await asset.downloadAsync()
        webTabBackingUri = asset.localUri ?? asset.uri
        if (!webTabBackingUri) {
          throw new Error('Could not resolve classic backing URL for tab sync.')
        }
      }
    }

    try {
      // #region agent log
      fetch('http://127.0.0.1:7847/ingest/304bce8c-5898-4e69-ad2e-982e56245f77', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': 'f059aa' },
        body: JSON.stringify({
          sessionId: 'f059aa',
          runId: 'pre-fix',
          hypothesisId: 'H6',
          location: 'jam.tsx:before-createAsync',
          message: 'Preparing jam playback source',
          data: {
            backingMode,
            classicTrackId: classicTrackDef.id,
            hasWebTabBackingUri: Boolean(webTabBackingUri),
            webTabBackingUriPrefix: webTabBackingUri ? webTabBackingUri.slice(0, 32) : '',
          },
          timestamp: Date.now(),
        }),
      }).catch(() => {})
      // #endregion
      const { sound } = await Audio.Sound.createAsync(source, { isLooping: true, shouldPlay: false })
      jamAiPlaybackReleaseRef.current = pendingUriCleanup.length > 0 ? pendingUriCleanup[0]! : null
      pendingUriCleanup.length = 0
      soundRef.current = sound
      jamSeamLogRef.current = { started: false, nearEnd: false, wrapped: false }
      if (Platform.OS === 'web' && webTabBackingUri) {
        setJamWebTabAudioSrc(webTabBackingUri)
      }
      jamLastStemPlayingRef.current = false
      sound.setOnPlaybackStatusUpdate(handleJamPlaybackStatus)
      await sound.setVolumeAsync(1)
      await sound.playAsync()
      jamStartedAtRef.current = Date.now()
      setIsJamming(true)
      startPulse()
    } catch (err) {
      for (const fn of pendingUriCleanup) {
        fn()
      }
      pendingUriCleanup.length = 0
      throw err
    }
  }, [
    backingMode,
    classicTrackDef.bpm,
    classicTrackDef.key,
    classicTrackDef.source,
    handleJamPlaybackStatus,
    startPulse,
    weakAreas,
  ])

  const attemptStartJam = useCallback(async () => {
    if (busy || isJamming) return
    setBusy(true)
    setWebMicBlocked(false)
    phraseSegmenterRef.current?.reset()
    setPhraseCoachLines({ observation: '', suggestion: '' })
    jamPhraseClockStartRef.current = Date.now()
    histogramRef.current = createPitchClassHistogram()
    setScaleLabel('—')
    setScalePitchClasses(null)
    setScaleRootPitchClass(null)
    lastScaleUiAtRef.current = 0
    lastScaleTintRef.current = null
    if (Platform.OS === 'web') {
      jamStemTabRef.current?.getTabSurface()?.clearScaleHighlight()
    }

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
        const label = scale ? scale.label : histogramRef.current.getBestLabel()
        setScaleLabel(label)
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
      jamAiPlaybackReleaseRef.current?.()
      jamAiPlaybackReleaseRef.current = null
      lastAiPromptRef.current = null
      if (e instanceof ApiError) {
        if (e.status === 503) {
          toast.error(
            'AI backing needs GEMINI_API_KEY on the practice server. Choose a classic loop or configure the backend.',
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

    const snd = soundRef.current
    soundRef.current = null
    if (snd) {
      try {
        snd.setOnPlaybackStatusUpdate(null)
        await snd.stopAsync()
        await snd.unloadAsync()
      } catch {
        /* ignore */
      }
    }
    jamLastStemPlayingRef.current = false
    if (Platform.OS === 'web') {
      jamStemTabRef.current?.getTabSurface()?.setStemPlaybackActive(false)
    }

    const hist = histogramRef.current
    const pitchClassWeightMap = hist.toScalePositionMap(durationSec)
    const bestScale = hist.getBestScale()
    const inferred = bestScale ? bestScale.label : hist.getBestLabel()
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
    if (Platform.OS === 'web') {
      jamStemTabRef.current?.getTabSurface()?.clearScaleHighlight()
    }
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
        track_id: trackIdForSave,
        track_label: trackLabelForSave,
        track_key: classicTrackDef.key,
        track_bpm: classicTrackDef.bpm,
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

    try {
      await insertJamSnapshotRow({
        id: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        date: new Date().toISOString(),
        duration_seconds: durationSeconds,
        scale_position_map: Object.keys(mergedPitchMap).length > 0 ? mergedPitchMap : pitchClassWeightMap,
        pitch_class_weight_map: Object.keys(mergedPitchMap).length > 0 ? mergedPitchMap : pitchClassWeightMap,
        position_weight_map: mergedPositionMap,
        inferred_scale_label: inferred === '—' ? null : inferred,
        inference_confidence: inferenceConfidence,
        track_id: trackIdForSave,
        track_label: trackLabelForSave,
        track_key: classicTrackDef.key,
        track_bpm: classicTrackDef.bpm,
        reliability_tags: reliabilityTags,
        reliability_confidence: reliabilityConfidence,
        reliability_signal_quality: reliabilitySignalQuality,
        recurring_gestures: [],
        coach_summary: coachSummary,
      })
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
    setLastJamDiagnostics({
      inferredScale: inferred === '—' ? null : inferred,
      confidence: reliabilityConfidence,
      tags: reliabilityTags,
    })
    setBusy(false)
    toast.success('Jam saved.')
    lastAiPromptRef.current = null
  }, [
    backingMode,
    busy,
    classicTrackDef.bpm,
    classicTrackDef.id,
    classicTrackDef.key,
    classicTrackDef.label,
    isJamming,
    stopPitch,
    stopPulse,
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
          contentContainerStyle={{ flexGrow: 1, justifyContent: 'space-between', paddingBottom: 24 }}
          showsVerticalScrollIndicator={false}
        >
          <View className="mt-6 mb-4">
            <Text className="mb-1 font-serif text-3xl text-cream">Jam Mode</Text>
            <Text className="font-sans text-sm text-muted-brown">
              {backingMode === 'ai'
                ? `AI instrumental · ${classicTrackDef.key}${
                    classicTrackDef.bpm != null ? ` · ${classicTrackDef.bpm} BPM` : ''
                  } · template: ${classicTrackDef.label}`
                : `${classicTrackDef.label} · ${classicTrackDef.key}${
                    classicTrackDef.bpm != null ? ` · ${classicTrackDef.bpm} BPM` : ' · ambient'
                  }`}
            </Text>
            {weakAreas.length > 0 ? (
              <Text className="mt-1 font-sans text-xs text-amber-light/90">
                Suggested loop from your practice focus: {weakAreas.join(', ')}
              </Text>
            ) : null}
            <Text className="mt-1 font-sans text-xs text-muted-brown">Reference tab is a generic scale map for visual guidance.</Text>
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
                    AI practice bed (instrumental)
                  </Text>
                  <Text className="mt-0.5 font-sans text-xs text-muted-brown">
                    Uses key/tempo from the template loop you select below · needs backend + Gemini key
                  </Text>
                </View>
                {busy && backingMode === 'ai' ? <ActivityIndicator color="#e8b86d" /> : null}
              </AnimatedPressable>
              {BACKING_TRACKS.map((track) => {
                const templateActive = backingMode === 'ai' && classicTrackId === track.id
                const classicActive = backingMode === 'classic' && classicTrackId === track.id
                return (
                  <AnimatedPressable
                    key={track.id}
                    onPress={() => {
                      setClassicTrackId(track.id)
                      setBackingMode('classic')
                    }}
                    onLongPress={() => {
                      setClassicTrackId(track.id)
                      setBackingMode('ai')
                    }}
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
                        <Text className="mt-0.5 font-sans text-xs text-muted-brown">Template for AI key / BPM</Text>
                      ) : null}
                    </View>
                    {track.bpm != null ? (
                      <Text className="font-mono text-xs text-muted-brown">{track.bpm} BPM</Text>
                    ) : (
                      <Text className="font-mono text-xs text-muted-brown">ambient</Text>
                    )}
                  </AnimatedPressable>
                )
              })}
              <Text className="font-sans text-[10px] text-muted-brown/90">
                Long-press a classic loop to keep it as the AI template while selecting AI bed above.
              </Text>
            </View>
          )}

          {!isJamming && lastJamDiagnostics ? (
            <View className="mb-4 rounded-xl border border-wood-700/45 bg-wood-800/45 p-4">
              <Text className="font-sans-medium text-xs uppercase tracking-wide text-muted-brown">Last jam diagnostics</Text>
              <Text className="mt-1 font-sans text-sm text-cream">
                {lastJamDiagnostics.inferredScale ?? 'No clear scale detected'} · confidence {lastJamDiagnostics.confidence}
              </Text>
              <Text className="mt-1 font-sans text-xs text-muted-brown">
                {lastJamDiagnostics.tags.length > 0
                  ? `tags: ${lastJamDiagnostics.tags.join(', ')}`
                  : 'tags: stable signal, usable map'}
              </Text>
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
                {phraseCoachLines.observation || phraseCoachLines.suggestion ? (
                  <View className="mt-1 max-w-[320px] gap-1 px-2">
                    {phraseCoachLines.observation ? (
                      <Text className="text-center font-sans text-sm leading-snug text-amber-light/95">
                        {phraseCoachLines.observation}
                      </Text>
                    ) : null}
                    {phraseCoachLines.suggestion ? (
                      <Text className="text-center font-sans text-sm leading-snug text-muted-brown">
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
              {Platform.OS === 'web' ? (
                <View className="gap-2">
                  <Text className="font-sans text-xs text-muted-brown">
                    Reference tab (generic): highlights detected scale tones over a fixed pattern.
                  </Text>
                  <SessionStemAndTab
                    ref={jamStemTabRef}
                    showStemPanel={false}
                    gp5Base64Override={JAM_REFERENCE_TAB_GP5_BASE64}
                    audioSrcOverride={jamWebTabAudioSrc}
                    transposeSemitonesOverride={0}
                    onTabReady={onJamTabReady}
                    tabFrameClassName="h-[200px] w-full overflow-hidden rounded-xl border border-wood-600/45 bg-ivory px-2"
                  />
                </View>
              ) : null}
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
