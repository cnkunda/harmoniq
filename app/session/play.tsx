import { useRouter } from 'expo-router'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Platform, Text, View } from 'react-native'
import Animated, { FadeIn } from 'react-native-reanimated'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { CoachFeedbackPrompt } from '@/components/CoachFeedbackPrompt'
import { CoachNote } from '@/components/CoachNote'
import { DemoTourCallout } from '@/components/DemoTourCallout'
import { ErrorBanner } from '@/components/ErrorBanner'
import { FretboardDiagram } from '@/components/FretboardDiagram'
import { GhostPlayerControl } from '@/components/GhostPlayerControl'
import { PlayCaptureCard, PlayStemRowScoringCard } from '@/components/play'
import { SessionNoteDetailModal } from '@/components/SessionNoteDetailModal'
import { SessionStemAndTab } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { speak, stop as stopVoiceCoach } from '@/src/audio/voiceCoach'
import { sessionHref } from '@/src/constants/sessionFlow'
import { getLatestGhostReference } from '@/src/db/client'
import { DEMO_TOUR_CALLOUT, DEMO_TOUR_SUBTITLE } from '@/src/demo/demoSessionTourCopy'
import { useIsDemoLesson } from '@/src/demo/useIsDemoLesson'
import { mapMicPermissionDenied, toErrorBannerProps, type MappedUiError } from '@/src/errors/mapErrorToUi'
import { openHarmoniqAppSettings } from '@/src/errors/openHarmoniqAppSettings'
import { capoSuggestion } from '@/src/music/capoSuggestion'
import { buildNoteSelectionDetail } from '@/src/music/noteSelectionDetail'
import { commitPendingGhostTakeIfNeeded } from '@/src/session/commitPendingGhostTake'
import { hitInnerThresholdCents } from '@/src/session/noteAccuracyBeats'
import { ghostReferenceToPlaybackUri } from '@/src/session/persistGhostTake'
import { useFretboardTuner } from '@/src/session/useFretboardTuner'
import { usePlayCapture } from '@/src/session/usePlayCapture'
import { useStepCoachNarration } from '@/src/session/useStepCoachNarration'
import type { PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import { MusicProvider, useMusicActions } from '@/src/context/MusicContext'
import { useMusicTimelineData } from '@/src/session/useMusicTimelineData'
import { useMetronomeDefaultOn } from '@/src/settings/useMetronomeDefaultOn'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSessionPlayStore } from '@/src/stores/sessionPlayStore'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
import { useAppStore } from '@/src/stores/useAppStore'
import { CENTS_TOLERANCE } from '@/src/utils/practiceConfig'
import type { NoteEventMessage } from '@/types/tabMessage'
import * as FileSystem from 'expo-file-system/legacy'

export default function PlayScreen() {
  const { chordEvents, soloNotesArr, barTimestamps } = useMusicTimelineData()

  return (
    <MusicProvider chordEvents={chordEvents} soloNotes={soloNotesArr} barTimestamps={barTimestamps}>
      <PlayScreenInner />
    </MusicProvider>
  )
}

