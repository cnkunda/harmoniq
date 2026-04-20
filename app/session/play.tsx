import { useRouter } from 'expo-router'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Platform, Text, View } from 'react-native'
import Animated, { FadeIn } from 'react-native-reanimated'

import { speak, stop as stopVoiceCoach } from '@/src/audio/voiceCoach'
import { CoachNote } from '@/components/CoachNote'
import { DemoTourCallout } from '@/components/DemoTourCallout'
import { ErrorBanner } from '@/components/ErrorBanner'
import { FretboardDiagram } from '@/components/FretboardDiagram'
import { PlayCaptureCard, PlayStemRowScoringCard } from '@/components/play'
import { SessionNoteDetailModal } from '@/components/SessionNoteDetailModal'
import { SessionStemAndTab } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { useMetronomeDefaultOn } from '@/src/settings/useMetronomeDefaultOn'
import { DEMO_TOUR_CALLOUT, DEMO_TOUR_SUBTITLE } from '@/src/demo/demoSessionTourCopy'
import { useIsDemoLesson } from '@/src/demo/useIsDemoLesson'
import { sessionHref } from '@/src/constants/sessionFlow'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
import { mapMicPermissionDenied, toErrorBannerProps, type MappedUiError } from '@/src/errors/mapErrorToUi'
import { openHarmoniqAppSettings } from '@/src/errors/openHarmoniqAppSettings'
import { capoSuggestion } from '@/src/music/capoSuggestion'
import { buildNoteSelectionDetail } from '@/src/music/noteSelectionDetail'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useAppStore } from '@/src/stores/useAppStore'
import { usePlayCapture } from '@/src/session/usePlayCapture'
import { useStepCoachNarration } from '@/src/session/useStepCoachNarration'
import { useFretboardTuner } from '@/src/session/useFretboardTuner'
import { CENTS_TOLERANCE } from '@/src/utils/practiceConfig'
import { hitInnerThresholdCents } from '@/src/session/noteAccuracyBeats'
import type { NoteEventMessage } from '@/types/tabMessage'

