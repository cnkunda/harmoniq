import type { SessionJournalRow, UserFeedbackRow } from '@/src/db/types'
import { sessionOverallAccuracy } from '@/src/home/sessionAccuracy'
import { CHROMATIC_NOTE_NAMES } from '@/src/music/noteNames'
import { formatChordDisplay, parseChordSymbol } from '@/src/music/chordVoicing'
import { parseHarmonizedSolo } from '@/src/music/soloHarmony'
import type { LessonJSON } from '@/src/types'
import { parseFeedbackValues } from '@/src/utils/feedback'
import { getLessonWideChordEvents } from '@/src/utils/lessonChordTimeline'

/** Longest span the falling-note stage loops through before restarting. */
export const PULSE_WINDOW_SEC = 32

const DEFAULT_BPM = 90
const DEFAULT_BEATS_PER_BAR = 4
const NOTE_TO_PITCH_CLASS: Record<string, number> = {
  C: 0,
  'C#': 1,
  Db: 1,
  D: 2,
  'D#': 3,
  Eb: 3,
  E: 4,
  F: 5,
  'F#': 6,
  Gb: 6,
  G: 7,
  'G#': 8,
  Ab: 8,
  A: 9,
  'A#': 10,
  Bb: 10,
  B: 11,
}

/** Semitone intervals from the root for the chord qualities the visualizer understands. */
const CHORD_TONE_INTERVALS: Record<string, number[]> = {
  maj: [0, 4, 7],
  min: [0, 3, 7],
  dim: [0, 3, 6],
  aug: [0, 4, 8],
  '7': [0, 4, 7, 10],
  maj7: [0, 4, 7, 11],
  min7: [0, 3, 7, 10],
  '7sus4': [0, 5, 7, 10],
  sus4: [0, 5, 7],
  sus2: [0, 2, 7],
  '6': [0, 4, 7, 9],
  min6: [0, 3, 7, 9],
  '9': [0, 4, 7, 10, 2],
  maj9: [0, 4, 7, 11, 2],
  min9: [0, 3, 7, 10, 2],
  dim7: [0, 3, 6, 9],
  '7b9': [0, 4, 7, 10, 1],
  '7#9': [0, 4, 7, 10, 3],
  '11': [0, 4, 7, 10, 2, 5],
  '13': [0, 4, 7, 10, 2, 5, 9],
}

export type ChordQualityColumn = 'maj' | 'min' | '7' | 'maj7' | 'min7' | 'other'

export interface ChordQualityColumnDefinition {
  id: ChordQualityColumn
  label: string
}

export const CHORD_QUALITY_COLUMNS: readonly ChordQualityColumnDefinition[] = [
  { id: 'maj', label: 'Maj' },
  { id: 'min', label: 'Min' },
  { id: '7', label: '7' },
  { id: 'maj7', label: 'Maj7' },
  { id: 'min7', label: 'Min7' },
  { id: 'other', label: 'Other' },
] as const

export const PULSE_ROOTS = CHROMATIC_NOTE_NAMES

export interface PulseChordEvent {
  timestamp: number
  chord: string
  display: string
  confidence: number
  roman: string | null
}

export interface PulseBeatGrid {
  bpm: number
  pulseBpm: number
  beats: number[]
  downbeats: number[]
  beatsPerBar: number
  denominator: number
}

export interface PulseBar {
  index: number
  startSec: number
  endSec: number
  chord: string
  display: string
  confidence: number
  roman: string | null
}

export interface PulseFallingNote {
  id: string
  startSec: number
  durationSec: number
  pitch: number
  pitchClass: number
  isChordTone: boolean
  velocity: number
}

export interface PulseStageData {
  events: PulseChordEvent[]
  bars: PulseBar[]
  beatGrid: PulseBeatGrid
  notes: PulseFallingNote[]
  durationSec: number
  windowSec: number
}

export interface PulseAccuracyPoint {
  id: string
  date: string
  label: string
  accuracy: number
}

export interface ChordMasteryCell {
  rootPc: number
  rootLabel: string
  quality: ChordQualityColumn
  qualityLabel: string
  practiceCount: number
  correctionCount: number
  /** Estimated 0-1 mastery, or null when neither practice nor corrections exist. */
  mastery: number | null
}

