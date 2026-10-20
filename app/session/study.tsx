import { useFocusEffect } from '@react-navigation/native'
import { Audio } from 'expo-av'
import { useRouter } from 'expo-router'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Text, View } from 'react-native'
import { BookOpen, X } from 'lucide-react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { ChordCorrectionModal } from '@/components/ChordCorrectionModal'
import { ChordDiagram } from '@/components/ChordDiagram'
import { ChordPositionSelector } from '@/components/ChordPositionSelector'
import { ChordsAndLyrics } from '@/components/ChordsAndLyrics'
import { DemoTourCallout } from '@/components/DemoTourCallout'
import { EmptyState } from '@/components/EmptyState'
import { FretboardDiagram } from '@/components/FretboardDiagram'
import { NoteCorrectionPanel } from '@/components/NoteCorrectionPanel'
import { SessionNoteDetailModal } from '@/components/SessionNoteDetailModal'
import { SessionStemAndTab, type SessionStemAndTabHandle } from '@/components/SessionStemAndTab'
import { TheoryCard } from '@/components/TheoryCard'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { toast } from '@/components/ToastConfig'
import { colors } from '@/src/constants/colors'
import { correctChord, correctSoloNote, fetchTheoryAnnotation } from '@/src/api/analyze'
import { API_BASE_URL } from '@/src/config'
import { sessionHref } from '@/src/constants/sessionFlow'
import { MusicProvider, useMusicActions, useMusicState } from '@/src/context/MusicContext'
import { getAppPref } from '@/src/db/client'
import { PREF_PREFER_SIMPLER_TABS, TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX } from '@/src/db/schema'
import { DEMO_TOUR_CALLOUT, DEMO_TOUR_SUBTITLE } from '@/src/demo/demoSessionTourCopy'
import { useIsDemoLesson } from '@/src/demo/useIsDemoLesson'
import { capoSuggestion, parseKey } from '@/src/music/capoSuggestion'
import { getScalePitchClassesFromKey } from '@/src/music/scales'
import { getChordFunction } from '@/src/music/chordFunction'
import { findProgressions, COMMON_PROGRESSIONS } from '@/src/music/progressionAnalysis'
import type { ProgressionLabel } from '@/src/music/progressionAnalysis'
import { formatChordDisplay } from '@/src/music/chordVoicing'
import { buildNoteSelectionDetail } from '@/src/music/noteSelectionDetail'
import {
  barScopeForTime,
  findHarmonizedNoteForSelection,
  parseHarmonizedSolo,
  parsePerBarAnalysis,
} from '@/src/music/soloHarmony'
import { barIndexForPlaybackSeconds } from '@/src/session/smartScroll'
import { useFretboardTuner } from '@/src/session/useFretboardTuner'
import type { PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import { useStepCoachNarration } from '@/src/session/useStepCoachNarration'
import { useCorrectionStore } from '@/src/stores/correctionStore'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSessionAnnotationsStore } from '@/src/stores/sessionAnnotationsStore'
import {
  buildFretboardShareUrl,
  readFretboardShareStateFromLocation,
  type FretboardOverlayMode,
} from '@/src/utils/fretboardShareState'
import { findSoloNoteIndexForSelection } from '@/src/utils/feedback'
import { readSectionTabPayloads } from '@/src/utils/lessonTabs'
import type { NoteEventMessage } from '@/types/tabMessage'
import { getLessonWideChordEvents } from '@/src/utils/lessonChordTimeline'

// Transcription types (matching backend schemas)
interface ChordEvent {
  timestamp: number
  chord: string
  confidence: number
}

interface ChordTimelineMetadata {
  flicker_rate: number
  beat_alignment_pct: number
  downbeat_alignment_pct: number
  chord_change_histogram: {
    bins: string[]
    counts: number[]
    total_changes: number
    flicker_pct: number
    median_duration_beats: number
  }
  duration_filtering: {
    sub_beat_count: number
    total_chord_events: number
    sub_beat_ratio: number
    sub_beat_events: Array<{
      chord: string
      duration_beats: number
      confidence: number
      timestamp: number
    }>
  }
  total_events: number
  unique_chords: number
}

