import { useFocusEffect } from '@react-navigation/native'
import { useRouter } from 'expo-router'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { ErrorBanner } from '@/components/ErrorBanner'
import { FretboardDiagram } from '@/components/FretboardDiagram'
import { LyricsStrip } from '@/components/LyricsStrip'
import { SessionNoteDetailModal } from '@/components/SessionNoteDetailModal'
import { SessionStemAndTab, type SessionStemAndTabHandle } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { toast } from '@/components/ToastConfig'
import { sessionHref } from '@/src/constants/sessionFlow'
import { getAppPref } from '@/src/db/client'
import { PREF_PREFER_SIMPLER_TABS, TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX } from '@/src/db/schema'
import { mapLowTranscriptionConfidenceBanner, toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import { capoSuggestion, parseKey } from '@/src/music/capoSuggestion'
import { buildNoteSelectionDetail } from '@/src/music/noteSelectionDetail'
import { barIndexForPlaybackSeconds } from '@/src/session/smartScroll'
import { useFretboardTuner } from '@/src/session/useFretboardTuner'
import type { PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSessionAnnotationsStore } from '@/src/stores/sessionAnnotationsStore'
import {
  buildFretboardShareUrl,
  readFretboardShareStateFromLocation,
  type FretboardOverlayMode,
} from '@/src/utils/fretboardShareState'
import { readSectionTabPayloads } from '@/src/utils/lessonTabs'
import type { NoteEventMessage } from '@/types/tabMessage'

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

/** Cap long songs — chips wrap; keep count reasonable for layout. */
const STUDY_BAR_CHIP_MAX = 64

export default function StudyScreen() {
  const router = useRouter()
  const sessionStemRef = useRef<SessionStemAndTabHandle>(null)
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const [tick, setTick] = useState<PlaybackTickContext>(DEFAULT_TICK)

  const handleStemPlaybackTick = useCallback((ctx: PlaybackTickContext) => {
    setTick(ctx)
  }, [])

  const section = lesson?.sections?.[lessonSectionIndex]
  const tabs = useMemo(() => readSectionTabPayloads(section), [section])
  const lyricWords = useMemo(() => toLyricWords(lesson?.lyrics_aligned), [lesson?.lyrics_aligned])
  const keyLabel = (lesson?.key ?? 'Unknown key').toString()
  const positionLabel = typeof (section as Record<string, unknown> | undefined)?.primary_position === 'string'
    ? ((section as Record<string, unknown>).primary_position as string)
    : 'Tap a note to infer position'
  const capoText = useMemo(() => capoSuggestion(keyLabel, positionLabel), [keyLabel, positionLabel])
  const degreeRootPitchClass = useMemo(() => parseKey(keyLabel)?.semitone ?? null, [keyLabel])
  const currentBar = useMemo(
    () => barIndexForPlaybackSeconds(lesson?.bar_timestamps ?? [], tick.positionSec),
    [lesson?.bar_timestamps, tick.positionSec],
  )

  const sectionKey = `${lesson?.job_id ?? 'no-job'}:${lessonSectionIndex}`
  const notesBySection = useSessionAnnotationsStore((s) => s.notesBySection)
  const setAnnotation = useSessionAnnotationsStore((s) => s.setNote)
  const sectionNotes = notesBySection[sectionKey] ?? {}

  const [variant, setVariant] = useState<TabVariant>('full')
  const [selectedNote, setSelectedNote] = useState<{ string?: number; fret?: number; midi?: number } | null>(null)
  const [fretPulseKey, setFretPulseKey] = useState(0)
  const [noteModalOpen, setNoteModalOpen] = useState(false)
  const [overlayMode, setOverlayMode] = useState<FretboardOverlayMode>('off')
  const [preferSimplerTabs, setPreferSimplerTabs] = useState(false)
  const [lowConfBannerDismissed, setLowConfBannerDismissed] = useState(false)
  const { state: tunerState, toggleTuner, startCalibration } = useFretboardTuner()

  const onTabNoteEvent = useCallback((evt: NoteEventMessage) => {
    setSelectedNote({ string: evt.string, fret: evt.fret, midi: evt.midi })
    setFretPulseKey((k) => k + 1)
    if (evt.fromScoreTap) {
      setNoteModalOpen(true)
    }
  }, [])

  const selectionDetail = useMemo(() => buildNoteSelectionDetail(keyLabel, selectedNote), [keyLabel, selectedNote])

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
    if (typeof window === 'undefined') return
    const shared = readFretboardShareStateFromLocation()
    if (!shared) return
    setOverlayMode(shared.overlay)
    if (shared.selected) {
      const note = {
        string: shared.selected.string,
        fret: shared.selected.fret,
        midi: Number.NaN,
      }
      setSelectedNote(note)
      setFretPulseKey((k) => k + 1)
    }
  }, [])

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

  const copyShareLink = () => {
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
      scalePitchClasses: null,
      rootPitchClass: degreeRootPitchClass,
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
    void writer(url).then(() => toast.success('Study fretboard link copied.'), () => toast.error('Clipboard access blocked.'))
  }

  const toggleFretboardTuner = useCallback(() => {
    void toggleTuner().catch((e) => {
      const message = e instanceof Error ? e.message : String(e)
      toast.error(message === 'MIC_PERMISSION_DENIED' ? 'Microphone permission is required for tuning.' : message)
    })
  }, [toggleTuner])

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
      <SessionStemAndTab
        ref={sessionStemRef}
        tabVariant={variant}
        onPlaybackTick={handleStemPlaybackTick}
        onNoteEvent={onTabNoteEvent}
        tabFrameClassName="mt-2 h-[328px] w-full px-2"
        insertBetweenStemAndTab={
          <>
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
              overlayMode={overlayMode}
              showOverlayControls
              onOverlayModeChange={setOverlayMode}
              showCopyShare
              onCopyShareLink={copyShareLink}
              degreeRootPitchClass={degreeRootPitchClass}
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

            <LyricsStrip words={lyricWords} playbackSec={tick.positionSec} />

            <View className="mt-2">
              <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
                Annotations (long-press bar)
              </Text>
              <View className="flex-row flex-wrap gap-2">
                {[...Array(Math.max(1, Math.min(lesson?.bar_timestamps?.length ?? 0, STUDY_BAR_CHIP_MAX))).keys()].map((bar) => (
                  <AnimatedPressable
                    key={`bar-${bar}`}
                    haptic="none"
                    onPress={() => {
                      const stamps = lesson?.bar_timestamps
                      const t = Array.isArray(stamps) && typeof stamps[bar] === 'number' ? stamps[bar]! : 0
                      void (async () => {
                        await sessionStemRef.current?.seekTransportToSeconds(t)
                        sessionStemRef.current?.scrollMasterBarIntoView(bar)
                      })()
                    }}
                    onLongPress={() => {
                      const text = `Practice note @ bar ${bar} (${new Date().toLocaleTimeString()})`
                      setAnnotation(sectionKey, bar, text)
                    }}
                    className={`rounded-full border px-2.5 py-1 ${
                      bar === currentBar ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/35 bg-cream-dark/35'
                    }`}
                    accessibilityRole="button"
                    accessibilityHint="Tap to seek; long press to save a practice note for this bar"
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
                onPress={() => void sessionStemRef.current?.seekTransportToSeconds(0)}
                className="rounded-full border border-wood-600/50 bg-cream-dark/50 px-3 py-1.5"
                accessibilityRole="button"
              >
                <Text className="font-sans text-xs text-wood-900">Seek to start</Text>
              </AnimatedPressable>
            </View>

            <Text className="mt-2 font-sans text-[11px] text-muted-brown">
              Tap the tablature to select a note — the fretboard and detail card update from the live score.
            </Text>
          </>
        }
      />

      <SessionNoteDetailModal
        detail={selectionDetail}
        visible={noteModalOpen}
        onClose={() => setNoteModalOpen(false)}
      />
    </SessionStepScreen>
  )
}
