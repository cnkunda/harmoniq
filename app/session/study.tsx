import { useFocusEffect } from '@react-navigation/native'
import { useRouter } from 'expo-router'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { ErrorBanner } from '@/components/ErrorBanner'
import { FretboardDiagram } from '@/components/FretboardDiagram'
import { allCellsForMidi, inferMidiFromNoteSelection, resolveFretCell } from '@/src/music/fretboardCell'
import { NoteDetailCard } from '@/components/NoteDetailCard'
import { ListenStemPanel } from '@/components/ListenStemPanel'
import { LyricsStrip } from '@/components/LyricsStrip'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { TabViewport } from '@/components/TabViewport'
import { sessionHref } from '@/src/constants/sessionFlow'
import { getAppPref } from '@/src/db/client'
import { PREF_PREFER_SIMPLER_TABS, TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX } from '@/src/db/schema'
import { mapLowTranscriptionConfidenceBanner, toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import { capoSuggestion } from '@/src/music/capoSuggestion'
import { suggestFingerings } from '@/src/music/fingerSuggestion'
import { buildStudyCoachLine, midiToNoteName, scaleDegreeLabel } from '@/src/music/scaleDegree'
import type { PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSessionAnnotationsStore } from '@/src/stores/sessionAnnotationsStore'
import { readSectionTabPayloads } from '@/src/utils/lessonTabs'
import type { AlphaTabSurfaceRef, NoteEventMessage } from '@/types/tabMessage'

type TabVariant = 'full' | 'skeleton' | 'alt'

const DEFAULT_TICK: PlaybackTickContext = {
  positionSec: 0,
  playing: false,
  rate: 1,
  ready: false,
}

function toLyricWords(input: unknown): Array<{ word: string; timeSec: number }> {
  if (!Array.isArray(input)) return []
  return input
    .map((raw) => {
      if (!raw || typeof raw !== 'object') return null
      const row = raw as Record<string, unknown>
      const word = typeof row.word === 'string' ? row.word.trim() : ''
      const t = row.time_seconds
      const timeSec = typeof t === 'number' ? t : typeof t === 'string' ? Number.parseFloat(t) : Number.NaN
      if (!word || !Number.isFinite(timeSec)) return null
      return { word, timeSec }
    })
    .filter((x): x is { word: string; timeSec: number } => x != null)
}

function barIndexForTime(barTimestamps: number[] | undefined, t: number): number {
  if (!barTimestamps || barTimestamps.length === 0) return 0
  for (let i = barTimestamps.length - 1; i >= 0; i -= 1) {
    if (t >= barTimestamps[i]) return i
  }
  return 0
}

export default function StudyScreen() {
  const router = useRouter()
  const tabRef = useRef<AlphaTabSurfaceRef>(null)
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const [tick, setTick] = useState<PlaybackTickContext>(DEFAULT_TICK)

  const handleStemPlaybackTick = useCallback((ctx: PlaybackTickContext) => {
    setTick(ctx)
    if (!ctx.ready) return
    tabRef.current?.syncPlaybackTimelineMs(ctx.positionSec * 1000)
  }, [])

  const section = lesson?.sections?.[lessonSectionIndex]
  const transposeSemitones =
    section && typeof section === 'object' && typeof (section as Record<string, unknown>).transposition_semitones === 'number'
      ? ((section as Record<string, unknown>).transposition_semitones as number)
      : 0
  const tabs = useMemo(() => readSectionTabPayloads(section), [section])
  const lyricWords = useMemo(() => toLyricWords(lesson?.lyrics_aligned), [lesson?.lyrics_aligned])
  const keyLabel = (lesson?.key ?? 'Unknown key').toString()
  const positionLabel = typeof (section as Record<string, unknown> | undefined)?.primary_position === 'string'
    ? ((section as Record<string, unknown>).primary_position as string)
    : 'Primary position unavailable'
  const capoText = useMemo(() => capoSuggestion(keyLabel, positionLabel), [keyLabel, positionLabel])
  const currentBar = useMemo(() => barIndexForTime(lesson?.bar_timestamps, tick.positionSec), [lesson?.bar_timestamps, tick.positionSec])

  const sectionKey = `${lesson?.job_id ?? 'no-job'}:${lessonSectionIndex}`
  const notesBySection = useSessionAnnotationsStore((s) => s.notesBySection)
  const setAnnotation = useSessionAnnotationsStore((s) => s.setNote)
  const sectionNotes = notesBySection[sectionKey] ?? {}

  const [variant, setVariant] = useState<TabVariant>('full')
  const [selectedNote, setSelectedNote] = useState<{ string?: number; fret?: number; midi?: number } | null>(null)
  const [fretPulseKey, setFretPulseKey] = useState(0)
  const [preferSimplerTabs, setPreferSimplerTabs] = useState(false)
  const [lowConfBannerDismissed, setLowConfBannerDismissed] = useState(false)

  const onTabNoteEvent = useCallback((evt: NoteEventMessage) => {
    setSelectedNote({ string: evt.string, fret: evt.fret, midi: evt.midi })
    setFretPulseKey((k) => k + 1)
  }, [])

  const selectionDetail = useMemo(() => {
    if (!selectedNote) return null
    const midi = inferMidiFromNoteSelection(selectedNote)
    const cell = resolveFretCell(selectedNote)
    if (midi == null) return null
    const noteName = midiToNoteName(midi)
    const degree = scaleDegreeLabel(keyLabel, midi)
    if (!cell) return null
    const { primary: fingerLine, alternates: alternateFingerLines } = suggestFingerings(cell, allCellsForMidi(midi))
    const coach = buildStudyCoachLine({
      noteName,
      degreeLabel: degree,
      fingerLine,
      keyLabel,
    })
    return { noteName, degree, fingerLine, alternateFingerLines, coach }
  }, [keyLabel, selectedNote])

  const transcriptionConfidence = lesson?.transcription_confidence
  const showLowTranscriptionBanner =
    typeof transcriptionConfidence === 'number' &&
    transcriptionConfidence < TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX &&
    !lowConfBannerDismissed

  useFocusEffect(
    useCallback(() => {
      void getAppPref(PREF_PREFER_SIMPLER_TABS).then((v) => setPreferSimplerTabs(v === '1'))
    }, []),
  )

  useEffect(() => {
    setLowConfBannerDismissed(false)
  }, [lesson?.job_id, lessonSectionIndex])

  useEffect(() => {
    const conf = lesson?.transcription_confidence
    const uncertain = typeof conf === 'number' && conf < TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX
    let primary: TabVariant
    if (preferSimplerTabs && uncertain) {
      if (tabs.skeleton) primary = 'skeleton'
      else if (tabs.alt) primary = 'alt'
      else primary = tabs.full ? 'full' : 'skeleton'
    } else {
      primary = tabs.full ? 'full' : tabs.skeleton ? 'skeleton' : tabs.alt ? 'alt' : 'full'
    }
    setVariant(primary)
  }, [
    lesson?.job_id,
    lesson?.transcription_confidence,
    lessonSectionIndex,
    preferSimplerTabs,
    tabs.alt,
    tabs.full,
    tabs.skeleton,
  ])

  const gp5Base64 = useMemo(() => {
    if (variant === 'full') return tabs.full ?? null
    if (variant === 'skeleton') return tabs.skeleton ?? null
    return tabs.alt ?? null
  }, [variant, tabs.alt, tabs.full, tabs.skeleton])

  const variantButton = (v: TabVariant, label: string) => {
    const disabled = v === 'full' ? !tabs.full : v === 'skeleton' ? !tabs.skeleton : !tabs.alt
    return (
      <AnimatedPressable
        haptic="light"
        onPress={() => setVariant(v)}
        disabled={disabled}
        className={`rounded-full border px-3 py-1.5 ${
          variant === v ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/45 bg-cream-dark/40'
        } ${disabled ? 'opacity-40' : ''}`}
        accessibilityRole="button"
        accessibilityState={{ selected: variant === v }}
      >
        <Text
          className={`font-sans text-xs ${variant === v ? 'text-wood-900' : 'text-muted-brown'}`}
        >
          {label}
        </Text>
      </AnimatedPressable>
    )
  }

  return (
    <SessionStepScreen
      title="Study"
      subtitle="Stems, lyrics, capo hint, and an interactive fretboard. Scroll to the tab and tap a note for fingerings and scale context."
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Next: Slow"
      onNext={() => router.push(sessionHref('slow'))}
    >
      <ListenStemPanel
        onPlaybackTick={handleStemPlaybackTick}
        onSeekSeconds={(sec) => {
          const ms = Math.max(0, sec) * 1000
          tabRef.current?.seekTo(ms)
          tabRef.current?.syncPlaybackTimelineMs(ms)
        }}
        onRateChange={(r) => tabRef.current?.setPlaybackRate(r)}
      />

      {showLowTranscriptionBanner ? (
        <ErrorBanner
          className="mt-3"
          dismissible
          {...toErrorBannerProps(mapLowTranscriptionConfidenceBanner(), {
            onRetry: () => setLowConfBannerDismissed(true),
            onDismiss: () => setLowConfBannerDismissed(true),
            onOpenSettings: () => setLowConfBannerDismissed(true),
            onContinue: () => setLowConfBannerDismissed(true),
          })}
        />
      ) : null}

      <FretboardDiagram
        keyLabel={keyLabel}
        positionLabel={positionLabel}
        capoText={capoText}
        selectedNote={selectedNote}
        pulseKey={fretPulseKey}
      />

      {selectionDetail ? (
        <View className="mt-3 w-full max-w-md self-center px-1">
          <NoteDetailCard
            noteName={selectionDetail.noteName}
            scaleDegree={selectionDetail.degree}
            fingerLine={selectionDetail.fingerLine}
            alternateFingerLines={selectionDetail.alternateFingerLines}
            coachText={selectionDetail.coach}
            onDismiss={() => setSelectedNote(null)}
          />
        </View>
      ) : null}

      <LyricsStrip words={lyricWords} playbackSec={tick.positionSec} />

      <View className="mt-2">
        <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
          Annotations (long-press bar)
        </Text>
        <View className="flex-row flex-wrap gap-2">
          {[...Array(Math.max(1, Math.min(lesson?.bar_timestamps?.length ?? 0, 16))).keys()].map((bar) => (
            <AnimatedPressable
              key={`bar-${bar}`}
              haptic="none"
              onLongPress={() => {
                const text = `Practice note @ bar ${bar} (${new Date().toLocaleTimeString()})`
                setAnnotation(sectionKey, bar, text)
              }}
              className={`rounded-full border px-2.5 py-1 ${
                bar === currentBar ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/35 bg-cream-dark/35'
              }`}
              accessibilityRole="button"
              accessibilityHint="Long press to save a practice note for this bar"
            >
              <Text className={`font-mono text-[10px] ${bar === currentBar ? 'text-wood-900' : 'text-muted-brown'}`}>
                bar {bar}
              </Text>
            </AnimatedPressable>
          ))}
        </View>
        <Text className="mt-1 font-sans text-[11px] text-muted-brown">
          Saved notes in this section: {Object.keys(sectionNotes).length}
        </Text>
      </View>

      <View className="mt-3 flex-row flex-wrap items-center gap-2">
        {variantButton('full', 'Full tab')}
        {variantButton('skeleton', 'Skeleton')}
        {tabs.alt ? variantButton('alt', 'Alt position') : null}
        <AnimatedPressable
          haptic="light"
          onPress={() => tabRef.current?.seekTo(0)}
          className="rounded-full border border-wood-600/50 bg-cream-dark/50 px-3 py-1.5"
          accessibilityRole="button"
        >
          <Text className="font-sans text-xs text-wood-900">Seek to start</Text>
        </AnimatedPressable>
      </View>

      <Text className="mt-2 font-sans text-[11px] text-muted-brown">
        Tap the tablature to select a note — the fretboard and detail card update from the live score.
      </Text>
      <View className="mt-2 h-[320px] w-full">
        <TabViewport
          ref={tabRef}
          gp5Base64={gp5Base64}
          transposeSemitones={transposeSemitones}
          onNoteEvent={onTabNoteEvent}
          style={{ flex: 1, height: '100%', width: '100%' }}
        />
      </View>
    </SessionStepScreen>
  )
}