export interface ChordMasteryHeatmap {
  cells: ChordMasteryCell[]
  populatedCount: number
  sessionCount: number
}

export interface SessionLessonPair {
  session: SessionJournalRow
  lesson: LessonJSON | null
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}

function finite(value: number | null | undefined, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function normalizeEvents(lesson: LessonJSON): PulseChordEvent[] {
  const raw = getLessonWideChordEvents(lesson) ?? []
  return raw
    .filter((event) => typeof event.timestamp === 'number' && Number.isFinite(event.timestamp))
    .filter((event) => typeof event.chord === 'string' && event.chord.trim() !== '' && event.chord !== 'N')
    .map((event) => ({
      timestamp: Math.max(0, event.timestamp),
      chord: event.chord,
      display: formatChordDisplay(event.chord),
      confidence: clamp01(finite(event.confidence, 0.5)),
      roman: event.roman_numeral?.trim() ? event.roman_numeral.trim() : null,
    }))
    .sort((a, b) => a.timestamp - b.timestamp)
}

function uniqueSorted(values: readonly number[]): number[] {
  const out: number[] = []
  for (const value of [...values].sort((a, b) => a - b)) {
    if (!Number.isFinite(value) || value < 0) continue
    if (out.length === 0 || Math.abs(out[out.length - 1]! - value) > 0.001) out.push(value)
  }
  return out
}

function estimateDuration(lesson: LessonJSON, events: readonly PulseChordEvent[]): number {
  const lastEvent = events.length > 0 ? events[events.length - 1]!.timestamp : 0
  const lastBar = lesson.bar_timestamps?.length ? Math.max(...lesson.bar_timestamps) : 0
  const lastBeat = lesson.beat_grid_structured?.beats?.length
    ? Math.max(...lesson.beat_grid_structured.beats)
    : lesson.beat_grid?.length
      ? Math.max(...lesson.beat_grid)
      : 0
  const structured = lesson.beat_grid_structured
  const bpm = finite(structured?.bpm ?? lesson.tempo, DEFAULT_BPM)
  const beatsPerBar = finite(structured?.time_signature?.numerator, DEFAULT_BEATS_PER_BAR)
  const barSec = (60 / Math.max(20, bpm)) * Math.max(1, beatsPerBar)
  const soloNotes = lesson.solo_notes?.notes
  const lastSolo =
    Array.isArray(soloNotes) && soloNotes.length > 0
      ? Math.max(...soloNotes.map((note) => note.start_time + Math.max(0, note.duration)))
      : 0
  const harmonized = parseHarmonizedSolo(lesson.harmonized_solo)
  const lastHarmonized =
    harmonized && harmonized.notes.length > 0
      ? Math.max(...harmonized.notes.map((note) => note.start_time + Math.max(0, note.duration)))
      : 0
  return Math.max(1, lastEvent + barSec, lastBar + barSec, lastBeat + 60 / Math.max(20, bpm), lastSolo, lastHarmonized)
}

export function resolveBeatGrid(
  lesson: LessonJSON,
  durationSec: number,
): PulseBeatGrid {
  const structured = lesson.beat_grid_structured
  const bpm = Math.max(20, finite(structured?.bpm ?? lesson.tempo, DEFAULT_BPM))
  const beatsPerBar = Math.max(1, Math.round(finite(structured?.time_signature?.numerator, DEFAULT_BEATS_PER_BAR)))
  const denominator = Math.max(1, Math.round(finite(structured?.time_signature?.denominator, 4)))
  const pulseBpm = Math.max(20, finite(structured?.pulse_bpm, bpm))

  let beats = uniqueSorted(structured?.beats?.length ? structured.beats : (lesson.beat_grid ?? []))
  if (beats.length === 0 && durationSec > 0) {
    const beatSec = 60 / bpm
    for (let t = 0; t < durationSec; t += beatSec) beats.push(Number(t.toFixed(3)))
  }

  const structuredDownbeats = uniqueSorted(structured?.downbeats ?? [])
  const downbeats =
    structuredDownbeats.length > 0
      ? structuredDownbeats
      : beats.filter((_, index) => index % beatsPerBar === 0)

  return { bpm, pulseBpm, beats, downbeats, beatsPerBar, denominator }
}

function deriveBarStarts(lesson: LessonJSON, beatGrid: PulseBeatGrid, durationSec: number): number[] {
  const explicit = uniqueSorted(lesson.bar_timestamps ?? [])
  if (explicit.length > 0) return explicit
  if (beatGrid.downbeats.length > 0) return beatGrid.downbeats

  const barSec = (60 / beatGrid.bpm) * beatGrid.beatsPerBar
  const bars: number[] = []
  for (let t = 0; t < durationSec; t += barSec) bars.push(Number(t.toFixed(3)))
  return bars
}

export function buildChordBars(
  lesson: LessonJSON,
  events: readonly PulseChordEvent[],
  beatGrid: PulseBeatGrid,
  durationSec: number,
): PulseBar[] {
  if (events.length === 0) return []
  const starts = deriveBarStarts(lesson, beatGrid, durationSec)
  if (starts.length === 0) return []

  return starts.map((startSec, index) => {
    const endSec = index + 1 < starts.length ? starts[index + 1]! : durationSec
    const clampedStart = Math.max(0, Math.min(startSec, durationSec))
    let active: PulseChordEvent | null = null
    for (const event of events) {
      if (event.timestamp <= clampedStart + 0.05) active = event
      else break
    }
    const fallback = events.find((event) => event.timestamp < endSec) ?? null
    const chordEvent = active ?? fallback
    return {
      index,
      startSec: clampedStart,
      endSec: Math.max(clampedStart, endSec),
      chord: chordEvent?.chord ?? 'N',
      display: chordEvent?.display ?? '—',
      confidence: chordEvent?.confidence ?? 0,
      roman: chordEvent?.roman ?? null,
    }
  })
}

function chordTonePitchClasses(chord: string): Set<number> {
  const parsed = parseChordSymbol(chord)
  if (!parsed) return new Set()
  const rootPc = NOTE_TO_PITCH_CLASS[parsed.root]
  if (rootPc == null) return new Set()
  const intervals = CHORD_TONE_INTERVALS[parsed.quality] ?? CHORD_TONE_INTERVALS.maj!
  return new Set(intervals.map((interval) => (((rootPc + interval) % 12) + 12) % 12))
}

function activeChordAt(events: readonly PulseChordEvent[], timeSec: number): PulseChordEvent | null {
  let active: PulseChordEvent | null = null
  for (const event of events) {
    if (event.timestamp <= timeSec) active = event
    else break
  }
  return active
}

function buildHarmonizedNotes(
  lesson: LessonJSON,
  windowSec: number,
): PulseFallingNote[] {
  const harmonized = parseHarmonizedSolo(lesson.harmonized_solo)
  if (!harmonized || harmonized.notes.length === 0) return []
  return harmonized.notes
    .filter((note) => note.start_time < windowSec)
    .map((note, index) => ({
      id: `h-${index}-${note.start_time}-${note.pitch}`,
      startSec: Math.max(0, note.start_time),
      durationSec: Math.max(0.08, note.duration),
      pitch: note.pitch,
      pitchClass: ((Math.round(note.pitch) % 12) + 12) % 12,
      isChordTone: note.chord_analysis?.chord_tone_type === 'chord_tone',
      velocity: clamp01(note.velocity > 1 ? note.velocity / 127 : note.velocity),
    }))
}

function buildSoloNotes(
  lesson: LessonJSON,
  events: readonly PulseChordEvent[],
  windowSec: number,
): PulseFallingNote[] {
  const notes = lesson.solo_notes?.notes
  if (!Array.isArray(notes) || notes.length === 0) return []
  return notes
    .filter((note) => note.start_time < windowSec)
    .map((note, index) => {
      const chord = activeChordAt(events, note.start_time)
      const toneSet = chord ? chordTonePitchClasses(chord.chord) : new Set<number>()
      const pitchClass = ((Math.round(note.pitch) % 12) + 12) % 12
      return {
        id: `s-${index}-${note.start_time}-${note.pitch}`,
        startSec: Math.max(0, note.start_time),
        durationSec: Math.max(0.08, note.duration),
        pitch: note.pitch,
        pitchClass,
        isChordTone: toneSet.has(pitchClass),
        velocity: clamp01(finite(note.velocity, 0.75)),
      }
    })
}

function buildSynthesizedNotes(
  events: readonly PulseChordEvent[],
  barGrid: PulseBeatGrid,
  windowSec: number,
): PulseFallingNote[] {
  const notes: PulseFallingNote[] = []
  const barSec = (60 / barGrid.bpm) * barGrid.beatsPerBar
  events.forEach((event, eventIndex) => {
    if (event.timestamp >= windowSec) return
    const next = events[eventIndex + 1]?.timestamp ?? event.timestamp + barSec
    const durationSec = Math.max(0.25, Math.min(barSec, next - event.timestamp))
    const parsed = parseChordSymbol(event.chord)
    const rootPc = parsed ? NOTE_TO_PITCH_CLASS[parsed.root] : null
    const intervals = parsed ? (CHORD_TONE_INTERVALS[parsed.quality] ?? CHORD_TONE_INTERVALS.maj!) : [0, 4, 7]
    for (const interval of intervals) {
      const pitchClass = rootPc == null ? interval : (((rootPc + interval) % 12) + 12) % 12
      notes.push({
        id: `c-${eventIndex}-${pitchClass}-${event.timestamp}`,
        startSec: event.timestamp + 0.05,
        durationSec,
        pitch: 48 + pitchClass,
        pitchClass,
        isChordTone: true,
        velocity: 0.65,
      })
    }
  })
  return notes
}

export function buildFallingNotes(
  lesson: LessonJSON,
  events: readonly PulseChordEvent[],
  beatGrid: PulseBeatGrid,
  windowSec: number,
): PulseFallingNote[] {
  const harmonized = buildHarmonizedNotes(lesson, windowSec)
  const source = harmonized.length > 0 ? harmonized : buildSoloNotes(lesson, events, windowSec)
  const notes = source.length > 0 ? source : buildSynthesizedNotes(events, beatGrid, windowSec)
  return notes
    .filter((note) => Number.isFinite(note.startSec) && note.startSec <= windowSec && note.pitchClass >= 0 && note.pitchClass < 12)
    .sort((a, b) => a.startSec - b.startSec)
    .slice(0, 240)
}

export function buildPulseStageData(lesson: LessonJSON | null | undefined): PulseStageData {
  if (!lesson) {
    return {
      events: [],
      bars: [],
      beatGrid: resolveBeatGrid({}, 0),
      notes: [],
      durationSec: 0,
      windowSec: 0,
    }
  }
  const events = normalizeEvents(lesson)
  const durationSec = estimateDuration(lesson, events)
  const beatGrid = resolveBeatGrid(lesson, durationSec)
  const bars = buildChordBars(lesson, events, beatGrid, durationSec)
  const windowSec = events.length > 0 ? Math.min(PULSE_WINDOW_SEC, durationSec) : 0
  const notes = buildFallingNotes(lesson, events, beatGrid, windowSec)
  return { events, bars, beatGrid, notes, durationSec, windowSec }
}

function shortDateLabel(date: string): string {
  const parsed = new Date(date)
  if (Number.isNaN(parsed.getTime())) return date
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function buildAccuracyTrend(
  sessions: readonly SessionJournalRow[],
  limit = 10,
): PulseAccuracyPoint[] {
  return sessions
    .map((session) => {
      const accuracy = sessionOverallAccuracy(session)
      if (accuracy == null || !Number.isFinite(accuracy)) return null
      return {
        id: session.id,
        date: session.date,
        label: shortDateLabel(session.date),
        accuracy: clamp01(accuracy),
        sortKey: Number.isNaN(new Date(session.date).getTime()) ? 0 : new Date(session.date).getTime(),
      }
    })
    .filter((point): point is PulseAccuracyPoint & { sortKey: number } => point != null)
    .sort((a, b) => a.sortKey - b.sortKey)
    .slice(-Math.max(1, limit))
    .map(({ sortKey: _sortKey, ...point }) => point)
}

export function qualityColumnForChord(chord: string): ChordQualityColumn | null {
  const parsed = parseChordSymbol(chord)
  if (!parsed) return null
  const quality = parsed.quality
  if (quality === 'maj') return 'maj'
  if (quality === 'min') return 'min'
  if (quality === '7' || quality === '9' || quality === '11' || quality === '13') return '7'
  if (quality.startsWith('7')) return '7'
  if (quality === 'maj7' || quality === 'maj9') return 'maj7'
  if (quality === 'min7' || quality === 'min9') return 'min7'
  return 'other'
}

export function classifyChordCell(
  chord: string,
): { rootPc: number; quality: ChordQualityColumn } | null {
  const parsed = parseChordSymbol(chord)
  if (!parsed) return null
  const rootPc = NOTE_TO_PITCH_CLASS[parsed.root]
  const quality = qualityColumnForChord(chord)
  if (rootPc == null || quality == null) return null
  return { rootPc, quality }
}

function chordFromFeedback(row: UserFeedbackRow): string | null {
  if (row.feedback_type !== 'chord_correction' && row.feedback_type !== 'wrong_chord') return null
  const corrected = parseFeedbackValues(row.corrected_value)?.chord
  if (typeof corrected === 'string' && corrected.trim()) return corrected.trim()
  const original = parseFeedbackValues(row.original_value)?.chord
  if (typeof original === 'string' && original.trim()) return original.trim()
  return null
}

interface MasteryAccumulator {
  practiceCount: number
  accuracySum: number
  accuracyCount: number
  correctionCount: number
}

export function buildChordMastery(
  sessionLessons: readonly SessionLessonPair[],
  feedback: readonly UserFeedbackRow[],
): ChordMasteryHeatmap {
  const buckets = new Map<string, MasteryAccumulator>()

  const bucketFor = (rootPc: number, quality: ChordQualityColumn): MasteryAccumulator => {
    const key = `${rootPc}:${quality}`
    const existing = buckets.get(key)
    if (existing) return existing
    const created: MasteryAccumulator = {
      practiceCount: 0,
      accuracySum: 0,
      accuracyCount: 0,
      correctionCount: 0,
    }
    buckets.set(key, created)
    return created
  }

  for (const pair of sessionLessons) {
    if (!pair.lesson) continue
    const events = normalizeEvents(pair.lesson)
    if (events.length === 0) continue
    const accuracy = sessionOverallAccuracy(pair.session)
    for (const event of events) {
      const cell = classifyChordCell(event.chord)
      if (!cell) continue
      const bucket = bucketFor(cell.rootPc, cell.quality)
      bucket.practiceCount += 1
      if (accuracy != null && Number.isFinite(accuracy)) {
        bucket.accuracySum += clamp01(accuracy)
        bucket.accuracyCount += 1
      }
    }
  }

  for (const row of feedback) {
    const chord = chordFromFeedback(row)
    if (!chord) continue
    const cell = classifyChordCell(chord)
    if (!cell) continue
    bucketFor(cell.rootPc, cell.quality).correctionCount += 1
  }

  const cells: ChordMasteryCell[] = []
  for (let rootPc = 0; rootPc < PULSE_ROOTS.length; rootPc += 1) {
    for (const column of CHORD_QUALITY_COLUMNS) {
      const accumulator = buckets.get(`${rootPc}:${column.id}`)
      const practiceCount = accumulator?.practiceCount ?? 0
      const correctionCount = accumulator?.correctionCount ?? 0
      const base = accumulator && accumulator.accuracyCount > 0
        ? accumulator.accuracySum / accumulator.accuracyCount
        : null
      const penalty = Math.min(0.6, correctionCount * 0.12)
      const mastery =
        base != null
          ? clamp01(base - penalty)
          : correctionCount > 0
            ? clamp01(0.55 - penalty)
            : null
      cells.push({
        rootPc,
        rootLabel: PULSE_ROOTS[rootPc] ?? 'C',
        quality: column.id,
        qualityLabel: column.label,
        practiceCount,
        correctionCount,
        mastery,
      })
    }
  }

  return {
    cells,
    populatedCount: cells.filter((cell) => cell.mastery != null).length,
    sessionCount: sessionLessons.length,
  }
}
