import { useFocusEffect } from '@react-navigation/native'
import { Audio } from 'expo-av'
import { useRouter } from 'expo-router'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { DemoTourCallout } from '@/components/DemoTourCallout'
import { ErrorBanner } from '@/components/ErrorBanner'
import { FretboardDiagram } from '@/components/FretboardDiagram'
import { LyricsStrip } from '@/components/LyricsStrip'
import { ScoreViewer } from '@/components/ScoreViewer'
import { SessionNoteDetailModal } from '@/components/SessionNoteDetailModal'
import { SessionStemAndTab, type SessionStemAndTabHandle } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { TheoryCard } from '@/components/TheoryCard'
import { toast } from '@/components/ToastConfig'
import { exportMusicXmlFromJson, fetchTheoryAnnotation } from '@/src/api/analyze'
import { sessionHref } from '@/src/constants/sessionFlow'
import { getAppPref } from '@/src/db/client'
import { PREF_PREFER_SIMPLER_TABS, TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX } from '@/src/db/schema'
import { DEMO_TOUR_CALLOUT, DEMO_TOUR_SUBTITLE } from '@/src/demo/demoSessionTourCopy'
import { useIsDemoLesson } from '@/src/demo/useIsDemoLesson'
import { mapLowTranscriptionConfidenceBanner, toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import { capoSuggestion, parseKey } from '@/src/music/capoSuggestion'
import { getChordFunction } from '@/src/music/chordFunction'
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
import { readSectionTabPayloads } from '@/src/utils/lessonTabs'
import type { AlphaTabSurfaceRef, NoteEventMessage } from '@/types/tabMessage'
import type { ChordEvent, ChordTimeline, SoloNote, SoloNotes } from '@/types/transcription'

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

type ProcessedMusicalEvent = { type: 'chord', time: number, data: ChordEvent } | { type: 'solo_note', time: number, data: SoloNote };

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
  useStepCoachNarration()
  const isDemo = useIsDemoLesson()
  const router = useRouter()
  const sessionStemRef = useRef<SessionStemAndTabHandle>(null)
  const scoreViewerRef = useRef<AlphaTabSurfaceRef>(null)
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const [tick, setTick] = useState<PlaybackTickContext>(DEFAULT_TICK)
  const [musicXmlData, setMusicXmlData] = useState<string | null>(null);
  const [alphaTabIsReady, setAlphaTabIsReady] = useState(false);
  const [processedMusicalEvents, setProcessedMusicalEvents] = useState<ProcessedMusicalEvent[]>([]);
  const [showTranscriptionWarningModal, setShowTranscriptionWarningModal] = useState(false);
  const [stemRoutingOverride, setStemRoutingOverride] = useState<string | null>(null);
  const [theoryAnnotation, setTheoryAnnotation] = useState<{ chordName: string; chordFunction: string; romanNumeral: string; rationale: string } | null>(null);

  // Orient clip states (moved from separate orient.tsx screen)
  const [orientClipUrl, setOrientClipUrl] = useState<string | null>(null)
  const [orientAnnotation, setOrientAnnotation] = useState<string | null>(null)
  const [orientIsLoading, setOrientIsLoading] = useState(false)
  const [orientError, setOrientError] = useState<string | null>(null)
  const [orientIsPlaying, setOrientIsPlaying] = useState(false)
  const orientSoundRef = useRef<any>(null)
  const orientSoundInstanceId = useRef(`study-orient-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`)

  // Fetch MusicXML from backend when transcription data is available
  useEffect(() => {
    const fetchMusicXml = async () => {
      const section = lesson?.sections?.[lessonSectionIndex] as LessonSectionWithMusic | undefined
      if (!section) return

      // Check if we have the required transcription data
      const hasBeatGrid = section.beat_grid != null
      const hasChordTimeline = section.chord_timeline != null
      const hasSoloNotes = section.solo_notes != null

      if (!hasBeatGrid || !hasChordTimeline || !hasSoloNotes) {
        setMusicXmlData(null)
        return
      }

      try {
        const musicXml = await exportMusicXmlFromJson({
          beat_grid: section.beat_grid,
          chord_timeline: section.chord_timeline,
          solo_notes: section.solo_notes,
          title: lesson?.song_title ?? null,
          artist: lesson?.artist ?? null,
        })
        setMusicXmlData(musicXml)
      } catch (e) {
        console.error('Failed to fetch MusicXML:', e)
        setMusicXmlData(null)
      }
    }

    void fetchMusicXml()
  }, [lesson?.job_id, lessonSectionIndex, lesson?.song_title, lesson?.artist])

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
  }, [])

  const handleAlphaTabReady = useCallback(() => {
    setAlphaTabIsReady(true);
    console.log('AlphaTab is ready!');
  }, []);

  const handleCursorPositionUpdate = useCallback((position: number) => {
    // console.log('Cursor position:', position);

    let currentEvent = null;
    for (let i = processedMusicalEvents.length - 1; i >= 0; i--) {
      if (processedMusicalEvents[i].time <= position) {
        currentEvent = processedMusicalEvents[i];
        break;
      }
    }

    if (currentEvent) {
      if (currentEvent.type === 'solo_note') {
        const note = currentEvent.data;
        // This is a placeholder, as SoloNote schema doesn't directly contain fret/string.
        // In a real scenario, you'd map pitch to a fretboard position.
        // For now, we'll use pitch as a proxy for midi and assign dummy fret/string.
        setSelectedNote({ midi: note.pitch, fret: note.pitch % 12, string: (note.pitch % 6) + 1 });
      } else if (currentEvent.type === 'chord') {
        const chordEvent = currentEvent.data;
        // For chords, we might want to highlight the chord shape or root note.
        // This is a simplified representation.
        // Assuming 'C:maj' -> C (MIDI 60), 'D:min' -> D (MIDI 62) etc.
        const rootNote = chordEvent.chord.split(':')[0];
        // This mapping is highly simplified and needs proper music theory implementation.
        const midiMap: { [key: string]: number } = { 'C': 60, 'D': 62, 'E': 64, 'F': 65, 'G': 67, 'A': 69, 'B': 71 };
        const midi = midiMap[rootNote] || 0;
        setSelectedNote({ midi: midi, fret: midi % 12, string: (midi % 6) + 1 });
      }
    } else {
      setSelectedNote(null);
    }
    setFretPulseKey((k) => k + 1);
  }, [processedMusicalEvents]);

  const handleBeatEvent = useCallback((beat: number) => {
    console.log('Beat event:', beat);
    // TODO: Potentially update UI elements based on beat
  }, []);

  const section = lesson?.sections?.[lessonSectionIndex] as LessonSectionWithMusic | undefined

  useEffect(() => {
    if (section?.chord_timeline?.events || section?.solo_notes?.notes) {
      const allEvents: ProcessedMusicalEvent[] = [];

      if (section.chord_timeline?.events) {
        section.chord_timeline.events.forEach((event: ChordEvent) => {
          allEvents.push({ type: 'chord', time: event.timestamp, data: event });
        });
      }

      if (section.solo_notes?.notes) {
        section.solo_notes.notes.forEach((note: SoloNote) => {
          allEvents.push({ type: 'solo_note', time: note.start_time, data: note });
        });
      }

      allEvents.sort((a, b) => a.time - b.time);
      setProcessedMusicalEvents(allEvents);
    }
  }, [section?.chord_timeline, section?.solo_notes]);

  // Update theory annotation based on current chord during playback
  useEffect(() => {
    const updateTheoryAnnotation = async () => {
      if (!section?.chord_timeline?.events || !lesson?.key) return;

      // Find current chord based on playback position
      const currentChordEvent = section.chord_timeline.events
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
  }, [tick.positionSec, section?.chord_timeline, lesson?.key]);

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
          <Text className="mb-2 font-sans-semibold text-amber-accent">
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
                    className={`rounded-md border px-3 py-1.5 ${
                      stemRoutingOverride === stemName
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
                      className={`font-sans-medium text-xs ${
                        stemRoutingOverride === stemName ? 'text-amber-accent' : 'text-cream'
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

      {musicXmlData && (
        <View style={{ flex: 1, height: 300, width: '100%' }}>
          <ScoreViewer
            ref={scoreViewerRef}
            musicXml={musicXmlData}
            onAlphaTabReady={handleAlphaTabReady}
            onCursorPositionUpdate={handleCursorPositionUpdate}
            onBeatEvent={handleBeatEvent}
            onNoteEvent={onTabNoteEvent}
          />
        </View>
      )}

      <SessionStemAndTab
        ref={sessionStemRef}
        tabRenderPreset="study"
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
              showOrientControl={!orientError}
              orientClipUrl={orientClipUrl}
              orientAnnotation={orientAnnotation}
              orientIsPlaying={orientIsPlaying}
              onToggleOrientPlayback={handleToggleOrientPlayback}
              onSelectNote={(note) => {
                setSelectedNote(note)
                setFretPulseKey((k) => k + 1)
                setNoteModalOpen(true)
              }}
            />

            <LyricsStrip words={lyricWords} playbackSec={tick.positionSec} />

            {theoryAnnotation && (
              <TheoryCard
                chordName={theoryAnnotation.chordName}
                chordFunction={theoryAnnotation.chordFunction}
                romanNumeral={theoryAnnotation.romanNumeral}
                rationale={theoryAnnotation.rationale}
              />
            )}

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
