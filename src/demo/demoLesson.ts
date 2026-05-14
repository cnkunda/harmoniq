import { JAM_REFERENCE_TAB_GP5_BASE64 } from '@/src/jam/jamReferenceTabGp5Base64'
import type { LessonJSON } from '@/src/types'

import { DEMO_LESSON_JOB_ID } from './constants'

const BPM = 90
const BEAT_DURATION = 60 / BPM
const BEATS_PER_BAR = 4
const BAR_DURATION = BEAT_DURATION * BEATS_PER_BAR
const BAR_COUNT = 11

function fmt(v: number, decimals = 3): number {
  return +v.toFixed(decimals)
}

const BAR_TIMESTAMPS: number[] = Array.from({ length: BAR_COUNT }, (_, i) => fmt(i * BAR_DURATION))

const BEAT_GRID: number[] = Array.from({ length: BAR_COUNT * BEATS_PER_BAR }, (_, i) => {
  const barIdx = Math.floor(i / BEATS_PER_BAR)
  const beatInBar = i % BEATS_PER_BAR
  return fmt(barIdx * BAR_DURATION + beatInBar * BEAT_DURATION)
})

const CHORD_EVENTS: Array<{ timestamp: number; chord: string; confidence: number }> = [
  { timestamp: fmt(0), chord: 'G', confidence: 0.92 },
  { timestamp: fmt(2 * BAR_DURATION), chord: 'C', confidence: 0.90 },
  { timestamp: fmt(4 * BAR_DURATION), chord: 'G', confidence: 0.91 },
  { timestamp: fmt(6 * BAR_DURATION), chord: 'D', confidence: 0.89 },
  { timestamp: fmt(8 * BAR_DURATION), chord: 'G', confidence: 0.92 },
  { timestamp: fmt(10 * BAR_DURATION), chord: 'C', confidence: 0.88 },
]

type SoloNote = { start_time: number; duration: number; pitch: number; velocity: number }

function buildSoloNotes(): SoloNote[] {
  const phrases: SoloNote[][] = [
    // Phrase 1 — bars 1-2 (G)
    [
      { start_time: 0.5, duration: 0.3, pitch: 71, velocity: 85 },
      { start_time: 1.0, duration: 0.25, pitch: 74, velocity: 80 },
      { start_time: 1.5, duration: 0.2, pitch: 71, velocity: 75 },
      { start_time: 2.0, duration: 0.4, pitch: 67, velocity: 90 },
      { start_time: 3.0, duration: 0.3, pitch: 69, velocity: 80 },
      { start_time: 3.5, duration: 0.2, pitch: 71, velocity: 85 },
      { start_time: 4.0, duration: 0.5, pitch: 67, velocity: 88 },
    ],
    // Phrase 2 — bars 3-4 (C)
    [
      { start_time: 5.8, duration: 0.3, pitch: 76, velocity: 82 },
      { start_time: 6.3, duration: 0.25, pitch: 74, velocity: 78 },
      { start_time: 6.8, duration: 0.2, pitch: 72, velocity: 85 },
      { start_time: 7.5, duration: 0.35, pitch: 69, velocity: 80 },
      { start_time: 8.5, duration: 0.3, pitch: 67, velocity: 85 },
      { start_time: 9.0, duration: 0.2, pitch: 71, velocity: 82 },
      { start_time: 9.5, duration: 0.4, pitch: 67, velocity: 86 },
    ],
    // Phrase 3 — bars 5-6 (G)
    [
      { start_time: 11.0, duration: 0.3, pitch: 74, velocity: 88 },
      { start_time: 11.5, duration: 0.2, pitch: 71, velocity: 82 },
      { start_time: 12.0, duration: 0.4, pitch: 67, velocity: 85 },
      { start_time: 13.0, duration: 0.3, pitch: 69, velocity: 80 },
      { start_time: 13.5, duration: 0.2, pitch: 67, velocity: 75 },
      { start_time: 14.0, duration: 0.25, pitch: 71, velocity: 84 },
      { start_time: 14.5, duration: 0.3, pitch: 74, velocity: 88 },
      { start_time: 15.0, duration: 0.5, pitch: 67, velocity: 90 },
    ],
    // Phrase 4 — bars 7-8 (D)
    [
      { start_time: 16.5, duration: 0.3, pitch: 69, velocity: 82 },
      { start_time: 17.0, duration: 0.25, pitch: 67, velocity: 78 },
      { start_time: 17.5, duration: 0.2, pitch: 71, velocity: 85 },
      { start_time: 18.0, duration: 0.3, pitch: 74, velocity: 88 },
      { start_time: 19.0, duration: 0.3, pitch: 78, velocity: 90 },
      { start_time: 19.5, duration: 0.2, pitch: 76, velocity: 85 },
      { start_time: 20.0, duration: 0.4, pitch: 74, velocity: 82 },
    ],
    // Phrase 5 — bars 9-11 (G - C)
    [
      { start_time: 21.8, duration: 0.3, pitch: 71, velocity: 85 },
      { start_time: 22.3, duration: 0.2, pitch: 67, velocity: 80 },
      { start_time: 23.0, duration: 0.3, pitch: 69, velocity: 82 },
      { start_time: 23.5, duration: 0.2, pitch: 71, velocity: 85 },
      { start_time: 24.0, duration: 0.35, pitch: 74, velocity: 88 },
      { start_time: 25.0, duration: 0.3, pitch: 67, velocity: 86 },
      { start_time: 25.5, duration: 0.2, pitch: 76, velocity: 84 },
      { start_time: 26.0, duration: 0.25, pitch: 74, velocity: 80 },
      { start_time: 27.0, duration: 0.3, pitch: 71, velocity: 82 },
      { start_time: 27.5, duration: 0.2, pitch: 67, velocity: 78 },
      { start_time: 28.0, duration: 0.6, pitch: 67, velocity: 92 },
    ],
  ]
  return phrases.flat()
}

