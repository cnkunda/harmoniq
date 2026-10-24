import { describe, expect, it } from 'vitest'

import type { SessionJournalRow, UserFeedbackRow } from '@/src/db/types'
import type { LessonJSON } from '@/src/types'

import {
  buildAccuracyTrend,
  buildChordMastery,
  buildPulseStageData,
  classifyChordCell,
} from './pulseData'

function sessionRow(
  id: string,
  date: string,
  pitch: number | null,
  phrasing: number | null = null,
): SessionJournalRow {
  return {
    id,
    song_title: null,
    artist: null,
    section_label: null,
    date,
    coach_review: null,
    pitch_accuracy: pitch,
    phrasing_score: phrasing,
    nodes_targeted: [],
    has_review_snapshot: false,
    waveform_user_path: null,
    waveform_ref_path: null,
  }
}

function feedbackRow(
  type: UserFeedbackRow['feedback_type'],
  original: Record<string, unknown>,
  corrected: Record<string, unknown> | null,
  index = 0,
): UserFeedbackRow {
  return {
    id: `f-${index}`,
    job_id: 'job-1',
    song_id: 'song-1',
    user_id: 'user-1',
    timestamp: '2026-04-01T10:00:00.000Z',
    feedback_type: type,
    event_index: index,
    original_value: JSON.stringify(original),
    corrected_value: corrected == null ? null : JSON.stringify(corrected),
    reason: null,
  }
}

function lessonFixture(): LessonJSON {
  return {
    job_id: 'job-1',
    tempo: 120,
    bar_timestamps: [0, 2, 4],
    chord_timeline: {
      events: [
        { timestamp: 0, chord: 'G:maj', confidence: 0.9 },
        { timestamp: 2, chord: 'C:maj', confidence: 0.8 },
      ],
    },
    solo_notes: {
      notes: [
        { start_time: 1, duration: 0.5, pitch: 67 },
        { start_time: 2.5, duration: 0.5, pitch: 72 },
        { start_time: 3.5, duration: 0.5, pitch: 71 },
      ],
    },
  }
}

describe('buildAccuracyTrend', () => {
  it('keeps scored sessions in chronological order and respects the limit', () => {
    const sessions = [
      sessionRow('s3', '2026-03-03T10:00:00.000Z', 0.7),
      sessionRow('s1', '2026-03-01T10:00:00.000Z', 0.5, 0.7),
      sessionRow('s2', '2026-03-02T10:00:00.000Z', null),
      sessionRow('s4', '2026-03-04T10:00:00.000Z', 0.9),
    ]
    expect(buildAccuracyTrend(sessions, 2).map((p) => p.id)).toEqual(['s3', 's4'])
  })

  it('blends pitch and phrasing and ignores unscored sessions', () => {
    const [point] = buildAccuracyTrend(
      [sessionRow('s1', '2026-03-01T10:00:00.000Z', 0.5, 0.7)],
      10,
    )
    expect(point?.accuracy).toBeCloseTo(0.6)
  })
})

describe('buildPulseStageData', () => {
  it('builds bars, carries chords forward, and classifies solo notes', () => {
    const stage = buildPulseStageData(lessonFixture())
    expect(stage.events).toHaveLength(2)
    expect(stage.bars.map((bar) => bar.display)).toEqual(['G', 'C', 'C'])
    expect(stage.beatGrid.bpm).toBe(120)
    expect(stage.notes.map((note) => note.isChordTone)).toEqual([true, true, false])
  })
})

describe('classifyChordCell', () => {
  it('maps roots and chord qualities into the heatmap grid', () => {
    expect(classifyChordCell('C:maj')).toEqual({ rootPc: 0, quality: 'maj' })
    expect(classifyChordCell('Bb:min7')).toEqual({ rootPc: 10, quality: 'min7' })
    expect(classifyChordCell('F#:7')).toEqual({ rootPc: 6, quality: '7' })
    expect(classifyChordCell('N')).toBeNull()
  })
})

describe('buildChordMastery', () => {
  it('aggregates session accuracy and penalizes chord corrections', () => {
    const heatmap = buildChordMastery(
      [{ session: sessionRow('s1', '2026-03-01T10:00:00.000Z', 0.8), lesson: lessonFixture() }],
      [feedbackRow('chord_correction', { chord: 'C:maj' }, { chord: 'C:maj' })],
    )

    const gMajor = heatmap.cells.find((cell) => cell.rootPc === 7 && cell.quality === 'maj')
    const cMajor = heatmap.cells.find((cell) => cell.rootPc === 0 && cell.quality === 'maj')
    expect(gMajor?.practiceCount).toBe(1)
    expect(gMajor?.mastery).toBeCloseTo(0.8)
    expect(cMajor?.practiceCount).toBe(1)
    expect(cMajor?.correctionCount).toBe(1)
    expect(cMajor?.mastery).toBeCloseTo(0.68)
    expect(heatmap.populatedCount).toBe(2)
  })

  it('leaves cells empty when there is neither practice nor feedback', () => {
    const heatmap = buildChordMastery([], [])
    expect(heatmap.populatedCount).toBe(0)
    expect(heatmap.cells).toHaveLength(72)
    expect(heatmap.cells.every((cell) => cell.mastery == null)).toBe(true)
  })
})
