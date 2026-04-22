import { Buffer } from 'buffer'
import * as FileSystem from 'expo-file-system/legacy'
import { useRouter } from 'expo-router'
import * as Sharing from 'expo-sharing'
import * as WebBrowser from 'expo-web-browser'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Platform, Pressable, Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { DemoTourCallout } from '@/components/DemoTourCallout'
import { ErrorBanner } from '@/components/ErrorBanner'
import { PhrasingWaveformVisualizer } from '@/components/PhrasingWaveformVisualizer'
import { ScoreSummaryCard } from '@/components/ReviewSessionPanel'
import { SessionPitchReview } from '@/components/SessionPitchReview'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { toast } from '@/components/ToastConfig'
import { ApiError, submitExportJob, submitScore } from '@/src/api/analyze'
import { isHarmoniqSkillMutationSkipped } from '@/src/config'
import { sessionEntryHref } from '@/src/constants/sessionFlow'
import {
    applyReviewSkillUpdates,
    getAllSkillNodes,
    getAppPref,
    getLatestGhostReference,
    getSessionCount,
    insertLickRow,
    insertSessionRow,
} from '@/src/db/client'
import { PREF_MOOD_CHECK_LAST_MOOD } from '@/src/db/schema'
import type { GhostReferenceRow } from '@/src/db/types'
import { DEMO_TOUR_CALLOUT, DEMO_TOUR_SUBTITLE } from '@/src/demo/demoSessionTourCopy'
import { useIsDemoLesson } from '@/src/demo/useIsDemoLesson'
import type { MappedUiError } from '@/src/errors/mapErrorToUi'
import { mapScoreFlowError, toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import { openHarmoniqAppSettings } from '@/src/errors/openHarmoniqAppSettings'
import { coachReviewFromScoreResult } from '@/src/session/coachReviewFromScoreResult'
import { commitPendingGhostTakeIfNeeded } from '@/src/session/commitPendingGhostTake'
import { navigateToPracticePlanSlot } from '@/src/session/practicePlanNavigation'
import {
    sessionAccuracy01FromScoreResult,
    timingStability01FromScoreResult,
} from '@/src/session/scoreProgressSignals'
import { computeSkillMutations } from '@/src/session/skillMutator'
import { useDnaStore } from '@/src/stores/dnaStore'
import { useLessonStore } from '@/src/stores/lessonStore'
import { usePlanStore } from '@/src/stores/planStore'
import { useSessionPlayStore } from '@/src/stores/sessionPlayStore'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
import { useSkillStore } from '@/src/stores/skillStore'
import { useAppStore } from '@/src/stores/useAppStore'
import type { ScoreResult } from '@/src/types'
import { bytesToBase64 } from '@/src/utils/bytesToBase64'
import { shareExportedBlob } from '@/src/utils/exportShare'
import { firstLessonStemRelPath, serializeLessonStemsJson } from '@/src/utils/lessonAudio'
import { readSectionTabPayloads } from '@/src/utils/lessonTabs'
import { BPM_DRIFT_NOTE_MINIMUM } from '@/src/utils/practiceConfig'

function midiVarLen(value: number): number[] {
  let buffer = value & 0x7f
  const out: number[] = []
  while ((value >>= 7) > 0) {
    buffer <<= 8
    buffer |= (value & 0x7f) | 0x80
  }
  for (;;) {
    out.push(buffer & 0xff)
    if (buffer & 0x80) buffer >>= 8
    else break
  }
  return out
}

function buildFallbackMidiBase64(tempoBpm: number | null | undefined, key: string | null | undefined): string {
  const noteNames = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
  const root = typeof key === 'string' ? key.split(/\s+/)[0].toUpperCase() : 'A'
  const idx = noteNames.indexOf(root)
  const rootPc = idx >= 0 ? idx : 9
  const rootMidi = 60 + rootPc
  const tpq = 480
  const qnUs = Math.max(240000, Math.min(1200000, Math.round(60000000 / Math.max(40, Math.min(220, tempoBpm ?? 90)))))
  const tempoBytes = [(qnUs >> 16) & 0xff, (qnUs >> 8) & 0xff, qnUs & 0xff]

  const track: number[] = []
  track.push(0x00, 0xff, 0x51, 0x03, ...tempoBytes) // tempo meta
  track.push(0x00, 0xc0, 0x18) // nylon guitar
  const pattern = [0, 2, 4, 5, 7, 9, 7, 5]
  for (const step of pattern) {
    const midi = rootMidi + step
    track.push(0x00, 0x90, midi, 92) // note on
    track.push(...midiVarLen(tpq), 0x80, midi, 0x00) // note off after quarter
  }
  track.push(0x00, 0xff, 0x2f, 0x00) // end track

  const header = [0x4d, 0x54, 0x68, 0x64, 0x00, 0x00, 0x00, 0x06, 0x00, 0x00, 0x00, 0x01, (tpq >> 8) & 0xff, tpq & 0xff]
  const trackLen = track.length
  const trackHeader = [
    0x4d,
    0x54,
    0x72,
    0x6b,
    (trackLen >> 24) & 0xff,
    (trackLen >> 16) & 0xff,
    (trackLen >> 8) & 0xff,
    trackLen & 0xff,
  ]
  const bytes = new Uint8Array([...header, ...trackHeader, ...track])
  return Buffer.from(bytes).toString('base64')
}

export default function ReviewScreen() {
  const isDemo = useIsDemoLesson()
  const router = useRouter()
  const lesson = useLessonStore((s) => s.lesson)
  const sectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const saveLesson = useLessonStore((s) => s.saveLesson)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)
  const section = lesson?.sections?.[sectionIndex]
  const latestTake = useSessionPlayStore((s) => s.latestTake)
  const clearLatestTake = useSessionPlayStore((s) => s.clearLatestTake)
  const currentSession = useAppStore((s) => s.currentSession)
  const [busy, setBusy] = useState(false)
  const [score, setScore] = useState<ScoreResult | null>(null)
  const [reviewError, setReviewError] = useState<MappedUiError | null>(null)
  const [exportState, setExportState] = useState<string>('Idle')
  const [sessionCount, setSessionCount] = useState<number | null>(null)
  const [savingLick, setSavingLick] = useState(false)
  const [ghostRowForViz, setGhostRowForViz] = useState<GhostReferenceRow | null>(null)

  const tabs = useMemo(() => readSectionTabPayloads(section), [section])
  const hasMoreSectionsInLesson = useMemo(() => {
    const n = lesson?.sections?.length ?? 0
    return n > 0 && sectionIndex + 1 < n
  }, [lesson?.sections?.length, sectionIndex])
  const gp5ForExport = tabs.full ?? tabs.skeleton ?? tabs.alt ?? null
  const songTitleBase =
    typeof lesson?.song_title === 'string' && lesson.song_title.trim()
      ? lesson.song_title.trim()
      : `section-${sectionIndex + 1}`
  const sectionMidiBase64 =
    section && typeof section === 'object' && typeof (section as Record<string, unknown>).midi_base64 === 'string'
      ? ((section as Record<string, unknown>).midi_base64 as string)
      : null
  const midiBase64 = useMemo(
    () => sectionMidiBase64 ?? buildFallbackMidiBase64(lesson?.tempo, lesson?.key),
    [lesson?.key, lesson?.tempo, sectionMidiBase64],
  )

  const runScore = useCallback(async () => {
    if (!latestTake || latestTake.audioBytes.length === 0) {
      setReviewError({
        message: 'No performance capture yet. Go back to Play and record a short take.',
        variant: 'warning',
        actionKind: 'dismiss',
        actionLabel: 'Dismiss',
      })
      setScore(null)
      return
    }
    if (!section) {
      setReviewError({
        message: 'This section is missing data needed to score. Try another section or re-analyze the song.',
        variant: 'warning',
        actionKind: 'dismiss',
        actionLabel: 'Dismiss',
      })
      setScore(null)
      return
    }
    setBusy(true)
    setReviewError(null)
    try {
      const result = await submitScore({
        recording_wav_base64: bytesToBase64(latestTake.audioBytes),
        recording_mime_type: latestTake.mimeType,
        section: {
          ...(section && typeof section === 'object' ? section : {}),
          tempo: lesson?.tempo,
          key: lesson?.key,
          beat_grid: lesson?.beat_grid ?? [],
          bar_timestamps: lesson?.bar_timestamps ?? [],
        },
        skill_nodes: ['pitch_accuracy', 'phrasing', 'timing'],
      })
      setScore(result)
      const targeted = ['pitch_accuracy', 'phrasing', 'timing']
      const targetedSet = new Set(targeted)
      const cs = useAppStore.getState().currentSession
      const harmoniq_dna_capture =
        cs && (cs.noteTargetMidis.length > 0 || cs.bpmDriftSampleCount > 0)
          ? {
              note_target_midis: [...cs.noteTargetMidis],
              note_results: [...cs.noteResults],
              note_target_cells: cs.noteTargetCells.map((c) => (c ? { row: c.row, fret: c.fret } : null)),
              bpm_drift_ms: cs.bpmDrift,
              bpm_drift_sample_count: cs.bpmDriftSampleCount,
            }
          : undefined
      await insertSessionRow({
        id: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        song_title: typeof lesson?.song_title === 'string' ? lesson.song_title : null,
        artist: typeof lesson?.artist === 'string' ? lesson.artist : null,
        section_label:
          section && typeof section === 'object' && typeof (section as Record<string, unknown>).label === 'string'
            ? ((section as Record<string, unknown>).label as string)
            : null,
        date: new Date().toISOString(),
        coach_review: coachReviewFromScoreResult(result),
        pitch_accuracy: result.pitch_accuracy,
        phrasing_score: result.phrasing_score,
        nodes_targeted: targeted,
        review_snapshot: JSON.stringify({ ...result, harmoniq_dna_capture }),
        job_id: typeof lesson?.job_id === 'string' ? lesson.job_id.trim() : null,
        section_index: sectionIndex,
        is_ghost_reference: false,
        mood: ((await getAppPref(PREF_MOOD_CHECK_LAST_MOOD)) as 'focused' | 'loose' | 'tired' | 'on_fire' | null) ?? null,
      })
      void useDnaStore.getState().refresh()
      await applyReviewSkillUpdates({
        node_scores: result.node_scores,
        targeted_node_ids: targeted,
        node_confidence_map: Object.fromEntries(targeted.map((id) => [id, result.reliability?.confidence ?? 'medium'])),
        node_reliability_map: Object.fromEntries(
          targeted.map((id) => [id, result.reliability?.signal_quality ?? result.diagnostics?.signal_quality ?? 0.7]),
        ),
        reliability_flags: result.reliability?.reliability_flags ?? result.diagnostics?.reliability_flags ?? [],
        session_accuracy01: sessionAccuracy01FromScoreResult(result),
        session_timing_stability01: timingStability01FromScoreResult(result),
      })
      let skillStoreRefreshed = false
      if (!isHarmoniqSkillMutationSkipped()) {
        const nodes = await getAllSkillNodes()
        const nodesById = new Map(
          nodes.map((n) => [n.id, { score: n.score, technique_roll_json: n.technique_roll_json ?? null }]),
        )
        const beats = useAppStore.getState().currentSession?.noteResults ?? []
        const mutations = computeSkillMutations({ nodesById, beats, section })
        if (mutations.length > 0) {
          await useSkillStore.getState().applySessionMutation(mutations)
          skillStoreRefreshed = true
        }
      }
      if (!skillStoreRefreshed) await useSkillStore.getState().loadFromDb()
      if (__DEV__) {
        const refreshed = useSkillStore.getState().nodes
        console.log(
          '[skill] SM-2 after review',
          refreshed
            .filter((n) => targetedSet.has(n.id))
            .map((n) => ({ id: n.id, score: n.score, next_review_date: n.next_review_date, interval_days: n.interval_days })),
        )
      }
      setSessionCount(await getSessionCount())
    } catch (e) {
      setScore(null)
      setReviewError(mapScoreFlowError(e))
    } finally {
      setBusy(false)
    }
  }, [latestTake, lesson?.artist, lesson?.song_title, lesson?.bar_timestamps, lesson?.beat_grid, lesson?.key, lesson?.tempo, section])

  useEffect(() => {
    void getSessionCount().then(setSessionCount).catch(() => {})
  }, [])

  useEffect(() => {
    void commitPendingGhostTakeIfNeeded({ lesson, sectionIndex }).catch((e) =>
      console.warn('[ghost] pending persist failed', e),
    )
  }, [lesson, sectionIndex])

  useEffect(() => {
    let cancelled = false
    async function loadGhostRow() {
      const jid = typeof lesson?.job_id === 'string' ? lesson.job_id.trim() : ''
      if (!jid) {
        setGhostRowForViz(null)
        return
      }
      try {
        const row = await getLatestGhostReference(jid, sectionIndex)
        if (!cancelled) setGhostRowForViz(row)
      } catch {
        if (!cancelled) setGhostRowForViz(null)
      }
    }
    void loadGhostRow()
    return () => {
      cancelled = true
    }
  }, [lesson?.job_id, sectionIndex])

  const exportMidi = useCallback(async () => {
    if (gp5ForExport) {
      try {
        setExportState('Exporting MIDI…')
        const { blob, mimeType, contentDisposition } = await submitExportJob({
          gp5_base64: gp5ForExport,
          format: 'midi',
          title: songTitleBase,
        })
        await shareExportedBlob({
          blob,
          mimeType,
          contentDisposition,
          fallbackBase: songTitleBase,
          dialogTitle: 'Export MIDI',
        })
        setExportState('MIDI exported.')
        return
      } catch (e) {
        if (e instanceof ApiError && e.status === 422) {
          setExportState(`Export failed: ${e.message}`)
          return
        }
        // Server off, 503, or network — fall back to local MIDI when available.
      }
    }

    if (!midiBase64) {
      setExportState('No MIDI/GP5 payload found for this section.')
      return
    }
    try {
      setExportState(gp5ForExport ? 'Using offline MIDI…' : 'Exporting MIDI…')
      if (Platform.OS === 'web') {
        const dataUrl = `data:audio/midi;base64,${midiBase64}`
        const opened = await WebBrowser.openBrowserAsync(dataUrl)
        setExportState(`Export opened (${opened.type}).`)
        return
      }
      const dir = FileSystem.cacheDirectory ?? FileSystem.documentDirectory
      if (!dir) throw new Error('No writable directory for export')
      const path = `${dir}harmoniq-section-${sectionIndex + 1}.mid`
      await FileSystem.writeAsStringAsync(path, midiBase64, { encoding: FileSystem.EncodingType.Base64 })
      const canShare = await Sharing.isAvailableAsync()
      if (!canShare) throw new Error('Share sheet unavailable on this device')
      await Sharing.shareAsync(path, { mimeType: 'audio/midi', dialogTitle: 'Export MIDI' })
      setExportState('MIDI exported via share sheet.')
    } catch (e) {
      setExportState(`Export failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }, [gp5ForExport, midiBase64, sectionIndex, songTitleBase])

  const exportMusicXml = useCallback(async () => {
    if (!gp5ForExport) {
      setExportState('No GP5 tab payload for MusicXML export.')
      return
    }
    try {
      setExportState('Exporting MusicXML…')
      const { blob, mimeType, contentDisposition } = await submitExportJob({
        gp5_base64: gp5ForExport,
        format: 'musicxml',
        title: songTitleBase,
      })
      await shareExportedBlob({
        blob,
        mimeType,
        contentDisposition,
        fallbackBase: songTitleBase,
        dialogTitle: 'Export MusicXML',
      })
      setExportState('MusicXML exported.')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e)
      setExportState(`Export failed: ${msg}`)
    }
  }, [gp5ForExport, songTitleBase])

  const finish = useCallback(async () => {
    clearLatestTake()
    const sectionsLen = lesson?.sections?.length ?? 0
    if (sectionsLen > 0 && sectionIndex + 1 < sectionsLen) {
      setLessonSectionIndex(sectionIndex + 1)
      const skipTune = useSessionPrefsStore.getState().skipTuneStep
      router.replace(sessionEntryHref(skipTune))
      return
    }

    const { currentPlan, currentSlotIndex, clearPlan } = usePlanStore.getState()
    const slots = currentPlan?.slots
    const hasNext = Boolean(slots?.length && currentSlotIndex < slots.length - 1)
    const activeSlot = slots?.[currentSlotIndex]
    const slotRef =
      typeof activeSlot?.lesson_ref === 'string' && activeSlot.lesson_ref.trim().length > 0
        ? activeSlot.lesson_ref.trim()
        : null
    const currentJobId = typeof lesson?.job_id === 'string' && lesson.job_id.trim().length > 0 ? lesson.job_id.trim() : null
    /** Avoid advancing a stale plan when the user opened a different song than this slot references. */
    const planLessonConflict = Boolean(slotRef && currentJobId && slotRef !== currentJobId)

    if (currentPlan && hasNext && !planLessonConflict) {
      try {
        const nextSlot = slots?.[currentSlotIndex + 1]
        if (nextSlot?.slot_type === 'free_jam') {
          toast.success('Song practice complete — opening Jam.')
        }
        await navigateToPracticePlanSlot(router, { saveLesson, setLessonSectionIndex }, currentSlotIndex + 1)
        return
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Could not open the next plan step.')
        return
      }
    }
    if (currentPlan) clearPlan()
    router.replace('/(tabs)')
  }, [clearLatestTake, lesson?.job_id, lesson?.sections?.length, router, saveLesson, sectionIndex, setLessonSectionIndex])

  const saveLick = useCallback(async () => {
    const gp5 = tabs.full ?? tabs.skeleton ?? tabs.alt ?? null
    if (!gp5) {
      setReviewError({
        message: 'No tab is available to save for this section yet.',
        variant: 'warning',
        actionKind: 'dismiss',
        actionLabel: 'Dismiss',
      })
      return
    }
    if (!section || typeof section !== 'object') {
      setReviewError({
        message: 'Section data is missing, so this lick cannot be saved.',
        variant: 'warning',
        actionKind: 'dismiss',
        actionLabel: 'Dismiss',
      })
      return
    }
    setSavingLick(true)
    try {
      const sec = section as Record<string, unknown>
      await insertLickRow({
        id: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        song_title: typeof lesson?.song_title === 'string' ? lesson.song_title : null,
        artist: typeof lesson?.artist === 'string' ? lesson.artist : null,
        key: typeof lesson?.key === 'string' ? lesson.key : null,
        scale: null,
        position: typeof sec.primary_position === 'string' ? sec.primary_position : typeof sec.label === 'string' ? sec.label : null,
        tab_gp5_base64: gp5,
        audio_segment_path: firstLessonStemRelPath(lesson?.stems),
        stems_json: serializeLessonStemsJson(lesson?.stems),
        coach_oneliner: typeof sec.coach_note === 'string' ? sec.coach_note : null,
        technique_tags: [],
        user_annotations: [],
        date_saved: new Date().toISOString(),
      })
      toast.success('Saved to Library.')
    } catch {
      setReviewError({
        message: 'Could not save to Library. Try again in a moment.',
        variant: 'error',
        actionKind: 'dismiss',
        actionLabel: 'Dismiss',
      })
    } finally {
      setSavingLick(false)
    }
  }, [insertLickRow, lesson?.artist, lesson?.key, lesson?.song_title, lesson?.stems, section, tabs.alt, tabs.full, tabs.skeleton])

  return (
    <SessionStepScreen
      title="Review"
      subtitle={
        isDemo
          ? DEMO_TOUR_SUBTITLE.review
          : 'Session scores, optional MIDI export, and phrasing / ghost waveforms when data is available.'
      }
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel={hasMoreSectionsInLesson ? 'Next section' : 'Done'}
      onNext={finish}
    >
      {isDemo ? <DemoTourCallout>{DEMO_TOUR_CALLOUT.review}</DemoTourCallout> : null}
      <PhrasingWaveformVisualizer score={score} ghostRow={ghostRowForViz} />

      {currentSession && currentSession.noteContours.length > 0 ? (
        <View className="mt-3">
          <SessionPitchReview
            noteContours={currentSession.noteContours}
            noteTargetMidis={currentSession.noteTargetMidis}
            noteResults={currentSession.noteResults}
          />
          {currentSession.bpmDriftSampleCount >= BPM_DRIFT_NOTE_MINIMUM ? (
            <Text className="mt-2 font-sans text-xs text-muted-brown">
              Timing vs beat (mean): {currentSession.bpmDrift >= 0 ? '+' : ''}
              {Math.round(currentSession.bpmDrift)} ms — {currentSession.bpmDrift >= 0 ? 'ahead of grid' : 'behind grid'}
            </Text>
          ) : null}
          {currentSession.bestStreak > currentSession.bestStreakAtSessionStart ? (
            <Text className="mt-1 font-sans text-xs text-muted-brown">
              New high clean-streak this session: {currentSession.bestStreak} beats (previous best at start:{' '}
              {currentSession.bestStreakAtSessionStart}).
            </Text>
          ) : null}
        </View>
      ) : null}

      <View className="mt-3 flex-row flex-wrap items-center gap-2">
        <Pressable
          onPress={() => void runScore()}
          disabled={busy}
          className="rounded-lg bg-amber-accent/90 px-4 py-2 disabled:opacity-40"
          accessibilityRole="button"
        >
          <Text className="font-sans-medium text-wood-900">{busy ? 'Scoring…' : 'Run score'}</Text>
        </Pressable>
        <AnimatedPressable
          onPress={() => void exportMidi()}
          className="rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-2"
          accessibilityRole="button"
        >
          <Text className="font-sans-medium text-wood-900">Export MIDI</Text>
        </AnimatedPressable>
        <AnimatedPressable
          onPress={() => void exportMusicXml()}
          className="rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-2"
          accessibilityRole="button"
        >
          <Text className="font-sans-medium text-wood-900">Export MusicXML</Text>
        </AnimatedPressable>
        <Pressable
          onPress={() => void saveLick()}
          disabled={savingLick}
          className="rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-2 disabled:opacity-40"
          accessibilityRole="button"
        >
          <Text className="font-sans-medium text-wood-900">{savingLick ? 'Saving…' : 'Save to Library'}</Text>
        </Pressable>
        <Pressable
          onPress={() => router.push('/library')}
          className="rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-2"
          accessibilityRole="button"
        >
          <Text className="font-sans-medium text-wood-900">Open Library</Text>
        </Pressable>
      </View>

      <Text className="mt-2 font-mono text-[11px] text-muted-brown">{exportState}</Text>

      {reviewError ? (
        <ErrorBanner
          className="mt-3"
          onDismissed={() => setReviewError(null)}
          {...toErrorBannerProps(reviewError, {
            onRetry: () => {
              setReviewError(null)
              void runScore()
            },
            onDismiss: () => setReviewError(null),
            onOpenSettings: () => {
              void openHarmoniqAppSettings()
              setReviewError(null)
            },
            onContinue: () => setReviewError(null),
          })}
        />
      ) : null}

      {score ? <ScoreSummaryCard score={score} /> : null}

      {!sectionMidiBase64 && (tabs.full || tabs.skeleton || tabs.alt) ? (
        <Text className="mt-2 font-sans text-[11px] text-muted-brown">
          Using generated fallback MIDI for export (section has no `midi_base64` yet).
        </Text>
      ) : null}

      <Text className="mt-3 font-sans text-[11px] text-muted-brown">
        Recording buffer: {latestTake ? `${(latestTake.durationMs / 1000).toFixed(1)}s / ${latestTake.audioBytes.length} bytes` : 'none'}
      </Text>
      <Text className="mt-1 font-sans text-[11px] text-muted-brown">
        Persisted sessions (local DB): {sessionCount ?? '...'}
      </Text>
    </SessionStepScreen>
  )
}