function sectionCoachNote(sectionIndex: number): string {
  const notes = [
    'Listen to how the guitar locks with the bass and drums — reggae\'s "one drop" feel lives in the space between the backbeat.',
    'Notice the chord change and how the solo line weaves through the harmony — pickups and pentatonic phrases over the IV chord.',
    'The turnaround builds tension back to the I — the V chord creates forward motion that resolves when the pattern restarts.',
  ]
  return notes[sectionIndex] ?? notes[0]!
}

/** GP5-backed practice lesson using bundled stems only (offline). */
export function getDemoLesson(): LessonJSON {
  return {
    job_id: DEMO_LESSON_JOB_ID,
    song_title: 'Reggae pocket (demo)',
    artist: 'Harmoniq',
    style_label: 'reggae',
    key: 'G major',
    key_confidence: 0.95,
    tempo: BPM,
    tempo_confidence: 0.93,
    transcription_confidence: 0.85,
    analysis_audio_role: 'guitar_stem',
    beat_align_offset_sec: 0,
    stems: {
      guitar: 'bundled://demo/reggae-guitar',
      bass: 'bundled://demo/reggae-bass',
      drums: 'bundled://demo/reggae-drums',
      vocals: 'bundled://demo/reggae-vocals',
      piano: 'bundled://demo/reggae-piano',
      other: 'bundled://demo/reggae-other',
    },
    beat_grid: BEAT_GRID,
    bar_timestamps: BAR_TIMESTAMPS,
    chord_timeline: { events: CHORD_EVENTS },
    solo_notes: { notes: buildSoloNotes() },
    sections: [
      {
        label: 'Main Riff',
        start_time_seconds: 0,
        confidence: 0.88,
        coach_note: sectionCoachNote(0),
        coach_explanation: '',
        tab_full_gp5_base64: JAM_REFERENCE_TAB_GP5_BASE64,
      },
      {
        label: 'Fill',
        start_time_seconds: fmt(BAR_DURATION * 4),
        confidence: 0.86,
        coach_note: sectionCoachNote(1),
        coach_explanation: '',
        tab_full_gp5_base64: JAM_REFERENCE_TAB_GP5_BASE64,
      },
      {
        label: 'Turnaround',
        start_time_seconds: fmt(BAR_DURATION * 7),
        confidence: 0.87,
        coach_note: sectionCoachNote(2),
        coach_explanation: '',
        tab_full_gp5_base64: JAM_REFERENCE_TAB_GP5_BASE64,
      },
    ],
  }
}