interface ChordTimeline {
  events: ChordEvent[]
  metadata?: ChordTimelineMetadata | null
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
  /** Commit 119: label confidence (0-1) */
  label_confidence?: number | null;
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

export default function StudyScreen() {
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const section = lesson?.sections?.[lessonSectionIndex] as LessonSectionWithMusic | undefined

  // Extract timeline data for MusicProvider (prefer lesson-wide timeline; merge sections if needed)
  // Use helper to ensure consistent whole-song chord events are provided to MusicProvider
  // so consumers (fretboard, chords UI) update as playback crosses sections.
  const chordEvents = getLessonWideChordEvents(lesson)
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
  const musicState = useMusicState()
  const sessionStemRef = useRef<SessionStemAndTabHandle>(null)
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const [tick, setTick] = useState<PlaybackTickContext>(DEFAULT_TICK)
  const [stemRoutingOverride, setStemRoutingOverride] = useState<string | null>(null);
  const [theoryAnnotation, setTheoryAnnotation] = useState<{
    chordName: string; chordFunction: string; romanNumeral: string; rationale: string
  } | null>(null);
  const [chordPosIndex, setChordPosIndex] = useState(0);
  useEffect(() => {
    setChordPosIndex(0);
  }, [theoryAnnotation?.chordName]);
  // Intelligent fretboard display mode (auto-detect or manual override)
  const [fretboardMode, setFretboardMode] = useState<'auto' | 'chords' | 'solo' | 'both'>('auto')
  const [voicingMode, setVoicingMode] = useState<'full' | 'compact'>('full')

  // Commit 110: chord correction state
  const jobId = lesson?.job_id ?? ''
  const corrections = useCorrectionStore((s) => s.corrections[jobId])
  const applyChordCorrectionStore = useCorrectionStore((s) => s.applyChordCorrection)
  const [chordModalVisible, setChordModalVisible] = useState(false)
  const [chordModalIndex, setChordModalIndex] = useState(0)
  const [chordModalChord, setChordModalChord] = useState('N')
  // Commit 110: note correction state
  const [noteModalVisible, setNoteModalVisible] = useState(false)
  const [noteModalIndex, setNoteModalIndex] = useState(0)
  const [noteModalPitch, setNoteModalPitch] = useState(60)
  const [noteModalDuration, setNoteModalDuration] = useState(0.5)
  const [noteModalStartTime, setNoteModalStartTime] = useState(0)
  const [noteModalString, setNoteModalString] = useState<number | undefined>(undefined)
  const [noteModalFret, setNoteModalFret] = useState<number | undefined>(undefined)
  const applyNoteCorrectionStore = useCorrectionStore((s) => s.applyNoteCorrection)
  const reportFeedback = useCorrectionStore((s) => s.reportFeedback)
  // Correction-aware chord events for display
  const correctedChordEvents = useMemo(() => {
    const raw = getLessonWideChordEvents(lesson)
    if (!raw?.length) return raw
    const normalized: Array<{ timestamp: number; chord: string; confidence: number }> = raw.map((e) => ({
      timestamp: e.timestamp,
      chord: e.chord,
      confidence: e.confidence ?? 0,
    }))
    if (!corrections?.chordCorrections?.length) return normalized
    return normalized.map((ev, idx) => {
      const c = corrections.chordCorrections.find((cc) => cc.eventIndex === idx)
      return c ? { ...ev, chord: c.correctedChord, confidence: 1.0 } : ev
    })
  }, [lesson, corrections])

  // Orient clip states (moved from separate orient.tsx screen)
  const [orientClipUrl, setOrientClipUrl] = useState<string | null>(null)
  const [orientAnnotation, setOrientAnnotation] = useState<string | null>(null)
  const [, setOrientIsLoading] = useState(false)
  const [orientError, setOrientError] = useState<string | null>(null)
  const [orientIsPlaying, setOrientIsPlaying] = useState(false)
  const orientSoundRef = useRef<any>(null)

  // Fetch orient clip when lesson changes
  useEffect(() => {
    const fetchOrientClip = async () => {
      if (!lesson?.job_id) return

      setOrientIsLoading(true)
      setOrientError(null)

      try {
        const response = await fetch(`${API_BASE_URL}/session/orient-clip`, {
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
  const soloNotesForFeedback = section?.solo_notes?.notes ?? lesson?.solo_notes?.notes ?? []

  // Update theory annotation based on current chord during playback
  useEffect(() => {
    const updateTheoryAnnotation = async () => {
    // Use lesson-wide chord events so theory annotations track across section boundaries
    const chordEvents = getLessonWideChordEvents(lesson)
      if (!chordEvents || !lesson?.key) return;

      // Find current chord based on playback position
      const currentChordEvent = chordEvents
        .slice()
        .reverse()
        .find((event) => event.timestamp <= tick.positionSec);

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
  const keyLabel = (lesson?.key ?? 'Unknown key').toString()
  const harmonizedSolo = useMemo(
    () => parseHarmonizedSolo(lesson?.harmonized_solo),
    [lesson?.harmonized_solo],
  )
  const perBarAnalysis = useMemo(
    () => parsePerBarAnalysis(lesson?.per_bar_analysis),
    [lesson?.per_bar_analysis],
  )
  const barScope = useMemo(
    () => barScopeForTime(perBarAnalysis, tick.positionSec),
    [perBarAnalysis, tick.positionSec],
  )
  const positionLabel = barScope?.primary_position
    ?? (typeof (section as Record<string, unknown> | undefined)?.primary_position === 'string'
      ? ((section as Record<string, unknown>).primary_position as string)
      : 'Tap a note to infer position')
  const capoText = useMemo(() => capoSuggestion(keyLabel, positionLabel), [keyLabel, positionLabel])
  const degreeRootPitchClass = useMemo(() => parseKey(keyLabel)?.semitone ?? null, [keyLabel])
  const scalePitchClasses = useMemo(() => getScalePitchClassesFromKey(keyLabel) ?? [], [keyLabel])
  // Commit B2: Sync scale pitch classes to MusicContext when key changes
  useEffect(() => {
    musicActions.setScalePitchClasses(scalePitchClasses)
  }, [scalePitchClasses, musicActions])
  const currentBar = useMemo(
    () => barIndexForPlaybackSeconds(lesson?.bar_timestamps ?? [], tick.positionSec),
    [lesson?.bar_timestamps, tick.positionSec],
  )

  const sectionKey = `${lesson?.job_id ?? 'no-job'}:${lessonSectionIndex}`
  const setAnnotation = useSessionAnnotationsStore((s) => s.setNote)

    const chordTimelineEvents = getLessonWideChordEvents(lesson) ?? null
  const barsData = useMemo(() => {
    const timestamps = lesson?.bar_timestamps
    if (!timestamps || !chordTimelineEvents) return []
    const words = toLyricWords(lesson?.lyrics_aligned)
    return timestamps.map((barTime, i) => {
      const nextBarTime = i + 1 < timestamps.length ? timestamps[i + 1] : Infinity
      const chordEvent = [...chordTimelineEvents]
        .reverse()
        .find((e) => e.timestamp >= barTime && e.timestamp < nextBarTime && e.chord !== 'N')
      const chord = chordEvent ? formatChordDisplay(chordEvent.chord) : ''
      const roman = chordEvent?.roman_numeral ?? undefined
      const voicing = chordEvent?.voicing_shape ?? undefined
      const barWords = words
        .filter((w) => w.timeSec >= barTime && w.timeSec < nextBarTime)
        .map((w) => w.word)
      return { chord, text: barWords.join(' '), roman, voicing }
    })
  }, [chordTimelineEvents, lesson?.bar_timestamps, lesson?.lyrics_aligned])

  // Commit B6: Compute progression labels from roman numeral sequence
  const progressionLabels = useMemo(() => {
    const romanNumerals = barsData.map(b => b.roman ?? '?')
    const matches = findProgressions(romanNumerals, COMMON_PROGRESSIONS)
    return matches.map(m => ({
      startBar: m.startBar,
      endBar: m.endBar,
      name: m.pattern.name,
      description: m.pattern.description,
    } satisfies ProgressionLabel))
  }, [barsData])

  const [variant, setVariant] = useState<TabVariant>('full')
  const [selectedNote, setSelectedNote] = useState<{ string?: number; fret?: number; midi?: number } | null>(null)
  const [fretPulseKey, setFretPulseKey] = useState(0)
  const [noteModalOpen, setNoteModalOpen] = useState(false)
  const [overlayMode, setOverlayMode] = useState<FretboardOverlayMode>('off')
  const [harmonicContextMode, setHarmonicContextMode] = useState<'key_context' | 'chord_only' | 'off'>('chord_only')
  const [preferSimplerTabs, setPreferSimplerTabs] = useState(false)
  const [transcriptionWarningDismissed, setTranscriptionWarningDismissed] = useState(false)
  const { state: tunerState, toggleTuner, startCalibration } = useFretboardTuner()

  const onTabNoteEvent = useCallback((evt: NoteEventMessage) => {
    setSelectedNote({ string: evt.string, fret: evt.fret, midi: evt.midi })
    setFretPulseKey((k) => k + 1)
    if (evt.fromScoreTap) {
      setNoteModalOpen(true)
    }
  }, [])

  const noteConfidence = typeof section?.confidence === 'number' ? section.confidence : (lesson?.transcription_confidence ?? null)
  const selectionDetail = useMemo(
    () => buildNoteSelectionDetail(keyLabel, selectedNote, musicState.currentChord, noteConfidence, {
      note: findHarmonizedNoteForSelection(harmonizedSolo, perBarAnalysis, {
        midi: selectedNote?.midi,
        timeSec: tick.positionSec,
      }),
    }),
    [keyLabel, selectedNote, musicState.currentChord, noteConfidence, harmonizedSolo, perBarAnalysis, tick.positionSec],
  )

  const notifyFeedbackSaved = useCallback((result: { serverSynced: boolean; syncError?: string }) => {
    if (result.serverSynced) {
      toast.success('Feedback saved')
    } else if (result.syncError) {
      toast.error(`Feedback saved on this device; server sync failed: ${result.syncError}`)
    } else {
      toast.success('Feedback saved on this device')
    }
  }, [])

  const reportSelectedNote = useCallback(async () => {
    if (!jobId) {
      toast.error('No analyzed song is loaded for feedback.')
      return
    }
    const index = findSoloNoteIndexForSelection(soloNotesForFeedback, {
      midi: selectedNote?.midi,
      timeSec: tick.positionSec,
    })
    if (index < 0) {
      toast.error('Could not match this note to the transcribed solo line.')
      return
    }
    const note = soloNotesForFeedback[index]!
    try {
      const result = await reportFeedback(
        jobId,
        {
          feedback_type: 'note_correction',
          event_index: index,
          original_value: { pitch: note.pitch, duration: note.duration, start_time: note.start_time },
          corrected_value: {},
        },
        { syncToServer: !isDemo },
      )
      notifyFeedbackSaved(result)
      setNoteModalOpen(false)
    } catch (e) {
      toast.error(`Could not save feedback: ${e instanceof Error ? e.message : 'unknown error'}`)
    }
  }, [isDemo, jobId, notifyFeedbackSaved, reportFeedback, selectedNote?.midi, soloNotesForFeedback, tick.positionSec])

  const correctSelectedNote = useCallback(() => {
    const index = findSoloNoteIndexForSelection(soloNotesForFeedback, {
      midi: selectedNote?.midi,
      timeSec: tick.positionSec,
    })
    if (index < 0) {
      toast.error('Could not match this note to the transcribed solo line.')
      return
    }
    const note = soloNotesForFeedback[index]!
    setNoteModalIndex(index)
    setNoteModalPitch(note.pitch)
    setNoteModalDuration(note.duration)
    setNoteModalStartTime(note.start_time)
    setNoteModalString(selectedNote?.string)
    setNoteModalFret(selectedNote?.fret)
    setNoteModalOpen(false)
    setNoteModalVisible(true)
  }, [selectedNote?.fret, selectedNote?.midi, selectedNote?.string, soloNotesForFeedback, tick.positionSec])

  const currentChordVoicing = useMemo(() => {
    if (currentBar == null || !chordTimelineEvents) return null
    const timestamps = lesson?.bar_timestamps
    if (!timestamps) return null
    const barTime = timestamps[currentBar]
    if (barTime == null) return null
    const nextBarTime = currentBar + 1 < timestamps.length ? timestamps[currentBar + 1] : Infinity
    const chordEvent = [...chordTimelineEvents]
      .reverse()
      .find((e) => e.timestamp >= barTime && e.timestamp < nextBarTime && e.chord !== 'N')
    if (!chordEvent?.voicing_shape) return null
    const pos = chordEvent.voicing_position
    if (pos && pos > 0) {
      const romanNumerals = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']
      const roman = romanNumerals[pos] ?? String(pos)
      return `${chordEvent.voicing_shape}-shape barre ${roman}`
    }
    return `${chordEvent.voicing_shape}-shape (open)`
  }, [currentBar, chordTimelineEvents, lesson?.bar_timestamps])

  const transcriptionConfidence = lesson?.transcription_confidence
  const sectionConfidence = typeof section?.confidence === 'number' ? section.confidence : 1.0
  const hasValidationFlag = !!(section?.transcription_metadata?.validation?.flag_reason)
  const isLowConfidence =
    (typeof transcriptionConfidence === 'number' && transcriptionConfidence < TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX)
    || sectionConfidence < TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX
  const showTranscriptionWarning =
    !transcriptionWarningDismissed && (isLowConfidence || hasValidationFlag)

  useFocusEffect(
    useCallback(() => {
      void getAppPref(PREF_PREFER_SIMPLER_TABS).then((v) => setPreferSimplerTabs(v === '1'))
    }, []),
  )

  useEffect(() => {
    setTranscriptionWarningDismissed(false)
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
      phaseEyebrow="Isolate phase"
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

      {!lesson ? (
        <EmptyState
          Icon={BookOpen}
          heading="No song loaded for the Study step"
          subtext="Start from the Home tab to add and analyze a song."
        />
      ) : (
        <>
      {showTranscriptionWarning && (
        <View className="mx-4 rounded-xl border border-amber-accent/50 bg-amber-accent/10 p-4">
          <View className="mb-2 flex-row items-center justify-between">
            <Text className="font-sans-medium text-amber-accent">
              Transcription Uncertainty
            </Text>
            <AnimatedPressable
              haptic="light"
              onPress={() => setTranscriptionWarningDismissed(true)}
              hitSlop={8}
            >
              <X color={colors.amber.accent} size={16} />
            </AnimatedPressable>
          </View>
          <Text className="mb-3 font-sans text-sm text-cream">
            We're {Math.round((lesson?.transcription_confidence ?? 1.0) * 100)}% sure about this transcription.
            {'\n'}
            This part is a rough approximation — use it as a guide, not a rule.
          </Text>

          {/* Stem routing override UI */}
          {lesson?.stems && Object.keys(lesson.stems).length > 1 && (
            <View className="mb-3">
              <Text className="mb-2 font-sans-medium text-xs text-cream">
                Re-route stem source:
              </Text>
              <View className="flex-row flex-wrap gap-2">
                {Object.keys(lesson.stems).map((stemName) => (
                  <AnimatedPressable
                    key={stemName}
                    className={`rounded-xl border px-3 py-1.5 ${stemRoutingOverride === stemName
                      ? 'border-amber-accent bg-amber-accent/20'
                      : 'border-wood-600/30 bg-wood-800/50'
                      }`}
                    onPress={() => {
                      setStemRoutingOverride(stemName)
                      console.log('[Study] stem routing override:', stemName)
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
              className="flex-1 rounded-xl border border-amber-accent/30 bg-amber-accent/20 px-3 py-2.5"
              onPress={() => {
                setTranscriptionWarningDismissed(true)
                const tabSurface = sessionStemRef.current?.getTabSurface()
                tabSurface?.setPlaybackRate(0.5)
              }}
            >
              <Text className="text-center font-sans-medium text-sm text-cream">
                Slow Down & Verify
              </Text>
            </AnimatedPressable>
            <AnimatedPressable
              className="flex-1 rounded-xl border border-wood-600/30 bg-wood-800/50 px-3 py-2.5"
              onPress={() => setTranscriptionWarningDismissed(true)}
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
        onPlaybackTick={handleStemPlaybackTick}
        onNoteEvent={onTabNoteEvent}
        onTabVariantChange={setVariant}
        tabFrameClassName="mt-2 min-h-[328px] w-full px-2"
        insertBetweenStemAndTab={
          <>
            {/* Chord diagram with position selector */}
            {theoryAnnotation && theoryAnnotation.chordName && theoryAnnotation.chordName !== 'N' && (
              <View className="flex-row items-center gap-3 px-2 py-1">
                <ChordDiagram
                  name={theoryAnnotation.chordName}
                  size="md"
                  positionIndex={chordPosIndex}
                />
                <View className="flex-1">
                  <Text className="font-serif text-md text-cream">
                    {theoryAnnotation.romanNumeral}
                  </Text>
                  <Text className="font-sans text-xs text-muted-brown">
                    {theoryAnnotation.chordFunction}
                  </Text>
                  <ChordPositionSelector
                    chordSymbol={theoryAnnotation.chordName}
                    currentIndex={chordPosIndex}
                    onPositionChange={setChordPosIndex}
                  />
                </View>
              </View>
            )}

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
              scalePitchClasses={scalePitchClasses}
              voicingLabel={currentChordVoicing ?? undefined}
              harmonicContextMode={harmonicContextMode}
              onHarmonicContextModeChange={setHarmonicContextMode}
              onSelectNote={(note) => {
                setSelectedNote(note)
                setFretPulseKey((k) => k + 1)
                setNoteModalOpen(true)
              }}
            />

            {barScope && barScope.suggested_scales.length > 0 ? (
              <Text className="font-sans text-xs text-muted-brown px-2 mt-1">
                Scale ideas: {barScope.suggested_scales.join(' · ')}
              </Text>
            ) : null}

            <View className="mt-2">
             <ChordsAndLyrics
                  bars={barsData}
                  currentBar={currentBar}
                  bpm={lesson?.tempo ?? 92}
                  onBarPress={(bar) => {
                    const stamps = lesson?.bar_timestamps
                    const t = Array.isArray(stamps) && typeof stamps[bar] === 'number' ? stamps[bar]! : 0
                    void (async () => {
                      await sessionStemRef.current?.seekTransportToSeconds(t)
                      sessionStemRef.current?.scrollMasterBarIntoView(bar)
                    })()
                  }}
                  onBarLongPress={(bar) => {
                    const text = `Practice note @ bar ${bar} (${new Date().toLocaleTimeString()})`
                    setAnnotation(sectionKey, bar, text)
                  }}
                  onChordTap={(barIdx, chord) => {
                    // Find the event index in chordEvents that corresponds to this bar
                    const barTime = lesson?.bar_timestamps?.[barIdx] ?? 0
                    const eventIdx = correctedChordEvents
                      ?.slice()
                      .reverse()
                      .findIndex((ev) => ev.timestamp <= barTime)
                    const idx = eventIdx != null && eventIdx >= 0 ? correctedChordEvents!.length - 1 - eventIdx : 0
                    setChordModalIndex(idx)
                    setChordModalChord(chord)
                    setChordModalVisible(true)
                  }}
                   progressionLabels={progressionLabels}
                   onProgressionTap={(label) => {
                     toast.info(`${label.name}: ${label.description}`)
                   }}
                   barsPerLine={4}
                   label={(section?.label ?? '') as string}
                   labelConfidence={section?.label_confidence ?? null}
                 />
            </View>

            {/* Commit 116: Theory annotation card for current chord */}
            {theoryAnnotation && (
              <View className="mt-2 px-2">
                <TheoryCard
                  chordName={theoryAnnotation.chordName}
                  chordFunction={theoryAnnotation.chordFunction}
                  romanNumeral={theoryAnnotation.romanNumeral}
                  rationale={theoryAnnotation.rationale}
                />
              </View>
            )}

          </>
        }
      />

      <SessionNoteDetailModal
        detail={selectionDetail}
        visible={noteModalOpen}
        onClose={() => setNoteModalOpen(false)}
        currentChordVoicing={currentChordVoicing}
        onReportIncorrect={() => void reportSelectedNote()}
        onCorrectNote={correctSelectedNote}
      />

      {/* Commit 110: Chord correction modal */}
      <ChordCorrectionModal
        visible={chordModalVisible}
        currentChord={chordModalChord}
        songKey={lesson?.key ?? null}
        eventIndex={chordModalIndex}
        onSelect={async (idx, newChord) => {
          const original = correctedChordEvents?.[idx]?.chord ?? 'N'
          if (jobId) {
            void reportFeedback(
              jobId,
              {
                feedback_type: 'chord_correction',
                event_index: idx,
                original_value: { chord: original },
                corrected_value: { chord: newChord },
              },
              { syncToServer: !isDemo },
            ).then(notifyFeedbackSaved).catch((e) => {
              toast.error(`Could not save feedback: ${e instanceof Error ? e.message : 'unknown error'}`)
            })
          }
          await applyChordCorrectionStore(jobId, idx, original, newChord)
          // Re-apply to lesson for immediate display
          if (lesson && jobId) {
            const updatedCorrections = useCorrectionStore.getState().getCorrections(jobId)
            const patched = correctedChordEvents?.map((ev, i) => {
              const c = updatedCorrections.chordCorrections.find((cc) => cc.eventIndex === i)
              return c ? { ...ev, chord: c.correctedChord, confidence: 1.0 } : ev
            })
            const updatedLesson = { ...lesson, chord_timeline: { events: patched ?? [], metadata: lesson.chord_timeline?.metadata ?? null } as import('@/src/types').ChordTimeline }
            useLessonStore.getState().saveLesson(updatedLesson)
          }
          // Commit 153: sync to backend so the rebuilt MusicXML can be re-fetched.
          if (jobId && !isDemo) {
            void correctChord(jobId, idx, { chord: newChord })
              .then(() => useLessonStore.getState().requestScoreRefetch(jobId))
              .catch((e) => {
                console.log('[Study] chord correction sync failed', e)
                toast.error(
                  `Chord saved locally, but the score could not refresh: ${e instanceof Error ? e.message : 'unknown error'}`,
                )
              })
          }
        }}
        onMarkWrong={() => {
          if (!jobId) {
            toast.error('No analyzed song is loaded for feedback.')
            return
          }
          const original = correctedChordEvents?.[chordModalIndex]?.chord ?? chordModalChord
          void reportFeedback(
            jobId,
            {
              feedback_type: 'wrong_chord',
              event_index: chordModalIndex,
              original_value: { chord: original },
              corrected_value: null,
            },
            { syncToServer: !isDemo },
          ).then(notifyFeedbackSaved).catch((e) => {
            toast.error(`Could not save feedback: ${e instanceof Error ? e.message : 'unknown error'}`)
          })
        }}
        onClose={() => setChordModalVisible(false)}
      />

      {/* Commit 110: Note correction panel */}
      <NoteCorrectionPanel
        visible={noteModalVisible}
        noteIndex={noteModalIndex}
        originalPitch={noteModalPitch}
        originalDuration={noteModalDuration}
        originalStartTime={noteModalStartTime}
        currentString={noteModalString}
        currentFret={noteModalFret}
        onSelect={async (idx, corrected) => {
          if (jobId) {
            void reportFeedback(
              jobId,
              {
                feedback_type: 'note_correction',
                event_index: idx,
                original_value: {
                  pitch: noteModalPitch,
                  duration: noteModalDuration,
                  start_time: noteModalStartTime,
                },
                corrected_value: corrected,
              },
              { syncToServer: !isDemo },
            ).then(notifyFeedbackSaved).catch((e) => {
              toast.error(`Could not save feedback: ${e instanceof Error ? e.message : 'unknown error'}`)
            })
          }
          await applyNoteCorrectionStore(
            jobId,
            idx,
            { pitch: noteModalPitch, duration: noteModalDuration, start_time: noteModalStartTime },
            corrected,
          )
          // Re-apply to lesson
          if (lesson && jobId) {
            const updatedCorrections = useCorrectionStore.getState().getCorrections(jobId)
            const soloNotes = section?.solo_notes?.notes ?? lesson?.solo_notes?.notes ?? []
            const patchedNotes = soloNotes.map((n, i) => {
              const c = updatedCorrections.noteCorrections.find((nc) => nc.noteIndex === i)
              if (!c) return n
              return {
                start_time: c.correctedStartTime ?? n.start_time,
                duration: c.correctedDuration ?? n.duration,
                pitch: c.correctedPitch ?? n.pitch,
                velocity: n.velocity,
              }
            })
            const updatedLesson = { ...lesson, solo_notes: { notes: patchedNotes } }
            useLessonStore.getState().saveLesson(updatedLesson)
          }
          // Commit 153: sync to backend so the rebuilt MusicXML can be re-fetched.
          if (jobId && !isDemo) {
            void correctSoloNote(jobId, idx, corrected)
              .then(() => useLessonStore.getState().requestScoreRefetch(jobId))
              .catch((e) => {
                console.log('[Study] note correction sync failed', e)
                toast.error(
                  `Note saved locally, but the score could not refresh: ${e instanceof Error ? e.message : 'unknown error'}`,
                )
              })
          }
        }}
        onReportWrong={(idx) => {
          if (!jobId) {
            toast.error('No analyzed song is loaded for feedback.')
            return
          }
          const note = soloNotesForFeedback[idx]
          if (!note) {
            toast.error('Could not find the transcribed note for feedback.')
            return
          }
          void reportFeedback(
            jobId,
            {
              feedback_type: 'note_correction',
              event_index: idx,
              original_value: { pitch: note.pitch, duration: note.duration, start_time: note.start_time },
              corrected_value: {},
            },
            { syncToServer: !isDemo },
          ).then(notifyFeedbackSaved).catch((e) => {
            toast.error(`Could not save feedback: ${e instanceof Error ? e.message : 'unknown error'}`)
          })
        }}
        onClose={() => setNoteModalVisible(false)}
      />
        </>
      )}
    </SessionStepScreen>
  )
}
