import { useFocusEffect } from '@react-navigation/native'
import { Audio } from 'expo-av'
import { useRouter } from 'expo-router'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { ChordCorrectionDropdown } from '@/components/ChordCorrectionDropdown'
import { CorrectionHistoryPanel } from '@/components/CorrectionHistoryPanel'
import { DemoTourCallout } from '@/components/DemoTourCallout'
import { ErrorBanner } from '@/components/ErrorBanner'
import { FretboardDiagram } from '@/components/FretboardDiagram'
import { NoteCorrectionSheet } from '@/components/NoteCorrectionSheet'
import { SessionNoteDetailModal } from '@/components/SessionNoteDetailModal'
import { SessionStemAndTab, type SessionStemAndTabHandle } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { toast } from '@/components/ToastConfig'
import {
  correctChord,
  correctSoloNote,
  fetchTheoryAnnotation,
  getCorrectionHistory,
  revertCorrection,
  type CorrectionHistory,
  type CorrectionRecord,
} from '@/src/api/analyze'
import { sessionHref } from '@/src/constants/sessionFlow'
import { getAppPref } from '@/src/db/client'
import { PREF_PREFER_FULL_TABS, PREF_PREFER_SIMPLER_TABS_LEGACY, TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX } from '@/src/db/schema'
import { DEMO_TOUR_CALLOUT, DEMO_TOUR_SUBTITLE } from '@/src/demo/demoSessionTourCopy'
import { useIsDemoLesson } from '@/src/demo/useIsDemoLesson'
import { mapLowTranscriptionConfidenceBanner, toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import { capoSuggestion, parseKey } from '@/src/music/capoSuggestion'
import { getChordFunction } from '@/src/music/chordFunction'
import { MusicProvider, useMusicActions } from '@/src/context/MusicContext'
import { formatChordDisplay } from '@/src/music/chordVoicing'
import { buildNoteSelectionDetail } from '@/src/music/noteSelectionDetail'
import { barIndexForPlaybackSeconds } from '@/src/session/smartScroll'
import { useFretboardTuner } from '@/src/session/useFretboardTuner'
import type { PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import { useStepCoachNarration } from '@/src/session/useStepCoachNarration'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSessionAnnotationsStore } from '@/src/stores/sessionAnnotationsStore'
import {
  buildFretboardShareUrl,
  readFretboardShareStateFromLocation,
  type FretboardOverlayMode,
} from '@/src/utils/fretboardShareState'
import { pickTabVariant, readSectionTabPayloads } from '@/src/utils/lessonTabs'
import type { NoteEventMessage } from '@/types/tabMessage'

// Transcription types (matching backend schemas)
interface BeatGrid {
  bpm: number
  pulse_bpm: number
  beats: number[]
  downbeats: number[]
  time_signature: { numerator: number; denominator: number }
  tick_value: number
}

interface ChordEvent {
  timestamp: number
  chord: string
  confidence: number
}

interface ChordTimeline {
  events: ChordEvent[]
}

interface SoloNote {
  start_time: number
  duration: number
  pitch: number
  velocity?: number
}

interface SoloNotes {
  notes: SoloNote[]
}

type TabVariant = 'full' | 'skeleton' | 'alt'

interface TranscriptionValidationMetadata {
  validation?: {
    is_playable: boolean;
    flag_reason?: string | null;
    model_version: string;
    confidence: number;
  };
}

interface LessonSectionWithMusic extends Record<string, unknown> {
  chord_timeline?: ChordTimeline;
  solo_notes?: SoloNotes;
  confidence?: number | null;
  transcription_metadata?: TranscriptionValidationMetadata | null;
}



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
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const section = lesson?.sections?.[lessonSectionIndex] as LessonSectionWithMusic | undefined

  // Extract timeline data for MusicProvider (prefer section-level, fall back to lesson-level)
  const chordEvents = section?.chord_timeline?.events ?? lesson?.chord_timeline?.events ?? null
  const soloNotesArr = section?.solo_notes?.notes ?? lesson?.solo_notes?.notes ?? null
  const barTimestamps = lesson?.bar_timestamps ?? null

  return (
    <MusicProvider
      chordEvents={chordEvents}
      soloNotes={soloNotesArr}
      barTimestamps={barTimestamps}
    >
      <StudyScreenInner />
    </MusicProvider>
  )
}

