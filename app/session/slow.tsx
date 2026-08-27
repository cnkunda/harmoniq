import { useRouter } from 'expo-router'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Text, View } from 'react-native'

import { DemoTourCallout } from '@/components/DemoTourCallout'
import { FretboardDiagram } from '@/components/FretboardDiagram'
import { LoopRegionControl } from '@/components/LoopRegionControl'
import { SessionNoteDetailModal } from '@/components/SessionNoteDetailModal'
import { SessionStemAndTab } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { sessionHref } from '@/src/constants/sessionFlow'
import { MusicProvider, useMusicActions } from '@/src/context/MusicContext'
import { DEMO_TOUR_CALLOUT, DEMO_TOUR_SUBTITLE } from '@/src/demo/demoSessionTourCopy'
import { useIsDemoLesson } from '@/src/demo/useIsDemoLesson'
import { barRangeToSeconds } from '@/src/music/barLoopBounds'
import { capoSuggestion } from '@/src/music/capoSuggestion'
import { buildNoteSelectionDetail } from '@/src/music/noteSelectionDetail'
import { deriveSlowLoopRegion } from '@/src/session/slowLoopRegion'
import { useFretboardTuner } from '@/src/session/useFretboardTuner'
import { useMusicTimelineData } from '@/src/session/useMusicTimelineData'
import { useStepCoachNarration } from '@/src/session/useStepCoachNarration'
import type { PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import { useMetronomeDefaultOn } from '@/src/settings/useMetronomeDefaultOn'
import { useLessonStore } from '@/src/stores/lessonStore'
import type { NoteEventMessage, TabLoopBarRegion } from '@/types/tabMessage'

export default function SlowScreen() {
  const { chordEvents, soloNotesArr, barTimestamps } = useMusicTimelineData()

  return (
    <MusicProvider chordEvents={chordEvents} soloNotes={soloNotesArr} barTimestamps={barTimestamps}>
      <SlowScreenInner />
    </MusicProvider>
  )
}

function SlowScreenInner() {
  useStepCoachNarration()
  const isDemo = useIsDemoLesson()
  const router = useRouter()
  const initialMetronomeOn = useMetronomeDefaultOn()
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)

  const sections = (lesson?.sections ?? []) as Array<Record<string, unknown>>
  const section = sections[lessonSectionIndex]
  const keyLabel = (lesson?.key ?? 'Unknown key').toString()
  const positionLabel =
    section && typeof section.primary_position === 'string'
      ? section.primary_position
      : 'Tap a note to infer position'
  const capoText = useMemo(() => capoSuggestion(keyLabel, positionLabel), [keyLabel, positionLabel])
  const barTimestamps = lesson?.bar_timestamps ?? []
  const beatSec = lesson?.tempo && lesson.tempo > 0 ? 60 / lesson.tempo : 0.5

  const derived = useMemo(
    () => deriveSlowLoopRegion(section, sections, barTimestamps, lesson?.tempo),
    [barTimestamps, lesson?.tempo, lessonSectionIndex, section, sections],
  )

  const [loopBars, setLoopBars] = useState<TabLoopBarRegion | null>(null)
  const [selectedNote, setSelectedNote] = useState<{ string?: number; fret?: number; midi?: number } | null>(null)
  const [fretPulseKey, setFretPulseKey] = useState(0)
  const [noteModalOpen, setNoteModalOpen] = useState(false)
  const selectionDetail = useMemo(() => buildNoteSelectionDetail(keyLabel, selectedNote), [keyLabel, selectedNote])
  const { state: tunerState, toggleTuner, startCalibration } = useFretboardTuner()
  const musicActions = useMusicActions()

  const handlePlaybackTick = useCallback(
    (ctx: PlaybackTickContext) => {
      musicActions.setPosition(ctx.positionSec * 1000)
      musicActions.setPlaying(ctx.playing)
    },
    [musicActions],
  )

  useEffect(() => {
    musicActions.setPosition(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!derived) {
      setLoopBars(null)
      return
    }
    setLoopBars({
      startBarIndex: derived.startBarIndex,
      endBarIndexExclusive: derived.endBarIndexExclusive,
    })
  }, [derived?.endBarIndexExclusive, derived?.startBarIndex, lesson?.job_id, lessonSectionIndex])

  const playbackLoop = useMemo(() => {
    if (loopBars && barTimestamps.length > 0) {
      const r = barRangeToSeconds(barTimestamps, loopBars.startBarIndex, loopBars.endBarIndexExclusive, beatSec)
      if (r) {
        return {
          startSec: r.startSec,
          endSec: r.endSec,
          label: `Bars ${loopBars.startBarIndex + 1}–${loopBars.endBarIndexExclusive}`,
        }
      }
    }
    if (derived) {
      return {
        startSec: derived.startSec,
        endSec: derived.endSec,
        label: derived.label,
      }
    }
    return null
  }, [barTimestamps, beatSec, derived, loopBars])

  const loopHighlight: TabLoopBarRegion | null =
    loopBars && barTimestamps.length > 0 ? loopBars : null

  const toggleFretboardTuner = () => {
    void toggleTuner().catch(() => {})
  }

  return (
    <SessionStepScreen
      title="Slow"
      subtitle={
        isDemo
          ? DEMO_TOUR_SUBTITLE.slow
          : 'Starts at 65% speed, loops a bar-aligned region, and keeps the tab cursor synced to slowed stems.'
      }
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Next: Play"
      onNext={() => router.push(sessionHref('play'))}
    >
      {isDemo ? <DemoTourCallout>{DEMO_TOUR_CALLOUT.slow}</DemoTourCallout> : null}
      {playbackLoop ? (
        <View className="rounded-lg border border-wood-600/45 bg-cream-dark/45 px-3 py-2">
          <Text className="font-sans text-xs text-wood-900">
            Slow loop: {playbackLoop.label} ({playbackLoop.startSec.toFixed(2)}s – {playbackLoop.endSec.toFixed(2)}s)
          </Text>
          {__DEV__ && derived ? (
            <Text className="mt-1 font-mono text-[10px] text-muted-light">Source: {derived.source}</Text>
          ) : null}
        </View>
      ) : null}

      {loopBars && barTimestamps.length >= 2 ? (
        <LoopRegionControl
          barCount={barTimestamps.length}
          value={loopBars}
          onChange={setLoopBars}
        />
      ) : null}

      <SessionStemAndTab
        tabRenderPreset="light"
        initialRate={0.65}
        initialMetronomeOn={initialMetronomeOn}
        autoLoopRegion={playbackLoop}
        loopHighlight={loopHighlight}
        tabFrameClassName="mt-2 min-h-[328px] w-full px-2"
        onPlaybackTick={handlePlaybackTick}
        insertBetweenStemAndTab={
          <FretboardDiagram
            keyLabel={keyLabel}
            positionLabel={positionLabel}
            capoText={capoText}
            selectedNote={selectedNote}
            pulseKey={fretPulseKey}
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
              setNoteModalOpen(true)
            }}
          />
        }
        onNoteEvent={(evt: NoteEventMessage) => {
          setSelectedNote({ string: evt.string, fret: evt.fret, midi: evt.midi })
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
    </SessionStepScreen>
  )
}
