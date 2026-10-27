import { describe, expect, it } from 'vitest'

import type { LessonListRow, SessionJournalRow } from '@/src/db/types'
import { buildSongPickerSources } from './songPickerItems'

const DAY_MS = 24 * 60 * 60 * 1000
const NOW = new Date('2026-10-26T12:00:00.000Z').getTime()

function lesson(jobId: string, title: string, analyzedDaysAgo: number, sectionCount = 4): LessonListRow {
  return {
    job_id: jobId,
    song_title: title,
    artist: 'Artist',
    analyzed_at: new Date(NOW - analyzedDaysAgo * DAY_MS).toISOString(),
    section_count: sectionCount,
  }
}

function session(
  id: string,
  title: string,
  playedDaysAgo: number,
  jobId: string | null = null,
): SessionJournalRow {
  return {
    id,
    song_title: title,
    artist: 'Artist',
    section_label: 'Verse',
    date: new Date(NOW - playedDaysAgo * DAY_MS).toISOString(),
    coach_review: null,
    pitch_accuracy: 0.64,
    phrasing_score: 0.56,
    nodes_targeted: ['pitch_accuracy'],
    has_review_snapshot: false,
    waveform_user_path: null,
    waveform_ref_path: null,
    job_id: jobId,
  }
}

describe('buildSongPickerSources', () => {
  it('floats the suggested song first even when it is older', () => {
    const result = buildSongPickerSources({
      lessons: [lesson('a', 'Blackbird', 20), lesson('b', 'Hotel California', 1)],
      sessions: [session('s1', 'Blackbird', 0, 'a')],
      suggestedTitle: 'Blackbird',
    })
    expect(result.map((song) => song.jobId)).toEqual(['a', 'b'])
    expect(result[0]?.lastPlayedDate).not.toBeNull()
  })

  it('orders by last played, then analyzed date', () => {
    const result = buildSongPickerSources({
      lessons: [
        lesson('a', 'Older', 10),
        lesson('b', 'Middle', 5),
        lesson('c', 'Newest', 1),
      ],
      sessions: [session('s1', 'Older', 0, 'a')],
      suggestedTitle: null,
      limit: 3,
    })
    expect(result.map((song) => song.jobId)).toEqual(['a', 'c', 'b'])
  })

  it('matches sessions by title when job_id is absent and computes accuracy', () => {
    const result = buildSongPickerSources({
      lessons: [lesson('a', 'Blackbird', 10)],
      sessions: [session('s1', '  blackbird ', 2)],
      suggestedTitle: null,
    })
    expect(result[0]?.lastPlayedDate).not.toBeNull()
    expect(result[0]?.accuracy).toBeCloseTo(0.6)
  })

  it('respects the limit', () => {
    expect(
      buildSongPickerSources({
        lessons: [lesson('a', 'A', 1), lesson('b', 'B', 2), lesson('c', 'C', 3)],
        sessions: [],
        suggestedTitle: null,
        limit: 0,
      }),
    ).toEqual([])
  })
})