function PlayScreenInner() {
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
  const musicActions = useMusicActions()

  const handlePlaybackTick = useCallback(
    (ctx: PlaybackTickContext) => {
      playbackTick(ctx)
      musicActions.setPosition(ctx.positionSec * 1000)
      musicActions.setPlaying(ctx.playing)
    },
    [playbackTick, musicActions],
  )

  useEffect(() => {
    musicActions.setPosition(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const activeMicProfile = useSessionPrefsStore((s) => s.activeMicProfile)
  const micNoiseGateRms = useSessionPrefsStore((s) => {
    const id = s.activeMicProfile
    const v = s.calibrationGateRmsByProfile[id]
    return typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : null
  })

  const selectionDetail = useMemo(() => buildNoteSelectionDetail(keyLabel, selectedNote), [keyLabel, selectedNote])

  const pendingGhostReference = useSessionPlayStore((s) => s.pendingGhostReference)
  const setPendingGhostReference = useSessionPlayStore((s) => s.setPendingGhostReference)

  const [ghostPlaybackUri, setGhostPlaybackUri] = useState<string | null>(null)
  const ghostBlobRevokeRef = useRef<(() => void) | null>(null)
  const [ghostAnchorSecForMix, setGhostAnchorSecForMix] = useState<number | null>(null)
  const [ghostRecordedLabel, setGhostRecordedLabel] = useState<string | null>(null)
  const [playWithGhost, setPlayWithGhost] = useState(false)

  useEffect(() => {
    let alive = true
    async function loadGhost() {
      const jobId = lesson?.job_id?.trim()
      if (!jobId) {
        setGhostPlaybackUri(null)
        setGhostAnchorSecForMix(null)
        setGhostRecordedLabel(null)
        setPlayWithGhost(false)
        return
      }
      try {
        const row = await getLatestGhostReference(jobId, sectionIndex)
        if (!alive) return
        if (!row) {
          setGhostPlaybackUri(null)
          setGhostAnchorSecForMix(null)
          setGhostRecordedLabel(null)
          setPlayWithGhost(false)
          return
        }
        setGhostRecordedLabel(row.date)
        setGhostAnchorSecForMix(row.ghost_anchor_sec ?? 0)
        if (Platform.OS !== 'web' && row.waveform_user_path) {
          const info = await FileSystem.getInfoAsync(row.waveform_user_path)
          if (!info.exists) {
            console.warn('[ghost] saved ghost file missing — disabling ghost mix', row.waveform_user_path)
            setGhostPlaybackUri(null)
            setPlayWithGhost(false)
            return
          }
        }
        const uri = ghostReferenceToPlaybackUri(row)
        if (ghostBlobRevokeRef.current) {
          ghostBlobRevokeRef.current()
          ghostBlobRevokeRef.current = null
        }
        setGhostPlaybackUri(uri)
        if (uri?.startsWith('blob:')) {
          ghostBlobRevokeRef.current = () => URL.revokeObjectURL(uri)
        }
        setPlayWithGhost(true)
      } catch (e) {
        console.warn('[ghost] load failed', e)
        if (!alive) return
        setGhostPlaybackUri(null)
        setPlayWithGhost(false)
      }
    }
    void loadGhost()
    return () => {
      alive = false
      if (ghostBlobRevokeRef.current) {
        ghostBlobRevokeRef.current()
        ghostBlobRevokeRef.current = null
      }
    }
  }, [lesson?.job_id, sectionIndex])

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
      onNext={() => {
        void commitPendingGhostTakeIfNeeded({ lesson, sectionIndex }).finally(() =>
          router.push(sessionHref('review')),
        )
      }}
    >
      <View className="gap-5">
        {isDemo ? <DemoTourCallout>{DEMO_TOUR_CALLOUT.play}</DemoTourCallout> : null}
        {typeof __DEV__ !== 'undefined' && __DEV__ ? (
          <Text className="rounded-lg border border-dashed border-wood-600/35 bg-cream-dark/40 px-3 py-2 font-mono text-xs text-muted-light">
            noiseGateThresholdRms ({activeMicProfile}):{' '}
            {micNoiseGateRms != null ? micNoiseGateRms.toFixed(4) : '—'} (Commit 62 calibration)
          </Text>
        ) : null}
        <SessionStemAndTab
          ref={stemTabRef}
          tabRenderPreset="light"
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
          ghostStemPlaybackUri={ghostPlaybackUri}
          ghostAnchorSec={ghostAnchorSecForMix}
          playGhostWhileRecording={Boolean(playWithGhost && ghostPlaybackUri)}
          tabFrameClassName="mt-2 min-h-[328px] w-full px-2"
          insertBetweenStemAndTab={
            <View className="gap-5">
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
                  <CoachFeedbackPrompt
                    focusArea={(section?.coach_note ? section.focus_area as string | null : null) ?? null}
                    onFeedbackSubmitted={(rating: 'helpful' | 'repetitive' | 'neutral' | 'skipped') => {
                      console.log('Coach feedback submitted:', rating)
                    }}
                  />
                </Animated.View>
              ) : null}
            </View>
          }
          onPlaybackTick={handlePlaybackTick}
          onNoteEvent={(evt: NoteEventMessage) => {
            hookOnNoteEvent(evt)
            setSelectedNote({ string: evt.string, fret: evt.fret, midi: Math.round(evt.midi) })
            setFretPulseKey((k) => k + 1)
            if (evt.fromScoreTap) {
              setNoteModalOpen(true)
            }
          }}
        />

        <GhostPlayerControl
          playWithGhost={playWithGhost}
          onTogglePlayWithGhost={setPlayWithGhost}
          ghostRecordedAtLabel={ghostRecordedLabel}
          hasGhost={Boolean(ghostPlaybackUri)}
        />

        {take && take.audioBytes.length > 0 ? (
          <View className="rounded-xl border border-wood-600/35 bg-cream-dark/25 px-3 py-2">
            <Text className="mb-2 font-sans-medium text-[10px] uppercase tracking-[0.12em] text-muted-light">
              Ghost reference take
            </Text>
            <View className="flex-row items-center justify-between gap-2">
              <Text className="min-w-0 flex-1 font-sans text-xs text-wood-900">
                Flag this capture as your ghost reference for this section (saved when you open Review).
              </Text>
              <AnimatedPressable
                accessibilityRole="switch"
                accessibilityState={{ checked: pendingGhostReference }}
                onPress={() => setPendingGhostReference(!pendingGhostReference)}
                className={`rounded-full px-3 py-1.5 ${pendingGhostReference ? 'bg-amber-accent/90' : 'border border-wood-600/50 bg-wood-900/15'}`}
              >
                <Text
                  className={`font-sans-medium text-xs ${pendingGhostReference ? 'text-wood-900' : 'text-muted-light'}`}
                >
                  {pendingGhostReference ? 'On' : 'Off'}
                </Text>
              </AnimatedPressable>
            </View>
          </View>
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
          <Text className="font-mono text-[10px] text-muted-light">
            Section: {String(section.label ?? 'Section')} {lesson?.key ? `| Key: ${lesson.key}` : ''}
          </Text>
        ) : null}
      </View>
    </SessionStepScreen>
  )
}
