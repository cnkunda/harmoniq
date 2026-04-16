import { useRouter } from 'expo-router'
import { useMemo, useState } from 'react'
import { Platform, Text, View } from 'react-native'
import Animated, { FadeIn } from 'react-native-reanimated'

import { CoachNote } from '@/components/CoachNote'
import { ErrorBanner } from '@/components/ErrorBanner'
import { FretboardDiagram } from '@/components/FretboardDiagram'
import {
  PlayBeatAccuracyPanel,
  PlayCaptureControls,
  PlayPitchLadderVertical,
  PlayTargetNoteQueue,
} from '@/components/play'
import { SessionNoteDetailModal } from '@/components/SessionNoteDetailModal'
import { SessionStemAndTab } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { useMetronomeDefaultOn } from '@/src/settings/useMetronomeDefaultOn'
import { sessionHref } from '@/src/constants/sessionFlow'
import { mapMicPermissionDenied, toErrorBannerProps, type MappedUiError } from '@/src/errors/mapErrorToUi'
import { openHarmoniqAppSettings } from '@/src/errors/openHarmoniqAppSettings'
import { capoSuggestion } from '@/src/music/capoSuggestion'
import { buildNoteSelectionDetail } from '@/src/music/noteSelectionDetail'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useAppStore } from '@/src/stores/useAppStore'
import { usePlayCapture } from '@/src/session/usePlayCapture'
import { useFretboardTuner } from '@/src/session/useFretboardTuner'
import { CENTS_TOLERANCE } from '@/src/utils/practiceConfig'
import { hitInnerThresholdCents } from '@/src/session/noteAccuracyBeats'
import type { NoteEventMessage } from '@/types/tabMessage'

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
  const adaptedCentsTolerance = useAppStore(
    (s) => s.currentSession?.adaptedCentsTolerance ?? CENTS_TOLERANCE,
  )
  const currentStreak = useAppStore((s) => s.currentSession?.currentStreak ?? 0)

  const innerTol = hitInnerThresholdCents(adaptedCentsTolerance)

  const {
    stemTabRef,
    recording,
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

  const [micError, setMicError] = useState<MappedUiError | null>(null)
  const [selectedNote, setSelectedNote] = useState<{ string?: number; fret?: number; midi?: number } | null>(null)
  const [fretPulseKey, setFretPulseKey] = useState(0)
  const [noteModalOpen, setNoteModalOpen] = useState(false)
  const { state: tunerState, toggleTuner, startCalibration } = useFretboardTuner({ disableWhen: recording })

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
      subtitle="Pitch targets follow the tab note-by-note; each beat scores your tuning against the current target. Guitar stem muted — capture an optional take."
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Next: Review"
      onNext={() => router.push(sessionHref('review'))}
    >
      <PlayCaptureControls
        recording={recording}
        status={status}
        take={take}
        autostopTriggered={autostopTriggered}
        onToggleCapture={handleToggleCapture}
      />

      <View className="mt-4 flex-col gap-3 md:flex-row md:items-stretch">
        <View className="w-full flex-col gap-3 md:w-1/3 md:min-w-0 md:flex-shrink-0">
          <PlayTargetNoteQueue queue={tabNoteQueue} isActive={recording} />
          <PlayBeatAccuracyPanel beats={accuracyBeats} noteLabels={beatNoteLabels} />
        </View>
        <View className="min-w-0 flex-1 flex-col md:min-h-0">
          <PlayPitchLadderVertical
            className="md:flex-1"
            cents={centsFromTarget}
            isActive={recording}
            adaptedCentsTolerance={adaptedCentsTolerance}
            targetMidi={targetMidi}
            nextTargetMidi={nextPreviewMidi}
            windowResult={lastWindowResult}
            windowFlashToken={windowFlashToken}
          />
          <Text className="mt-2 shrink-0 font-sans text-xs text-muted-brown">
            Clean streak: {currentStreak} beat{currentStreak === 1 ? '' : 's'} · Tolerance ±
            {Math.round(adaptedCentsTolerance)}¢ (adapts) · inner ≤{Math.round(innerTol)}¢
          </Text>
        </View>
      </View>

      <View className="w-full">
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
        <Animated.View className="mt-3" entering={FadeIn.duration(320)}>
          <CoachNote text={quickCoachText} />
        </Animated.View>
      ) : null}

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

      <SessionStemAndTab
        ref={stemTabRef}
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
