import Slider from '@react-native-community/slider'
import { useRouter } from 'expo-router'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Pressable, Text, useWindowDimensions, View } from 'react-native'

import { FretboardDiagram } from '@/components/FretboardDiagram'
import { PitchIndicator } from '@/components/PitchIndicator'
import { SessionNoteDetailModal } from '@/components/SessionNoteDetailModal'
import { SessionStemAndTab, type SessionStemAndTabHandle } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { WarmupTimerRing } from '@/components/WarmupTimerRing'
import { speak } from '@/src/audio/voiceCoach'
import { capoSuggestion } from '@/src/music/capoSuggestion'
import { buildNoteSelectionDetail } from '@/src/music/noteSelectionDetail'
import { navigateToPracticePlanSlot } from '@/src/session/practicePlanNavigation'
import { useFretboardTuner } from '@/src/session/useFretboardTuner'
import { useLessonStore } from '@/src/stores/lessonStore'
import { usePlanStore } from '@/src/stores/planStore'
import { useVoiceCoachPrefsStore } from '@/src/stores/voiceCoachPrefsStore'
import type { NoteEventMessage } from '@/types/tabMessage'

const WIDE_BREAKPOINT = 900

function formatClock(totalSec: number): string {
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatTechniqueTag(tag: string): string {
  return tag.replace(/_/g, ' ')
}

function Pill({ children, emphasis }: { children: string; emphasis?: boolean }) {
  return (
    <View
      className={`rounded-full border px-2.5 py-1 ${
        emphasis ? 'border-amber-accent/45 bg-amber-accent/20' : 'border-wood-600/25 bg-cream-dark/50'
      }`}
    >
      <Text className={`font-sans text-xs ${emphasis ? 'font-sans-medium text-wood-900' : 'text-wood-800'}`}>
        {children}
      </Text>
    </View>
  )
}

export default function WarmupScreen() {
  const router = useRouter()
  const { width } = useWindowDimensions()
  const twoColumn = width >= WIDE_BREAKPOINT
  const tabRef = useRef<SessionStemAndTabHandle>(null)
  const plan = usePlanStore((s) => s.currentPlan)
  const idx = usePlanStore((s) => s.currentSlotIndex)
  const lesson = useLessonStore((s) => s.lesson)
  const saveLesson = useLessonStore((s) => s.saveLesson)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)

  const slot = plan?.slots[idx]
  const wp = slot?.warmup_plan
  const exercises = wp?.exercises ?? []

  const [exerciseIndex, setExerciseIndex] = useState(0)
  const [secLeft, setSecLeft] = useState(exercises[0]?.duration_seconds ?? 0)
  const [completed, setCompleted] = useState(false)
  const [warmupStarted, setWarmupStarted] = useState(false)
  const [tempoMul, setTempoMul] = useState(1)
  const [selectedNote, setSelectedNote] = useState<{ string?: number; fret?: number; midi?: number } | null>(null)
  const [fretPulseKey, setFretPulseKey] = useState(0)
  const [noteModalOpen, setNoteModalOpen] = useState(false)
  const [pitchDemoFlashToken, setPitchDemoFlashToken] = useState(0)

  const keyLabel = (lesson?.key ?? 'E minor').toString()
  const positionLabel = 'Tap the tab or fretboard to explore'
  const capoText = useMemo(() => capoSuggestion(keyLabel, positionLabel), [keyLabel, positionLabel])
  const selectionDetail = useMemo(() => buildNoteSelectionDetail(keyLabel, selectedNote), [keyLabel, selectedNote])

  const { state: tunerState, toggleTuner, startCalibration } = useFretboardTuner()

  useEffect(() => {
    setPitchDemoFlashToken(1)
  }, [])

  useEffect(() => {
    setSelectedNote(null)
    setNoteModalOpen(false)
  }, [exerciseIndex])

  useEffect(() => {
    if (!exercises.length) {
      router.replace('/session/slow')
    }
  }, [exercises.length, router])

  const exerciseSignature = exercises.map((e) => `${e.name}:${e.duration_seconds}`).join('|')

  /** Reset stepping when this plan slot’s warm-up payload changes. */
  useEffect(() => {
    if (!exercises.length) return
    setExerciseIndex(0)
    setSecLeft(exercises[0].duration_seconds)
    setCompleted(false)
    setWarmupStarted(false)
  }, [idx, slot?.title, exerciseSignature])

  useEffect(() => {
    if (!warmupStarted || !exercises.length || completed) return
    const id = setInterval(() => {
      setSecLeft((s) => (s <= 1 ? 0 : s - 1))
    }, 1000)
    return () => clearInterval(id)
  }, [warmupStarted, completed, exercises.length, exerciseIndex])

  useEffect(() => {
    if (!warmupStarted) return
    if (secLeft !== 0 || !exercises.length || completed) return
    const isLast = exerciseIndex >= exercises.length - 1
    if (isLast) {
      setCompleted(true)
      return
    }
    const next = exerciseIndex + 1
    setExerciseIndex(next)
    setSecLeft(exercises[next].duration_seconds)
  }, [secLeft, exerciseIndex, exercises, completed, warmupStarted])

  const ex = exercises[exerciseIndex]

  useEffect(() => {
    if (!warmupStarted || !ex?.description) return
    if (!useVoiceCoachPrefsStore.getState().enabled) return
    speak(ex.description.trim())
  }, [warmupStarted, exerciseIndex, ex?.description])

  useEffect(() => {
    tabRef.current?.getTabSurface()?.setPlaybackRate(tempoMul)
  }, [tempoMul, exerciseIndex, ex?.tab_snippet_gp5_base64])

  const totalRemaining = useMemo(() => {
    if (!exercises.length) return 0
    let sum = secLeft
    for (let i = exerciseIndex + 1; i < exercises.length; i++) {
      sum += exercises[i].duration_seconds
    }
    return sum
  }, [exercises, exerciseIndex, secLeft])

  const totalWarmupSec = useMemo(() => {
    const fromPlan = wp?.total_duration_seconds
    if (typeof fromPlan === 'number' && fromPlan > 0) return fromPlan
    return exercises.reduce((acc, e) => acc + e.duration_seconds, 0)
  }, [wp?.total_duration_seconds, exercises])

  const displayBpm = ex ? Math.round(ex.bpm * tempoMul) : 0
  const targetBpm = ex ? Math.round(ex.bpm) : 0

  const { fretGuideCellsForUi, fretGuideFooterHint } = useMemo(() => {
    const g = ex?.fretboard_guide
    if (!g?.cells?.length) {
      return { fretGuideCellsForUi: undefined, fretGuideFooterHint: undefined }
    }
    return {
      fretGuideCellsForUi: g.cells,
      fretGuideFooterHint: g.caption?.trim() || undefined,
    }
  }, [ex?.fretboard_guide])

  const goNextDrill = () => {
    void navigateToPracticePlanSlot(router, { saveLesson, setLessonSectionIndex }, idx + 1)
  }

  const stopExercise = () => {
    if (!warmupStarted || completed) return
    setWarmupStarted(false)
    tabRef.current?.getTabSurface()?.setStemPlaybackActive(false)
  }

  const skipExercise = () => {
    if (completed) return
    const isLast = exerciseIndex >= exercises.length - 1
    if (isLast) {
      setCompleted(true)
      setSecLeft(0)
      return
    }
    const next = exerciseIndex + 1
    setExerciseIndex(next)
    setSecLeft(exercises[next].duration_seconds)
  }

  const goPrevExercise = () => {
    if (exerciseIndex <= 0) {
      router.back()
      return
    }
    const prev = exerciseIndex - 1
    setExerciseIndex(prev)
    setSecLeft(exercises[prev].duration_seconds)
    setCompleted(false)
  }

  const toggleFretboardTuner = () => {
    void toggleTuner().catch(() => {})
  }

  if (!exercises.length) {
    return null
  }

  const gp5 = ex?.tab_snippet_gp5_base64?.trim() || null
  const nextEx = !completed && exerciseIndex < exercises.length - 1 ? exercises[exerciseIndex + 1] : null

  const colClass = twoColumn ? 'flex-row items-start gap-8' : 'flex-col'
  const leftColClass = twoColumn ? 'flex-1' : 'w-full'
  const rightColClass = twoColumn ? 'flex-1' : 'mt-6 w-full'

  return (
    <SessionStepScreen
      title="Session warm-up"
      subtitle="Short moves before the rest of your plan."
      hideTitle
      showBack
      backLabel={exerciseIndex > 0 ? 'Previous exercise' : 'Back'}
      onBack={goPrevExercise}
      showNext={completed}
      nextLabel="Next drill"
      onNext={goNextDrill}
      footerContainerClassName="flex-row gap-3 border-t border-wood-600/20 bg-ivory px-6 pb-8 pt-4"
      backButtonClassName="flex-1 rounded-2xl border border-wood-600/45 bg-cream py-3.5"
      nextButtonClassName="flex-1 rounded-2xl border border-amber-accent/55 bg-amber-accent/35 py-3.5"
    >
      <View className={`mt-1 ${colClass}`}>
        <View className={leftColClass}>
          <Text className="font-sans-medium text-xs uppercase tracking-wider text-amber-accent">SESSION WARM-UP</Text>

          <View className="mt-4 items-center">
            <WarmupTimerRing
              totalRemainingSec={totalRemaining}
              totalWarmupSec={totalWarmupSec}
              completed={completed}
              timeLabel={formatClock(totalRemaining)}
            />
          </View>

          <View className="mt-5 flex-row items-center justify-center gap-2">
            {exercises.map((_, i) => {
              const done = completed || i < exerciseIndex
              const active = !completed && i === exerciseIndex
              return (
                <View
                  key={`ex-seg-${i}`}
                  className={
                    active
                      ? 'h-2 w-10 rounded-full bg-amber-accent'
                      : done
                        ? 'h-2 w-2 rounded-full bg-amber-accent/55'
                        : 'h-2 w-2 rounded-full bg-wood-600/35'
                  }
                />
              )
            })}
          </View>

          {!completed && !warmupStarted ? (
            <Pressable
              onPress={() => setWarmupStarted(true)}
              className="mt-6 w-full rounded-2xl bg-amber-accent/90 py-3.5"
              accessibilityRole="button"
              accessibilityLabel="Start warm-up exercise timer"
            >
              <Text className="text-center font-sans-medium text-wood-900">Start exercise</Text>
            </Pressable>
          ) : null}
          {!completed && warmupStarted ? (
            <Pressable
              onPress={stopExercise}
              className="mt-6 w-full rounded-2xl border-2 border-wood-600/45 bg-cream-dark/50 py-3.5"
              accessibilityRole="button"
              accessibilityLabel="Stop warm-up exercise timer"
            >
              <Text className="text-center font-sans-medium text-wood-900">Stop exercise</Text>
            </Pressable>
          ) : null}
        </View>

        <View className={rightColClass}>
          <View className="rounded-2xl border border-wood-600/20 bg-white px-4 pb-4 pt-3.5 shadow-sm">
            <View className="flex-row items-center justify-between">
              <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
                Exercise {completed ? exercises.length : exerciseIndex + 1} of {exercises.length}
              </Text>
              {!completed ? (
                <View className="flex-row items-center gap-1.5 rounded-full border border-amber-accent/40 bg-amber-accent/10 px-2.5 py-1">
                  <View className="h-1.5 w-1.5 rounded-full bg-amber-accent" />
                  <Text className="font-sans-medium text-xs text-wood-800">
                    {warmupStarted ? 'Active' : 'Ready'}
                  </Text>
                </View>
              ) : (
                <Text className="font-sans-medium text-xs text-muted-brown">Done</Text>
              )}
            </View>

            <Text className="mt-3 font-serif text-2xl text-wood-900">{ex?.name ?? '—'}</Text>

            <View className="mt-3 flex-row flex-wrap gap-2">
              <Pill emphasis>{`${formatClock(ex?.duration_seconds ?? 0)} duration`}</Pill>
              <Pill emphasis>{`${targetBpm} BPM target`}</Pill>
              <Pill>{ex ? formatTechniqueTag(ex.technique_tag) : '—'}</Pill>
            </View>

            <Text className="mt-3 font-sans text-sm leading-relaxed text-wood-800">{ex?.description}</Text>

            <View className="mt-4">
              <View className="mb-1.5 flex-row items-center justify-between">
                <Text className="font-sans-medium text-xs text-wood-800">Playback tempo</Text>
                <Text className="font-sans-medium text-xs text-amber-accent">{displayBpm} BPM</Text>
              </View>
              <Slider
                minimumValue={0.55}
                maximumValue={1.25}
                step={0.05}
                value={tempoMul}
                onValueChange={setTempoMul}
                minimumTrackTintColor="#c9a227"
                maximumTrackTintColor="#8b7355"
                thumbTintColor="#5c4033"
              />
              <Text className="mt-1 font-sans text-xs text-muted-brown">
                Adjusts preview only — plan stays the same.
              </Text>
            </View>

            {nextEx ? (
              <View className="mt-5 rounded-xl border border-wood-600/15 bg-cream-dark/35 px-3 py-2.5">
                <Text className="font-sans-medium text-[10px] uppercase tracking-wide text-muted-brown">Up next</Text>
                <View className="mt-1 flex-row items-center justify-between gap-2">
                  <Text className="flex-1 font-sans text-sm text-wood-900" numberOfLines={2}>
                    {nextEx.name}
                  </Text>
                  <Text className="font-sans-medium text-sm text-muted-brown">
                    {formatClock(nextEx.duration_seconds)}
                  </Text>
                </View>
              </View>
            ) : null}

            {!completed ? (
              <View className="mt-5 flex-row flex-wrap gap-2">
                <Pressable
                  onPress={skipExercise}
                  className="min-w-[140px] flex-1 rounded-xl border border-wood-600/40 bg-ivory py-3"
                  accessibilityRole="button"
                  accessibilityLabel="Skip to next warm-up exercise"
                >
                  <Text className="text-center font-sans-medium text-sm text-wood-900">Skip exercise</Text>
                </Pressable>
                <Pressable
                  onPress={goNextDrill}
                  className="min-w-[140px] flex-1 rounded-xl border border-wood-600/40 bg-ivory py-3"
                  accessibilityRole="button"
                  accessibilityLabel="Skip entire warm-up"
                >
                  <Text className="text-center font-sans-medium text-sm text-wood-900">Skip warm-up</Text>
                </Pressable>
              </View>
            ) : null}
          </View>
        </View>
      </View>

      <View className="mt-8 border-t border-wood-600/15 pt-6">
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
          fretGuideCells={fretGuideCellsForUi}
          fretGuideFooterHint={fretGuideFooterHint}
          pitchLadderDefaultExpanded
          pitchLadderSlot={
            <PitchIndicator
              note="E"
              cents={12}
              isActive={false}
              targetMidi={64}
              nextTargetMidi={67}
              windowResult="hit"
              windowFlashToken={pitchDemoFlashToken}
            />
          }
        />
      </View>

      {gp5 ? (
        <View className="mt-2">
          <SessionStemAndTab
            ref={tabRef}
            showStemPanel={false}
            gp5Base64Override={gp5}
            initialMetronomeOn={false}
            tabFrameClassName="mt-2 h-[280px] w-full px-1"
            onTabReady={() => tabRef.current?.getTabSurface()?.setPlaybackRate(tempoMul)}
            onNoteEvent={(evt: NoteEventMessage) => {
              setSelectedNote({ string: evt.string, fret: evt.fret, midi: evt.midi })
              setFretPulseKey((k) => k + 1)
              if (evt.fromScoreTap) {
                setNoteModalOpen(true)
              }
            }}
          />
        </View>
      ) : null}

      {completed ? (
        <Text className="mt-4 font-sans text-sm text-muted-brown">
          Nice — you&apos;re warmed up. Tap Next drill to continue your plan.
        </Text>
      ) : null}

      <SessionNoteDetailModal detail={selectionDetail} visible={noteModalOpen} onClose={() => setNoteModalOpen(false)} />
    </SessionStepScreen>
  )
}
