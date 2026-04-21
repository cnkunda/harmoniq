import { useCallback, useEffect, useRef, useState } from 'react'

import { createSessionRecorder } from '@/src/audio/recordSession'
import type { RecordedTake } from '@/src/audio/recordSession.types'
import { submitQuickFeedback } from '@/src/api/analyze'
import { usePitchStream } from '@/src/pitch/usePitchStream'
import { pitchClassLabelFromMidi } from '@/src/music/noteNames'
import { useAppStore } from '@/src/stores/useAppStore'
import { useSessionPlayStore } from '@/src/stores/sessionPlayStore'
import type { SessionStemAndTabHandle } from '@/components/SessionStemAndTab'
import type { PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import { effectiveRmsSignalGate } from '@/src/audio/noiseGate'
import {
  beatDurationSecFromTempo,
  beatIndexFromClocks,
  captureBeatIndexFromTick,
  CentSampleRing,
  dynamicGhostRmsThreshold,
  peakRmsInWindow,
  resolvePitchResult,
  type NoteResultLabel,
  type RmsHistorySample,
} from '@/src/session/noteAccuracyBeats'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
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
import { resolveFretCell } from '@/src/music/fretboardCell'
import type { NoteContourSample } from '@/src/stores/useAppStore'
import { toast } from '@/components/ToastConfig'
import type { NoteEventMessage } from '@/types/tabMessage'

export type TabNoteQueueEntry = {
  midi: number
  label: string
  beat: number
  string?: number
  fret?: number
}

export type FretCellResult = {
  /** Fretboard row 0–5 (high E → low E). */
  row: number
  fret: number
  result: 'hit' | 'close' | 'miss'
}

type ScratchContour = { hz: number; amp: number; t: number; wallMs: number }

function hzToMidiFloat(hz: number): number {
  return 69 + 12 * Math.log2(hz / 440)
}

const MAX_QUEUE = 32

export function usePlayCapture(tempo: number | null | undefined) {
  const setLatestTake = useSessionPlayStore((s) => s.setLatestTake)
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
  const beatNoteLabelsRef = useRef<string[]>([])
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
  const targetMidiRef = useRef(69)
  const lastTabPositionRef = useRef<{ string?: number; fret?: number; midi?: number } | null>(null)
  const aliveRef = useRef(true)
  const fretResultClearRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [pitchRunning, setPitchRunning] = useState(false)
  const [recording, setRecording] = useState(false)
  /** Wall time when capture session started (for mm:ss UI); cleared when capture ends. */
  const [recordingWallClockStartedAtMs, setRecordingWallClockStartedAtMs] = useState<number | null>(null)
  const [take, setTake] = useState<RecordedTake | null>(null)
  const [status, setStatus] = useState('Idle')
  const [targetLabel, setTargetLabel] = useState('A')
  const [targetMidi, setTargetMidi] = useState(69)
  const [nextPreviewMidi, setNextPreviewMidi] = useState<number | null>(null)
  const [centsFromTarget, setCentsFromTarget] = useState<number | null>(null)
  const [autostopTriggered, setAutostopTriggered] = useState(false)
  const [accuracyBeats, setAccuracyBeats] = useState<NoteResultLabel[]>([])
  const [beatNoteLabels, setBeatNoteLabels] = useState<string[]>([])
  const [lastWindowResult, setLastWindowResult] = useState<NoteResultLabel | null>(null)
  const [windowFlashToken, setWindowFlashToken] = useState(0)
  const [quickCoachText, setQuickCoachText] = useState<string | null>(null)
  const [tabNoteQueue, setTabNoteQueue] = useState<TabNoteQueueEntry[]>([])
  const [lastFretResult, setLastFretResult] = useState<FretCellResult | null>(null)

  targetMidiRef.current = targetMidi

  useEffect(() => {
    recordingRef.current = recording
  }, [recording])

  useEffect(() => {
    return () => {
      aliveRef.current = false
      if (fretResultClearRef.current) clearTimeout(fretResultClearRef.current)
    }
  }, [])

  const pruneRmsHistory = useCallback((nowMs: number) => {
    const h = rmsHistoryRef.current
    const cutoff = nowMs - 4000
    while (h.length > 0 && h[0]!.t < cutoff) {
      h.shift()
    }
  }, [])

  const mapResultToFretTint = (r: NoteResultLabel): 'hit' | 'close' | 'miss' | null => {
    if (r === 'hit' || r === 'vibrato') return 'hit'
    if (r === 'close') return 'close'
    if (r === 'miss') return 'miss'
    return null
  }

  const closeAndScoreBeat = useCallback(
    (closedBeatIndex: number) => {
      const now = Date.now()
      const beatSec = beatDurationSecFromTempo(tempo)
      const beatMs = beatSec * 1000

      const peakRecent = peakRmsInWindow(rmsHistoryRef.current, now)
      const ghostThresh = effectiveRmsSignalGate(
        dynamicGhostRmsThreshold(peakRecent),
        useSessionPrefsStore.getState().getActiveNoiseGateThresholdRms(),
      )
      const beatMax = beatMaxRmsRef.current
      beatMaxRmsRef.current = 0

      const contourScratch = [...contourScratchRef.current]
      contourScratchRef.current = []

      const storeApi = useAppStore.getState()
      const adapted = storeApi.currentSession?.adaptedCentsTolerance ?? CENTS_TOLERANCE
      const targetMidiNow = targetMidiRef.current
      const labelAtClose = pitchClassLabelFromMidi(targetMidiNow)

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
        const tabPos = lastTabPositionRef.current
        const resolvedCell = resolveFretCell({ ...(tabPos ?? {}), midi: targetMidiNow })
        storeApi.pushScoredBeat({
          result,
          contour: contourForStore,
          targetMidi: targetMidiNow,
          driftMsContribution: driftMs,
          fretCell: resolvedCell,
        })
      }

      patternRef.current.push(result)
      beatNoteLabelsRef.current.push(labelAtClose)
      setAccuracyBeats([...patternRef.current])
      setBeatNoteLabels([...beatNoteLabelsRef.current])

      const tint = mapResultToFretTint(result)
      if (tint) {
        const pos = lastTabPositionRef.current
        const cell = resolveFretCell({
          ...(pos ?? {}),
          midi: targetMidiNow,
        })
        if (cell) {
          if (fretResultClearRef.current) clearTimeout(fretResultClearRef.current)
          setLastFretResult({ row: cell.row, fret: cell.fret, result: tint })
          fretResultClearRef.current = setTimeout(() => {
            setLastFretResult(null)
            fretResultClearRef.current = null
          }, 1200)
        }
      }

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
    [tempo],
  )

  const resetAccuracyTracking = useCallback(() => {
    patternRef.current = []
    beatNoteLabelsRef.current = []
    setAccuracyBeats([])
    setBeatNoteLabels([])
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
    setLastFretResult(null)
    if (fretResultClearRef.current) {
      clearTimeout(fretResultClearRef.current)
      fretResultClearRef.current = null
    }
  }, [])

  const startCapture = useCallback(async () => {
    setStatus('Starting mic + recorder…')
    setQuickCoachText(null)
    stoppingCaptureRef.current = false
    resetAccuracyTracking()
    useSessionPlayStore.getState().setLastTakeAnchorSec(null)
    useAppStore.getState().initSessionForCapture()
    recordStartMsRef.current = Date.now()
    const anchor = tickRef.current?.positionSec ?? 0
    anchorPosRef.current = anchor
    try {
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
      setRecordingWallClockStartedAtMs(Date.now())
      setPitchRunning(true)
      setStatus('Capturing performance')
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      setRecordingWallClockStartedAtMs(null)
      if (message === 'MIC_PERMISSION_DENIED') {
        setStatus('Allow microphone access to capture your playing.')
      } else {
        setStatus(`Capture error: ${message}`)
      }
      try {
        await recorderRef.current.stop()
      } catch {
        /* ignore */
      }
      try {
        await stop()
      } catch {
        /* ignore */
      }
      throw e
    }
  }, [resetAccuracyTracking, start, pruneRmsHistory])

  const stopCapture = useCallback(
    async (reason: 'done' | 'silence') => {
      if (!recording && !pitchRunning) return
      stoppingCaptureRef.current = true
      let patternSnapshot: NoteResultLabel[] = []
      try {
        const beatSec = beatDurationSecFromTempo(tempo)
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
        setRecordingWallClockStartedAtMs(null)
        setPitchRunning(false)
        useSessionPlayStore.getState().setLastTakeAnchorSec(anchorPosRef.current)
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
    [pitchRunning, recording, setLatestTake, stop, tempo, closeAndScoreBeat],
  )

  useEffect(() => {
    return () => {
      void stop().catch(() => {})
      void recorderRef.current.stop().catch(() => {})
    }
  }, [stop])

  useEffect(() => {
    if (!recording) return
    const beatSec = beatDurationSecFromTempo(tempo)
    const id = setInterval(() => {
      if (stoppingCaptureRef.current) return
      const ctx = tickRef.current
      const idx = captureBeatIndexFromTick({
        tick: ctx ? { playing: ctx.playing, positionSec: ctx.positionSec } : null,
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
  }, [tempo, recording, closeAndScoreBeat])

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

  const onNoteEvent = useCallback((evt: NoteEventMessage) => {
    const midi = Math.round(evt.midi)
    if (evt.string != null && evt.fret != null && Number.isFinite(evt.string) && Number.isFinite(evt.fret)) {
      lastTabPositionRef.current = { string: evt.string, fret: evt.fret }
    } else {
      lastTabPositionRef.current = { midi }
    }
    setNextPreviewMidi(prevMidiForPreviewRef.current)
    prevMidiForPreviewRef.current = midi
    setTargetMidi(midi)
    setTargetLabel(pitchClassLabelFromMidi(midi))
    setTabNoteQueue((prev) => {
      const next: TabNoteQueueEntry[] = [
        ...prev,
        {
          midi,
          label: pitchClassLabelFromMidi(midi),
          beat: typeof evt.beat === 'number' ? evt.beat : 0,
          string: evt.string,
          fret: evt.fret,
        },
      ]
      return next.length > MAX_QUEUE ? next.slice(-MAX_QUEUE) : next
    })
  }, [])

  const playbackTick = useCallback((ctx: PlaybackTickContext) => {
    tickRef.current = ctx
  }, [])

  return {
    stemTabRef,
    pitchRunning,
    recording,
    recordingWallClockStartedAtMs,
    take,
    status,
    targetLabel,
    targetMidi,
    nextPreviewMidi,
    centsFromTarget,
    autostopTriggered,
    accuracyBeats,
    beatNoteLabels,
    lastWindowResult,
    windowFlashToken,
    quickCoachText,
    tabNoteQueue,
    lastFretResult,
    setQuickCoachText,
    setAutostopTriggered,
    startCapture,
    stopCapture,
    onNoteEvent,
    playbackTick,
    prevMidiForPreviewRef,
  }
}
