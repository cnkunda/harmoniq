import { useRouter } from 'expo-router'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Platform, Text, View } from 'react-native'
import Animated, { FadeIn } from 'react-native-reanimated'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { CoachNote } from '@/components/CoachNote'
import { ErrorBanner } from '@/components/ErrorBanner'
import { NoteAccuracyBar } from '@/components/NoteAccuracyBar'
import { PitchIndicator } from '@/components/PitchIndicator'
import { FretboardDiagram } from '@/components/FretboardDiagram'
import { SessionNoteDetailModal } from '@/components/SessionNoteDetailModal'
import { SessionStemAndTab, type SessionStemAndTabHandle } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { toast } from '@/components/ToastConfig'
import { sessionHref } from '@/src/constants/sessionFlow'
import { createSessionRecorder } from '@/src/audio/recordSession'
import { submitQuickFeedback } from '@/src/api/analyze'
import { useMetronomeDefaultOn } from '@/src/settings/useMetronomeDefaultOn'
import type { RecordedTake } from '@/src/audio/recordSession.types'
import type { PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import {
  beatDurationSecFromTempo,
  beatIndexFromClocks,
  CentSampleRing,
  dynamicGhostRmsThreshold,
  hitInnerThresholdCents,
  peakRmsInWindow,
  resolvePitchResult,
  type NoteResultLabel,
  type RmsHistorySample,
} from '@/src/session/noteAccuracyBeats'
import {
  ADAPT_CEILING_CENTS,
  ADAPT_FLOOR_CENTS,
  ADAPT_MISS_WINDOW_BEATS,
  ADAPT_WIDEN_THRESHOLD,
  ADAPT_STEP_CENTS,
  ADAPT_TIGHTEN_THRESHOLD,
  AUTO_LOOP_MISS_THRESHOLD,
  CENTS_TOLERANCE,
  CONTOUR_SAMPLE_MS,
} from '@/src/utils/practiceConfig'
import { capoSuggestion } from '@/src/music/capoSuggestion'
import { buildNoteSelectionDetail } from '@/src/music/noteSelectionDetail'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSessionPlayStore } from '@/src/stores/sessionPlayStore'
import { useAppStore } from '@/src/stores/useAppStore'
import type { NoteContourSample } from '@/src/stores/useAppStore'
import { usePitchStream } from '@/src/pitch/usePitchStream'
import type { MappedUiError } from '@/src/errors/mapErrorToUi'
import { mapMicPermissionDenied, toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import { openHarmoniqAppSettings } from '@/src/errors/openHarmoniqAppSettings'
import type { NoteEventMessage } from '@/types/tabMessage'

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const PITCH_COLORS = {
  amber: 'bg-amber-accent',
  sage: 'bg-success',
  terracotta: 'bg-danger',
} as const

type ScratchContour = { hz: number; amp: number; t: number; wallMs: number }

function noteNameToClass(note: string | null | undefined): number | null {
  if (!note) return null
  const token = note.trim().toUpperCase()
  const root = token.replace(/[0-9]/g, '')
  const idx = NOTE_NAMES.indexOf(root)
  return idx >= 0 ? idx : null
}

function hzToMidiFloat(hz: number): number {
  return 69 + 12 * Math.log2(hz / 440)
}

export default function PlayScreen() {
  const router = useRouter()
  const initialMetronomeOn = useMetronomeDefaultOn()
  const lesson = useLessonStore((s) => s.lesson)
  const sectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const section = lesson?.sections?.[sectionIndex] as Record<string, unknown> | undefined
  const keyLabel = (lesson?.key ?? 'Unknown key').toString()
  const positionLabel =
    section && typeof section.primary_position === 'string'
      ? section.primary_position
      : 'Tap a note to infer position'
  const capoText = useMemo(() => capoSuggestion(keyLabel, positionLabel), [keyLabel, positionLabel])
  const setLatestTake = useSessionPlayStore((s) => s.setLatestTake)
  const keyRoot = typeof lesson?.key === 'string' ? lesson.key.split(/\s+/)[0] : null
  const rootPc = noteNameToClass(keyRoot)

  const adaptedCentsTolerance = useAppStore(
    (s) => s.currentSession?.adaptedCentsTolerance ?? CENTS_TOLERANCE,
  )
  const currentStreak = useAppStore((s) => s.currentSession?.currentStreak ?? 0)

  const targetLadder = useMemo(() => {
    const basePc = rootPc ?? 9 // A as fallback
    return Array.from({ length: 12 }, (_, i) => {
      const pc = (basePc + i) % 12
      return {
        pc,
        label: NOTE_NAMES[pc],
        midi: 60 + pc,
      }
    })
  }, [rootPc])

  const { start, stop } = usePitchStream()
  const recorderRef = useRef(createSessionRecorder())
  const lastPitchAtRef = useRef<number>(0)
  const tickRef = useRef<PlaybackTickContext | null>(null)
  const stemTabRef = useRef<SessionStemAndTabHandle>(null)
  const recordingRef = useRef(false)
  const centRingRef = useRef(new CentSampleRing())
  const activeBeatRef = useRef(-1)
  const recordStartMsRef = useRef(0)
  const anchorPosRef = useRef(0)
  const patternRef = useRef<NoteResultLabel[]>([])
  const rmsHistoryRef = useRef<RmsHistorySample[]>([])
  const beatMaxRmsRef = useRef(0)
  const contourScratchRef = useRef<ScratchContour[]>([])
  const beatWallStartMsRef = useRef(0)
  const lastReadingRef = useRef<{ hz?: number; rms: number; wallMs: number }>({ rms: 0, wallMs: 0 })
  const consecutiveMissByBeatRef = useRef<Map<number, number>>(new Map())
  const cleanBeatStreakRef = useRef(0)
  const adaptRecentRef = useRef<Array<'miss' | 'clean'>>([])
  const prevMidiForPreviewRef = useRef<number | null>(null)
  const stoppingCaptureRef = useRef(false)

  const [pitchRunning, setPitchRunning] = useState(false)
  const [recording, setRecording] = useState(false)
  const [take, setTake] = useState<RecordedTake | null>(null)
  const [status, setStatus] = useState('Idle')
  const [targetLabel, setTargetLabel] = useState(targetLadder[0]?.label ?? 'A')
  const [targetMidi, setTargetMidi] = useState<number>(targetLadder[0]?.midi ?? 69)
  const [nextPreviewMidi, setNextPreviewMidi] = useState<number | null>(null)
  const [centsFromTarget, setCentsFromTarget] = useState<number | null>(null)
  const [micError, setMicError] = useState<MappedUiError | null>(null)
  const [autostopTriggered, setAutostopTriggered] = useState(false)
  const [accuracyBeats, setAccuracyBeats] = useState<NoteResultLabel[]>([])
  const [lastWindowResult, setLastWindowResult] = useState<NoteResultLabel | null>(null)
  const [windowFlashToken, setWindowFlashToken] = useState(0)
  const [quickCoachText, setQuickCoachText] = useState<string | null>(null)
  const [selectedNote, setSelectedNote] = useState<{ string?: number; fret?: number; midi?: number } | null>(null)
  const [fretPulseKey, setFretPulseKey] = useState(0)
  const [noteModalOpen, setNoteModalOpen] = useState(false)
  const aliveRef = useRef(true)
  const targetMidiRef = useRef(targetMidi)
  targetMidiRef.current = targetMidi
  const selectionDetail = useMemo(() => buildNoteSelectionDetail(keyLabel, selectedNote), [keyLabel, selectedNote])

  useEffect(() => {
    recordingRef.current = recording
  }, [recording])

  useEffect(() => {
    return () => {
      aliveRef.current = false
    }
  }, [])

  const pruneRmsHistory = useCallback((nowMs: number) => {
    const h = rmsHistoryRef.current
    const cutoff = nowMs - 4000
    while (h.length > 0 && h[0]!.t < cutoff) {
      h.shift()
    }
  }, [])

  const closeAndScoreBeat = useCallback(
    (closedBeatIndex: number) => {
      const now = Date.now()
      const beatSec = beatDurationSecFromTempo(lesson?.tempo)
      const beatMs = beatSec * 1000

      const peakRecent = peakRmsInWindow(rmsHistoryRef.current, now)
      const ghostThresh = dynamicGhostRmsThreshold(peakRecent)
      const beatMax = beatMaxRmsRef.current
      beatMaxRmsRef.current = 0

      const contourScratch = [...contourScratchRef.current]
      contourScratchRef.current = []

      const storeApi = useAppStore.getState()
      const adapted = storeApi.currentSession?.adaptedCentsTolerance ?? CENTS_TOLERANCE
      const targetMidiNow = targetMidiRef.current

      let result: NoteResultLabel

      if (beatMax < ghostThresh) {
        result = 'ignored'
        centRingRef.current.clear()
      } else {
        const medianAbs = centRingRef.current.medianAbs()
        centRingRef.current.clear()
        const centsContour = contourScratch
          .filter((s) => s.hz > 0)
          .map((s) => ({ t: s.t, cents: (hzToMidiFloat(s.hz) - targetMidiNow) * 100 }))
        result = resolvePitchResult({
          medianAbs,
          adaptedCentsTolerance: adapted,
          centsContour,
        })

        let driftMs: number | null = null
        const first = contourScratch.find((s) => s.hz > 0)
        if (first) {
          const expectedWall = recordStartMsRef.current + closedBeatIndex * beatMs
          driftMs = expectedWall - first.wallMs
        }

        const contourForStore: NoteContourSample[] = contourScratch.map(({ hz, amp, t }) => ({ hz, amp, t }))
        storeApi.pushScoredBeat({
          result,
          contour: contourForStore,
          targetMidi: targetMidiNow,
          driftMsContribution: driftMs,
        })
      }

      patternRef.current.push(result)
      setAccuracyBeats([...patternRef.current])
      if (result !== 'ignored') {
        setLastWindowResult(result)
        setWindowFlashToken((t) => t + 1)
      }

      if (result !== 'ignored') {
        if (result === 'miss') {
          cleanBeatStreakRef.current = 0
          adaptRecentRef.current.push('miss')
        } else {
          cleanBeatStreakRef.current += 1
          adaptRecentRef.current.push('clean')
        }
        while (adaptRecentRef.current.length > ADAPT_MISS_WINDOW_BEATS) adaptRecentRef.current.shift()

        const st = useAppStore.getState()
        const ad = st.currentSession?.adaptedCentsTolerance ?? CENTS_TOLERANCE

        if (cleanBeatStreakRef.current >= ADAPT_TIGHTEN_THRESHOLD) {
          cleanBeatStreakRef.current = 0
          const next = Math.max(ADAPT_FLOOR_CENTS, ad - ADAPT_STEP_CENTS)
          st.setAdaptedCentsTolerance(next)
        }

        const window = adaptRecentRef.current
        const misses = window.filter((x) => x === 'miss').length
        if (window.length >= ADAPT_MISS_WINDOW_BEATS && misses >= ADAPT_WIDEN_THRESHOLD) {
          const next = Math.min(ADAPT_CEILING_CENTS, ad + ADAPT_STEP_CENTS)
          st.setAdaptedCentsTolerance(next)
          adaptRecentRef.current = []
        }

        st.updateStreakAfterResult(result)
      }

      if (result === 'miss') {
        const map = consecutiveMissByBeatRef.current
        const n = (map.get(closedBeatIndex) ?? 0) + 1
        map.set(closedBeatIndex, n)
        if (n >= AUTO_LOOP_MISS_THRESHOLD) {
          map.set(closedBeatIndex, 0)
          const seekSec = anchorPosRef.current + Math.max(0, closedBeatIndex - 2) * beatSec
          void stemTabRef.current?.seekTransportToSeconds(seekSec)
          toast.info('Looping back…')
          const ctx = tickRef.current
          if (ctx) {
            activeBeatRef.current = beatIndexFromClocks({
              playing: ctx.playing,
              positionSec: ctx.positionSec,
              anchorPosSec: anchorPosRef.current,
              recordStartMs: recordStartMsRef.current,
              beatSec,
            })
          }
        }
      } else if (result !== 'ignored') {
        consecutiveMissByBeatRef.current.set(closedBeatIndex, 0)
      }
    },
    [lesson?.tempo],
  )

  const resetAccuracyTracking = useCallback(() => {
    patternRef.current = []
    setAccuracyBeats([])
    activeBeatRef.current = -1
    centRingRef.current.clear()
    setLastWindowResult(null)
    setWindowFlashToken(0)
    rmsHistoryRef.current = []
    beatMaxRmsRef.current = 0
    contourScratchRef.current = []
    consecutiveMissByBeatRef.current.clear()
    cleanBeatStreakRef.current = 0
    adaptRecentRef.current = []
  }, [])

  const startCapture = useCallback(async () => {
    setStatus('Starting mic + recorder…')
    setMicError(null)
    setQuickCoachText(null)
    stoppingCaptureRef.current = false
    resetAccuracyTracking()
    useAppStore.getState().initSessionForCapture()
    recordStartMsRef.current = Date.now()
    anchorPosRef.current = tickRef.current?.positionSec ?? 0
    await recorderRef.current.start()
    await start((reading) => {
      const now = Date.now()
      lastPitchAtRef.current = now
      pruneRmsHistory(now)
      rmsHistoryRef.current.push({ t: now, rms: reading.rms })
      if (recordingRef.current) {
        beatMaxRmsRef.current = Math.max(beatMaxRmsRef.current, reading.rms)
      }

      const peakRecent = peakRmsInWindow(rmsHistoryRef.current, now)
      const gate = dynamicGhostRmsThreshold(peakRecent)

      lastReadingRef.current = {
        hz: reading.hz,
        rms: reading.rms,
        wallMs: now,
      }

      if (reading.hz != null && Number.isFinite(reading.hz) && reading.hz > 0 && reading.rms >= gate) {
        const midi = hzToMidiFloat(reading.hz)
        const bestCents = (midi - targetMidiRef.current) * 100
        setCentsFromTarget(bestCents)
        if (recordingRef.current) {
          centRingRef.current.push(bestCents)
        }
      }
    })
    setTake(null)
    setRecording(true)
    setPitchRunning(true)
    setStatus('Capturing performance')
  }, [resetAccuracyTracking, start, pruneRmsHistory])

  const stopCapture = useCallback(
    async (reason: 'done' | 'silence') => {
      if (!recording && !pitchRunning) return
      stoppingCaptureRef.current = true
      let patternSnapshot: NoteResultLabel[] = []
      try {
        const beatSec = beatDurationSecFromTempo(lesson?.tempo)
        if (centRingRef.current.hasSamples() || contourScratchRef.current.length > 0) {
          const idx =
            activeBeatRef.current >= 0
              ? activeBeatRef.current
              : beatIndexFromClocks({
                  playing: tickRef.current?.playing ?? false,
                  positionSec: tickRef.current?.positionSec ?? 0,
                  anchorPosSec: anchorPosRef.current,
                  recordStartMs: recordStartMsRef.current,
                  beatSec,
                })
          closeAndScoreBeat(Math.max(0, idx))
        }

        patternSnapshot = [...patternRef.current]
        activeBeatRef.current = -1

        const rec = await recorderRef.current.stop()
        await stop()
        setRecording(false)
        setPitchRunning(false)
        setTake(rec)
        setLatestTake(rec)
        setStatus(reason === 'silence' ? 'Auto-stopped after 5s silence' : 'Capture stopped')

        const apiPattern = patternSnapshot.filter((x) => x !== 'ignored') as Array<
          'hit' | 'close' | 'miss' | 'vibrato'
        >
        if (apiPattern.length > 0) {
          void submitQuickFeedback({ accuracy_pattern: apiPattern }).then(({ message }) => {
            if (!aliveRef.current) return
            setQuickCoachText(message)
          })
        }
      } finally {
        stoppingCaptureRef.current = false
      }
    },
    [pitchRunning, recording, setLatestTake, stop, lesson?.tempo, closeAndScoreBeat],
  )

  useEffect(() => {
    return () => {
      void stop().catch(() => {})
      void recorderRef.current.stop().catch(() => {})
    }
  }, [stop])

  useEffect(() => {
    if (!recording) return
    const beatSec = beatDurationSecFromTempo(lesson?.tempo)
    const id = setInterval(() => {
      if (stoppingCaptureRef.current) return
      const ctx = tickRef.current
      if (!ctx) return
      const idx = beatIndexFromClocks({
        playing: ctx.playing,
        positionSec: ctx.positionSec,
        anchorPosSec: anchorPosRef.current,
        recordStartMs: recordStartMsRef.current,
        beatSec,
      })
      if (activeBeatRef.current < 0) {
        activeBeatRef.current = idx
        beatWallStartMsRef.current = Date.now()
        return
      }
      while (activeBeatRef.current < idx) {
        closeAndScoreBeat(activeBeatRef.current)
        activeBeatRef.current += 1
        beatWallStartMsRef.current = Date.now()
      }
    }, 100)
    return () => clearInterval(id)
  }, [lesson?.tempo, recording, closeAndScoreBeat])

  useEffect(() => {
    if (!recording) return
    const id = setInterval(() => {
      if (!recordingRef.current || activeBeatRef.current < 0) return
      const lr = lastReadingRef.current
      const wallMs = Date.now()
      const t = wallMs - beatWallStartMsRef.current
      const hz = lr.hz != null && Number.isFinite(lr.hz) && lr.hz > 0 ? lr.hz : 0
      contourScratchRef.current.push({ hz, amp: lr.rms, t, wallMs })
    }, CONTOUR_SAMPLE_MS)
    return () => clearInterval(id)
  }, [recording])

  useEffect(() => {
    if (!recording) return
    const id = setInterval(() => {
      const ctx = tickRef.current
      if (!ctx?.playing) return
      const last = lastPitchAtRef.current
      if (last <= 0) return
      if (Date.now() - last >= 5000) {
        setAutostopTriggered(true)
        void stopCapture('silence')
      }
    }, 250)
    return () => clearInterval(id)
  }, [recording, stopCapture])

  const innerTol = hitInnerThresholdCents(adaptedCentsTolerance)
  const pitchBandClass =
    centsFromTarget == null
      ? 'bg-wood-600'
      : Math.abs(centsFromTarget) <= innerTol
        ? PITCH_COLORS.sage
        : Math.abs(centsFromTarget) <= adaptedCentsTolerance
          ? PITCH_COLORS.amber
          : PITCH_COLORS.terracotta

  return (
    <SessionStepScreen
      title="Play"
      subtitle="Play along with backing mix (guitar muted), live pitch ladder, and in-memory take capture."
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Next: Review"
      onNext={() => router.push(sessionHref('review'))}
    >
      {Platform.OS === 'web' ? (
        <View className="rounded-lg border border-amber-accent/30 bg-amber-accent/10 px-3 py-2">
          <Text className="font-sans text-xs text-wood-900">
            Web play tip: allow microphone permissions and use headphones to reduce bleed/feedback.
          </Text>
          <Text className="mt-1 font-sans text-[11px] text-muted-brown">
            Browser mic capture needs HTTPS or localhost.
          </Text>
        </View>
      ) : null}

      <View className="mt-3 rounded-lg border border-wood-600/45 bg-cream-dark/40 px-3 py-3">
        <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Pitch ladder</Text>
        <Text className="mt-1 font-mono text-xs text-muted-brown">
          Target note: {targetLabel}{' '}
          {centsFromTarget != null ? `(${centsFromTarget >= 0 ? '+' : ''}${Math.round(centsFromTarget)}c)` : ''}
        </Text>
        <Text className="mt-0.5 font-sans text-xs text-muted-brown">
          Clean streak: {currentStreak} beat{currentStreak === 1 ? '' : 's'}
        </Text>
        <Text className="mt-0.5 font-sans text-xs text-muted-brown">
          Pitch tolerance: ±{Math.round(adaptedCentsTolerance)}¢ (adapts to your playing)
        </Text>
        <View className="mt-2">
          <PitchIndicator
            note={targetLabel}
            cents={centsFromTarget ?? undefined}
            isActive={recording}
            targetMidi={targetMidi}
            nextTargetMidi={nextPreviewMidi}
            windowResult={lastWindowResult}
            windowFlashToken={windowFlashToken}
          />
        </View>
        <View className="mt-2">
          <Text className="mb-1 font-sans text-[10px] uppercase tracking-wide text-muted-brown">Beat accuracy</Text>
          <NoteAccuracyBar beats={accuracyBeats} />
        </View>
        <View className="mt-2 flex-row items-end gap-1">
          {targetLadder.map((n) => {
            const active = n.label === targetLabel
            return (
              <View key={n.label} className="items-center">
                <View className={`h-8 w-3 rounded-sm ${active ? pitchBandClass : 'bg-wood-600/40'}`} />
                <Text className={`mt-1 font-mono text-[9px] ${active ? 'text-wood-900' : 'text-muted-brown'}`}>{n.label}</Text>
              </View>
            )
          })}
        </View>
        <Text className="mt-2 font-sans text-[11px] text-muted-brown">
          Inner band ≤{Math.round(innerTol)}¢ · outer ≤{Math.round(adaptedCentsTolerance)}¢ · terracotta beyond.
        </Text>
      </View>

      {quickCoachText ? (
        <Animated.View className="mt-3" entering={FadeIn.duration(320)}>
          <CoachNote text={quickCoachText} />
        </Animated.View>
      ) : null}

      <View className="mt-3 flex-row flex-wrap items-center gap-2">
        <AnimatedPressable
          onPress={() => {
            void (recording ? stopCapture('done') : startCapture()).catch((e) => {
              const message = e instanceof Error ? e.message : String(e)
              if (message === 'MIC_PERMISSION_DENIED') {
                setMicError(mapMicPermissionDenied(Platform.OS))
              }
              setStatus(message === 'MIC_PERMISSION_DENIED' ? 'Microphone access needed' : `Capture error: ${message}`)
            })
          }}
          className="rounded-lg bg-amber-accent/90 px-4 py-2"
          accessibilityRole="button"
        >
          <Text className="font-sans-medium text-wood-900">{recording ? 'Done' : 'Start play capture'}</Text>
        </AnimatedPressable>
        <Text className="font-mono text-[11px] text-muted-brown">{status}</Text>
      </View>
      {micError ? (
        <ErrorBanner
          className="mt-2"
          dismissible={false}
          {...toErrorBannerProps(micError, {
            onRetry: () => setMicError(null),
            onDismiss: () => setMicError(null),
            onOpenSettings: () => {
              void openHarmoniqAppSettings()
              setMicError(null)
            },
            onContinue: () => setMicError(null),
          })}
        />
      ) : null}
      {autostopTriggered ? (
        <Text className="mt-1 font-sans text-xs text-muted-brown">Auto-end triggered after 5 seconds of silence.</Text>
      ) : null}
      {take ? (
        <Text className="mt-1 font-sans text-xs text-wood-900">
          Recorded take: {(take.durationMs / 1000).toFixed(1)}s, {take.audioBytes.length} bytes ({take.mimeType})
        </Text>
      ) : null}

      <FretboardDiagram
        keyLabel={keyLabel}
        positionLabel={positionLabel}
        capoText={capoText}
        selectedNote={selectedNote}
        pulseKey={fretPulseKey}
        onSelectNote={(note) => {
          setSelectedNote(note)
          setFretPulseKey((k) => k + 1)
          setNoteModalOpen(true)
        }}
      />

      <SessionStemAndTab
        ref={stemTabRef}
        initialMetronomeOn={initialMetronomeOn}
        initialStemMuteById={{ guitar: true, bass: false, drums: false, vocals: true, piano: true, other: true }}
        onPlaybackTick={(ctx) => {
          tickRef.current = ctx
        }}
        onNoteEvent={(evt: NoteEventMessage) => {
          const midi = Math.round(evt.midi)
          setNextPreviewMidi(prevMidiForPreviewRef.current)
          prevMidiForPreviewRef.current = midi
          setTargetMidi(midi)
          const pc = ((midi % 12) + 12) % 12
          setTargetLabel(NOTE_NAMES[pc] ?? 'A')
          setSelectedNote({ string: evt.string, fret: evt.fret, midi })
          setFretPulseKey((k) => k + 1)
          if (evt.fromScoreTap) {
            setNoteModalOpen(true)
          }
        }}
      />
      <SessionNoteDetailModal
        detail={selectionDetail}
        visible={noteModalOpen}
        onClose={() => setNoteModalOpen(false)}
      />
      {section ? (
        <Text className="mt-2 font-mono text-[10px] text-muted-brown">
          Section: {String(section.label ?? 'Section')} {lesson?.key ? `| Key: ${lesson.key}` : ''}
        </Text>
      ) : null}
    </SessionStepScreen>
  )
}