export default function PlayScreen() {
  const isDemo = useIsDemoLesson()
  const router = useRouter()
  const recordingRef = useRef(false)
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
  const adaptedCentsTolerance = useAppStore(
    (s) => s.currentSession?.adaptedCentsTolerance ?? CENTS_TOLERANCE,
  )
  const currentStreak = useAppStore((s) => s.currentSession?.currentStreak ?? 0)

  const innerTol = hitInnerThresholdCents(adaptedCentsTolerance)

  const {
    stemTabRef,
    recording,
    recordingWallClockStartedAtMs,
    take,
    status,
    targetMidi,
    nextPreviewMidi,
    centsFromTarget,
    autostopTriggered,
    accuracyBeats,
    beatNoteLabels,
    quickCoachText,
    tabNoteQueue,
    lastFretResult,
    lastWindowResult,
    windowFlashToken,
    startCapture,
    stopCapture,
    onNoteEvent: hookOnNoteEvent,
    playbackTick,
  } = usePlayCapture(lesson?.tempo)

  recordingRef.current = recording
  useStepCoachNarration(() => recordingRef.current)

  useEffect(() => {
    if (recording) stopVoiceCoach()
  }, [recording])

  useEffect(() => {
    if (!quickCoachText?.trim() || recording) return
    speak(quickCoachText.trim())
  }, [quickCoachText, recording])

  const [micError, setMicError] = useState<MappedUiError | null>(null)
  const [selectedNote, setSelectedNote] = useState<{ string?: number; fret?: number; midi?: number } | null>(null)
  const [fretPulseKey, setFretPulseKey] = useState(0)
  const [noteModalOpen, setNoteModalOpen] = useState(false)
  const { state: tunerState, toggleTuner, startCalibration } = useFretboardTuner({ disableWhen: recording })

  const activeMicProfile = useSessionPrefsStore((s) => s.activeMicProfile)
  const micNoiseGateRms = useSessionPrefsStore((s) => {
    const id = s.activeMicProfile
    const v = s.calibrationGateRmsByProfile[id]
    return typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : null
  })

  const selectionDetail = useMemo(() => buildNoteSelectionDetail(keyLabel, selectedNote), [keyLabel, selectedNote])

  const handleToggleCapture = () => {
    if (!recording) setMicError(null)
    void (recording ? stopCapture('done') : startCapture()).catch((e) => {
      const message = e instanceof Error ? e.message : String(e)
      if (message === 'MIC_PERMISSION_DENIED') {
        setMicError(mapMicPermissionDenied(Platform.OS))
      }
      // status is managed inside the hook; surface permission UX here
      if (message !== 'MIC_PERMISSION_DENIED') {
        setMicError(null)
      }
    })
  }

  const toggleFretboardTuner = () => {
    if (recording) return
    void toggleTuner().catch((e) => {
      const message = e instanceof Error ? e.message : String(e)
      if (message === 'MIC_PERMISSION_DENIED') {
        setMicError(mapMicPermissionDenied(Platform.OS))
      }
    })
  }

  return (
    <SessionStepScreen
      title="Play"
      subtitle={
        isDemo
          ? DEMO_TOUR_SUBTITLE.play
          : 'Mute the guitar stem, follow the tab, and capture your take — scoring tracks pitch against each tab note and beat.'
      }
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Next: Review"
      onNext={() => router.push(sessionHref('review'))}
    >
      <View className="gap-5">
        {isDemo ? <DemoTourCallout>{DEMO_TOUR_CALLOUT.play}</DemoTourCallout> : null}
        {typeof __DEV__ !== 'undefined' && __DEV__ ? (
          <Text className="rounded-lg border border-dashed border-wood-600/35 bg-cream-dark/40 px-3 py-2 font-mono text-xs text-muted-brown">
            noiseGateThresholdRms ({activeMicProfile}):{' '}
            {micNoiseGateRms != null ? micNoiseGateRms.toFixed(4) : '—'} (Commit 62 calibration)
          </Text>
        ) : null}
        <SessionStemAndTab
          ref={stemTabRef}
          tabRenderPreset="play"
          lessonPlaybackCardVariant="play"
          captureRecording={recording}
          playCaptureSlot={(ctx) => (
            <PlayCaptureCard
              {...ctx}
              recording={recording}
              status={status}
              take={take}
              autostopTriggered={autostopTriggered}
              onToggleCapture={handleToggleCapture}
              recordingWallClockStartedAtMs={recordingWallClockStartedAtMs}
            />
          )}
          stemsColumnReplacement={
            <PlayStemRowScoringCard
              currentStreak={currentStreak}
              adaptedCentsTolerance={adaptedCentsTolerance}
              innerToleranceCents={innerTol}
              queue={tabNoteQueue}
              beats={accuracyBeats}
              noteLabels={beatNoteLabels}
              recording={recording}
              centsFromTarget={centsFromTarget}
              targetMidi={targetMidi}
              nextPreviewMidi={nextPreviewMidi}
              windowResult={lastWindowResult}
              windowFlashToken={windowFlashToken}
            />
          }
          initialMetronomeOn={initialMetronomeOn}
          initialStemMuteById={{ guitar: true, bass: false, drums: false, vocals: true, piano: true, other: true }}
          onPlaybackTick={playbackTick}
          onNoteEvent={(evt: NoteEventMessage) => {
            hookOnNoteEvent(evt)
            setSelectedNote({ string: evt.string, fret: evt.fret, midi: Math.round(evt.midi) })
            setFretPulseKey((k) => k + 1)
            if (evt.fromScoreTap) {
              setNoteModalOpen(true)
            }
          }}
        />

        <View className="w-full min-w-0">
          <FretboardDiagram
            keyLabel={keyLabel}
            positionLabel={positionLabel}
            capoText={capoText}
            selectedNote={selectedNote}
            pulseKey={fretPulseKey}
            lastCellResult={lastFretResult}
            enableKeyboardInput
            showTuneControl
            tuneActive={tunerState.active}
            tuneDisabled={recording}
            tuneCalibrating={tunerState.calibrating}
            onToggleTune={toggleFretboardTuner}
            onCalibrateTune={startCalibration}
            tunerState={tunerState}
            onSelectNote={(note) => {
              setSelectedNote(note)
              setFretPulseKey((k) => k + 1)
              setNoteModalOpen(true)
            }}
          />
        </View>

        {quickCoachText ? (
          <Animated.View entering={FadeIn.duration(320)}>
            <CoachNote text={quickCoachText} />
          </Animated.View>
        ) : null}

        {micError ? (
          <ErrorBanner
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
        <SessionNoteDetailModal
          detail={selectionDetail}
          visible={noteModalOpen}
          onClose={() => setNoteModalOpen(false)}
        />
        {section ? (
          <Text className="font-mono text-[10px] text-muted-brown">
            Section: {String(section.label ?? 'Section')} {lesson?.key ? `| Key: ${lesson.key}` : ''}
          </Text>
        ) : null}
      </View>
    </SessionStepScreen>
  )
}