function StudyScreenInner() {
  useStepCoachNarration()
  const isDemo = useIsDemoLesson()
  const router = useRouter()
  const musicActions = useMusicActions()
  const sessionStemRef = useRef<SessionStemAndTabHandle>(null)
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const [tick, setTick] = useState<PlaybackTickContext>(DEFAULT_TICK)
  const [showTranscriptionWarningModal, setShowTranscriptionWarningModal] = useState(false);
  const [stemRoutingOverride, setStemRoutingOverride] = useState<string | null>(null);
  const [theoryAnnotation, setTheoryAnnotation] = useState<{ chordName: string; chordFunction: string; romanNumeral: string; rationale: string } | null>(null);

  // Intelligent fretboard display mode (auto-detect or manual override)
  const [fretboardMode, setFretboardMode] = useState<'auto' | 'chords' | 'solo' | 'both'>('auto')
  const [voicingMode, setVoicingMode] = useState<'full' | 'compact'>('compact')

  // Correction mode state
  const [correctionMode, setCorrectionMode] = useState(false)
  const [correctionHistory, setCorrectionHistory] = useState<CorrectionHistory | null>(null)
  const [chordCorrectingBeat, setChordCorrectingBeat] = useState<number | null>(null)
  const [noteCorrectingIndex, setNoteCorrectingIndex] = useState<number | null>(null)
  const [noteCorrectingOriginal, setNoteCorrectingOriginal] = useState<{ pitch: number; start_time: number; duration: number; velocity: number } | null>(null)

  // Orient clip states (moved from separate orient.tsx screen)
  const [orientClipUrl, setOrientClipUrl] = useState<string | null>(null)
  const [orientAnnotation, setOrientAnnotation] = useState<string | null>(null)
  const [orientIsLoading, setOrientIsLoading] = useState(false)
  const [orientError, setOrientError] = useState<string | null>(null)
  const [orientIsPlaying, setOrientIsPlaying] = useState(false)
  const orientSoundRef = useRef<any>(null)
  const orientSoundInstanceId = useRef(`study-orient-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`)

  // Show transcription warning modal when section confidence is low
  useEffect(() => {
    const section = lesson?.sections?.[lessonSectionIndex] as LessonSectionWithMusic | undefined
    if (!section) return

    const sectionConfidence = typeof section.confidence === 'number' ? section.confidence : 1.0
    const transcriptionConfidence = typeof lesson?.transcription_confidence === 'number' ? lesson.transcription_confidence : 1.0
    const isLowConfidence = sectionConfidence < TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX ||
      transcriptionConfidence < TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX

    // Check transcription metadata for validation flags
    const validationMetadata = section.transcription_metadata?.validation
    const hasValidationFlag = validationMetadata?.flag_reason != null

    if (isLowConfidence || hasValidationFlag) {
      setShowTranscriptionWarningModal(true)
    } else {
      setShowTranscriptionWarningModal(false)
    }
  }, [lesson?.sections, lessonSectionIndex, lesson?.transcription_confidence])

  // Fetch orient clip when lesson changes
  useEffect(() => {
    const fetchOrientClip = async () => {
      if (!lesson?.job_id) return

      setOrientIsLoading(true)
      setOrientError(null)

      try {
        const response = await fetch(`${process.env.EXPO_PUBLIC_API_URL}/session/orient-clip`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            job_id: lesson.job_id,
            style_label: lesson.style_label,
            technique: null,
            key: lesson.key,
            bpm: lesson.tempo,
          }),
        })

        if (!response.ok) {
          throw new Error(`Failed to fetch orient clip: ${response.statusText}`)
        }

        const data = await response.json()
        setOrientClipUrl(data.wav_path)
        setOrientAnnotation(data.annotation)
      } catch (e) {
        console.error('Failed to fetch orient clip:', e)
        setOrientError(e instanceof Error ? e.message : 'Failed to load orient clip')
      } finally {
        setOrientIsLoading(false)
      }
    }

    void fetchOrientClip()
  }, [lesson?.job_id, lesson?.style_label, lesson?.key, lesson?.tempo])

  // Cleanup orient sound on unmount
  useEffect(() => {
    return () => {
      if (orientSoundRef.current) {
        orientSoundRef.current.unloadAsync()
      }
    }
  }, [])

  const handleStemPlaybackTick = useCallback((ctx: PlaybackTickContext) => {
    setTick(ctx)
    // Drive shared music context state from playback tick
    musicActions.setPosition(ctx.positionSec * 1000)
    musicActions.setPlaying(ctx.playing)
  }, [musicActions])

  // Seed initial chord/notes on mount so fretboard isn't blank before playback starts
  useEffect(() => {
    musicActions.setPosition(0)
    // Only run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const section = lesson?.sections?.[lessonSectionIndex] as LessonSectionWithMusic | undefined

  // Update theory annotation based on current chord during playback
  useEffect(() => {
    const updateTheoryAnnotation = async () => {
      // Check both section level and lesson level for chord_timeline
      const chordEvents = section?.chord_timeline?.events ?? lesson?.chord_timeline?.events
      if (!chordEvents || !lesson?.key) return;

      // Find current chord based on playback position
      const currentChordEvent = chordEvents
        .slice()
        .reverse()
        .find((event: ChordEvent) => event.timestamp <= tick.positionSec);

      if (!currentChordEvent || currentChordEvent.chord === 'N') {
        setTheoryAnnotation(null);
        return;
      }

      // Get chord function
      const chordFunction = getChordFunction(lesson.key, currentChordEvent.chord);
      if (!chordFunction) {
        setTheoryAnnotation(null);
        return;
      }

      // Fetch theory rationale from backend
      try {
        const response = await fetchTheoryAnnotation({
          key: lesson.key,
          chord: currentChordEvent.chord,
          chord_function: chordFunction.roman,
        });
        setTheoryAnnotation({
          chordName: currentChordEvent.chord,
          chordFunction: chordFunction.label,
          romanNumeral: chordFunction.roman,
          rationale: response.rationale,
        });
      } catch (e) {
        console.error('Failed to fetch theory annotation:', e);
        // Set fallback annotation without rationale
        setTheoryAnnotation({
          chordName: currentChordEvent.chord,
          chordFunction: chordFunction.label,
          romanNumeral: chordFunction.roman,
          rationale: 'This chord functions as ' + chordFunction.label.toLowerCase() + ' in the key.',
        });
      }
    };

    // Debounce the annotation fetch to avoid excessive API calls
    const timeoutId = setTimeout(() => {
      void updateTheoryAnnotation();
    }, 500);

    return () => clearTimeout(timeoutId);
  }, [tick.positionSec, section?.chord_timeline, lesson?.chord_timeline, lesson?.key]);

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
  const [preferFullTabs, setPreferFullTabs] = useState(false)
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
      void Promise.all([
        getAppPref(PREF_PREFER_FULL_TABS),
        getAppPref(PREF_PREFER_SIMPLER_TABS_LEGACY),
      ]).then(([v, legacy]) => {
        // Legacy "0" (always full) maps onto the new default-off toggle.
        setPreferFullTabs(v === '1' || (v == null && legacy === '0'))
      })
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
    setVariant(pickTabVariant(lesson?.transcription_confidence, tabs, preferFullTabs))
  }, [
    lesson?.job_id,
    lesson?.transcription_confidence,
    lessonSectionIndex,
    preferFullTabs,
    tabs.alt,
    tabs.full,
    tabs.skeleton,
  ])

  // --- Correction handlers ---
  const jobId = lesson?.job_id?.trim() || null

  const loadCorrectionHistory = useCallback(async () => {
    if (!jobId) return
    try {
      const history = await getCorrectionHistory(jobId)
      setCorrectionHistory(history)
    } catch {
      // Silently ignore — corrections may not exist yet
    }
  }, [jobId])

  const handleChordCorrection = useCallback(async (beatIndex: number, chord: string) => {
    if (!jobId) return
    try {
      await correctChord(jobId, beatIndex, { chord, reason: 'User correction' })
      toast.success(`Chord corrected to ${chord}`)
      setChordCorrectingBeat(null)
      await loadCorrectionHistory()
    } catch (e) {
      toast.error(`Correction failed: ${e instanceof Error ? e.message : 'unknown error'}`)
    }
  }, [jobId, loadCorrectionHistory])

  const handleNoteCorrection = useCallback(async (noteIndex: number, corrections: {
    pitch?: number; start_time?: number; duration?: number; velocity?: number; string?: number; fret?: number
  }) => {
    if (!jobId) return
    try {
      await correctSoloNote(jobId, noteIndex, { ...corrections, reason: 'User correction' })
      toast.success('Note corrected')
      setNoteCorrectingIndex(null)
      setNoteCorrectingOriginal(null)
      await loadCorrectionHistory()
    } catch (e) {
      toast.error(`Correction failed: ${e instanceof Error ? e.message : 'unknown error'}`)
    }
  }, [jobId, loadCorrectionHistory])

  const handleRevertCorrection = useCallback(async (correctionIndex: number) => {
    if (!jobId) return
    try {
      await revertCorrection(jobId, correctionIndex)
      toast.success('Correction reverted')
      await loadCorrectionHistory()
    } catch (e) {
      toast.error(`Revert failed: ${e instanceof Error ? e.message : 'unknown error'}`)
    }
  }, [jobId, loadCorrectionHistory])

  // Load correction history when correction mode is toggled on
  useEffect(() => {
    if (correctionMode) {
      void loadCorrectionHistory()
    }
  }, [correctionMode, loadCorrectionHistory])


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

  // Orient clip playback handler
  const handleToggleOrientPlayback = useCallback(async () => {
    if (!orientClipUrl) return

    try {
      if (orientIsPlaying) {
        const sound = orientSoundRef.current
        if (sound) {
          await sound.pauseAsync()
          setOrientIsPlaying(false)
        }
      } else {
        if (orientSoundRef.current) {
          await orientSoundRef.current.playAsync()
          setOrientIsPlaying(true)
        } else {
          const { sound } = await (Audio as any).Sound.createAsync(
            { uri: orientClipUrl },
            { shouldPlay: true }
          )
          orientSoundRef.current = sound
          setOrientIsPlaying(true)
          sound.setOnPlaybackStatusUpdate((status: any) => {
            if (status.isLoaded && status.didJustFinish) {
              setOrientIsPlaying(false)
            }
          })
        }
      }
    } catch (e) {
      console.error('Orient playback error:', e)
      toast.error('Could not play orient clip')
    }
  }, [orientClipUrl, orientIsPlaying])

  return (
    <SessionStepScreen
      title="Study"
      subtitle={
        isDemo
          ? DEMO_TOUR_SUBTITLE.study
          : 'Stems, lyrics, capo hint, and an interactive fretboard. Scroll to the tab and tap a note for fingerings and scale context.'
      }
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Next: Slow"
      onNext={() => router.push(sessionHref('slow'))}
    >
      {isDemo ? <DemoTourCallout>{DEMO_TOUR_CALLOUT.study}</DemoTourCallout> : null}

      {showTranscriptionWarningModal && (
        <View className="mx-4 rounded-lg border border-amber-accent/50 bg-amber-accent/10 p-4">
          <Text className="mb-2 font-sans-medium text-amber-accent">
            Transcription Uncertainty
          </Text>
          <Text className="mb-3 font-sans text-sm text-wood-900">
            We're {Math.round((lesson?.transcription_confidence ?? 1.0) * 100)}% sure about this transcription.
            Want to slow it down to 50% speed and verify?
          </Text>

          {/* Stem routing override UI */}
          {lesson?.stems && Object.keys(lesson.stems).length > 1 && (
            <View className="mb-3">
              <Text className="mb-2 font-sans-medium text-xs text-wood-900">
                Re-route stem source:
              </Text>
              <View className="flex-row flex-wrap gap-2">
                {Object.keys(lesson.stems).map((stemName) => (
                  <AnimatedPressable
                    key={stemName}
                    className={`rounded-md border px-3 py-1.5 ${stemRoutingOverride === stemName
                      ? 'border-amber-accent bg-amber-accent/20'
                      : 'border-wood-600/30 bg-wood-800/50'
                      }`}
                    onPress={() => {
                      setStemRoutingOverride(stemName)
                      // Trigger re-render with new stem
                      console.log('Stem routing override:', stemName)
                    }}
                  >
                    <Text
                      className={`font-sans-medium text-xs ${stemRoutingOverride === stemName ? 'text-amber-accent' : 'text-cream'
                        }`}
                    >
                      {stemName}
                    </Text>
                  </AnimatedPressable>
                ))}
              </View>
            </View>
          )}

          <View className="flex-row gap-2">
            <AnimatedPressable
              className="flex-1 rounded-md border border-amber-accent/30 bg-amber-accent/20 px-3 py-2"
              onPress={() => {
                setShowTranscriptionWarningModal(false)
                // Slow down playback to 50%
                const tabSurface = sessionStemRef.current?.getTabSurface()
                tabSurface?.setPlaybackRate(0.5)
              }}
            >
              <Text className="text-center font-sans-medium text-sm text-wood-900">
                Slow Down & Verify
              </Text>
            </AnimatedPressable>
            <AnimatedPressable
              className="flex-1 rounded-md border border-wood-600/30 bg-wood-800/50 px-3 py-2"
              onPress={() => {
                setShowTranscriptionWarningModal(false)
              }}
            >
              <Text className="text-center font-sans-medium text-sm text-cream">
                Continue Anyway
              </Text>
            </AnimatedPressable>
          </View>
        </View>
      )}

      <SessionStemAndTab
        ref={sessionStemRef}
        tabRenderPreset="light"
        tabVariant={variant}
        lyricWords={lyricWords}
        onPlaybackTick={handleStemPlaybackTick}
        onNoteEvent={onTabNoteEvent}
        onTabVariantChange={setVariant}
        tabFrameClassName="mt-2 min-h-[328px] w-full px-2"
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

            {/* Fretboard Mode Controls */}

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
              showOrientControl={!orientError}
              orientClipUrl={orientClipUrl}
              orientAnnotation={orientAnnotation}
              orientIsPlaying={orientIsPlaying}
              onToggleOrientPlayback={handleToggleOrientPlayback}
              fretboardMode={fretboardMode}
              onFretboardModeChange={setFretboardMode}
              voicingMode={voicingMode}
              onVoicingModeChange={setVoicingMode}
              onSelectNote={(note) => {
                setSelectedNote(note)
                setFretPulseKey((k) => k + 1)
                if (correctionMode && note?.midi != null) {
                  // In correction mode, open note correction sheet
                  const soloNotes = section?.solo_notes?.notes ?? lesson?.solo_notes?.notes ?? []
                  const matchingIdx = soloNotes.findIndex((n: SoloNote) =>
                    Math.abs(n.pitch - note.midi!) < 2
                  )
                  if (matchingIdx >= 0) {
                    const n = soloNotes[matchingIdx]
                    setNoteCorrectingIndex(matchingIdx)
                    setNoteCorrectingOriginal({ pitch: n.pitch, start_time: n.start_time, duration: n.duration, velocity: n.velocity ?? 80 })
                  } else {
                    toast.info('No matching solo note found near this position')
                  }
                } else {
                  setNoteModalOpen(true)
                }
              }}
            />

            <View className="mt-2">
              <View className="flex-row items-center justify-between mb-2">
                <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
                  Annotations (long-press bar)
                </Text>
                <AnimatedPressable
                  onPress={() => setCorrectionMode((m) => !m)}
                  haptic="light"
                  className={`rounded-full px-3 py-1 border ${correctionMode
                    ? 'border-amber-accent bg-amber-accent/20'
                    : 'border-wood-600/35 bg-cream-dark/35'
                  }`}
                >
                  <Text className={`font-sans-medium text-[10px] ${correctionMode ? 'text-amber-accent' : 'text-muted-light'}`}>
                    {correctionMode ? '✏️ Correcting' : 'Correct'}
                  </Text>
                </AnimatedPressable>
              </View>
              <View className="flex-row flex-wrap gap-2">
                {[...Array(Math.max(1, Math.min(lesson?.bar_timestamps?.length ?? 0, STUDY_BAR_CHIP_MAX))).keys()].map((bar) => {
                  // Get chord for this bar - check section level first, then lesson level
                  const barTime = lesson?.bar_timestamps?.[bar] ?? 0
                  const chordEvents = section?.chord_timeline?.events ?? lesson?.chord_timeline?.events
                  const chordForBar = chordEvents
                    ?.slice()
                    ?.reverse()
                    ?.find((e: ChordEvent) => e.timestamp <= barTime && e.chord !== 'N')
                  const chordLabel = chordForBar ? formatChordDisplay(chordForBar.chord) : '—'
                  const chordRaw = chordForBar?.chord ?? 'N'

                  return (
                    <AnimatedPressable
                      key={`bar-${bar}`}
                      haptic="none"
                      onPress={() => {
                        if (correctionMode && chordForBar) {
                          // In correction mode, tapping opens the chord correction dropdown
                          setChordCorrectingBeat(bar)
                          return
                        }
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
                      className={`min-w-[40px] items-center rounded-full border px-2 py-1 ${bar === currentBar ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/35 bg-cream-dark/35'
                        }`}
                      accessibilityRole="button"
                      accessibilityHint={`${chordLabel} at bar ${bar}. ${correctionMode ? 'Tap to correct chord.' : 'Tap to seek; long press to save a practice note'}`}
                    >
                      <Text className={`font-mono text-[10px] ${bar === currentBar ? 'text-wood-900' : 'text-muted-light'}`}>
                        {chordLabel}
                      </Text>
                    </AnimatedPressable>
                  )
                })}
              </View>

              {/* Chord correction dropdown */}
              {chordCorrectingBeat != null && jobId ? (
                <ChordCorrectionDropdown
                  currentChord={(() => {
                    const barTime = lesson?.bar_timestamps?.[chordCorrectingBeat] ?? 0
                    const chordEvents = section?.chord_timeline?.events ?? lesson?.chord_timeline?.events
                    const found = chordEvents?.slice()?.reverse()?.find((e: ChordEvent) => e.timestamp <= barTime && e.chord !== 'N')
                    return found?.chord ?? 'N'
                  })()}
                  beatIndex={chordCorrectingBeat}
                  keySignature={lesson?.key ?? undefined}
                  onSelect={handleChordCorrection}
                  onCancel={() => setChordCorrectingBeat(null)}
                  className="mt-2"
                />
              ) : null}

              {/* Note correction sheet */}
              {noteCorrectingIndex != null && noteCorrectingOriginal && jobId ? (
                <NoteCorrectionSheet
                  noteIndex={noteCorrectingIndex}
                  originalNote={noteCorrectingOriginal}
                  onSave={handleNoteCorrection}
                  onCancel={() => { setNoteCorrectingIndex(null); setNoteCorrectingOriginal(null) }}
                  className="mt-2"
                />
              ) : null}

              {/* Correction history */}
              {correctionMode && correctionHistory && correctionHistory.corrections.length > 0 ? (
                <View className="mt-3">
                  <CorrectionHistoryPanel
                    corrections={correctionHistory.corrections}
                    correctionCount={correctionHistory.correction_count}
                    correctionCoverage={correctionHistory.correction_coverage}
                    onRevert={handleRevertCorrection}
                  />
                </View>
              ) : null}

              <Text className="mt-1 font-sans text-[11px] text-muted-light">
                Saved notes in this section: {Object.keys(sectionNotes).length}
                {correctionMode ? ` · Corrections: ${correctionHistory?.correction_count ?? 0}` : ''}
              </Text>
            </View>


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
