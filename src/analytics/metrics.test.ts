import { describe, expect, it } from 'vitest'

import { computeEngagementMetrics } from '@/src/analytics/metrics'
import type { AnalyticsEventRow, UserFeedbackStats } from '@/src/db/types'

const NOW = new Date(2026, 9, 21, 12, 0, 0)

const EMPTY_FEEDBACK: UserFeedbackStats = {
  total: 0,
  chord_corrections: 0,
  note_corrections: 0,
  wrong_chords: 0,
  most_corrected_chords: [],
}

function row(
  id: string,
  eventType: AnalyticsEventRow['event_type'],
  payload: unknown,
  timestamp: Date,
): AnalyticsEventRow {
  return {
    id,
    user_id: 'user-1',
    event_type: eventType,
    payload_json: JSON.stringify(payload),
    timestamp: timestamp.toISOString(),
  }
}

function rawRow(
  id: string,
  eventType: AnalyticsEventRow['event_type'],
  payloadJson: string,
  timestamp: Date | string,
): AnalyticsEventRow {
  return {
    id,
    user_id: 'user-1',
    event_type: eventType,
    payload_json: payloadJson,
    timestamp: typeof timestamp === 'string' ? timestamp : timestamp.toISOString(),
  }
}

describe('computeEngagementMetrics', () => {
  it('returns zeroed metrics for an empty event list', () => {
    const metrics = computeEngagementMetrics([], EMPTY_FEEDBACK, NOW)

    expect(metrics.totalSessions).toBe(0)
    expect(metrics.completedSessions).toBe(0)
    expect(metrics.completionRate).toBe(0)
    expect(metrics.averageSessionLengthSec).toBe(0)
    expect(metrics.totalPlayAlongSec).toBe(0)
    expect(metrics.averagePlayAlongSec).toBe(0)
    expect(metrics.sessionsWithoutSongTitle).toBe(0)
    expect(metrics.sessionsThisWeek).toBe(0)
    expect(metrics.sessionsByDay).toHaveLength(7)
  })

  it('counts sessions, completions, and average completed duration', () => {
    const events = [
      row('a', 'session_start', { song_title: 'Gravity', step: 'tune' }, new Date(2026, 9, 21, 9)),
      row(
        'b',
        'session_complete',
        { song_title: 'Gravity', duration_sec: 300, final_step: 'review', started_at: '' },
        new Date(2026, 9, 21, 9, 5),
      ),
      row('c', 'session_start', { song_title: 'Gravity', step: 'tune' }, new Date(2026, 9, 20, 9)),
      row(
        'd',
        'session_complete',
        { song_title: 'Gravity', duration_sec: 180, final_step: 'review', started_at: '' },
        new Date(2026, 9, 20, 9, 3),
      ),
      row('e', 'session_start', { song_title: 'Gravity', step: 'tune' }, new Date(2026, 9, 19, 9)),
    ]

    const metrics = computeEngagementMetrics(events, EMPTY_FEEDBACK, NOW)

    expect(metrics.totalSessions).toBe(3)
    expect(metrics.completedSessions).toBe(2)
    expect(metrics.completionRate).toBeCloseTo(2 / 3)
    expect(metrics.averageSessionLengthSec).toBe(240)
    expect(metrics.mostPracticedSongs).toEqual([{ song_title: 'Gravity', count: 3 }])
    expect(metrics.sessionsThisWeek).toBe(3)
  })

  it('ignores blank song titles and reports how many sessions lacked one', () => {
    const events = [
      row('a', 'session_start', { song_title: '  ', step: 'tune' }, new Date(2026, 9, 21, 9)),
      row('b', 'session_start', { song_title: null, step: 'tune' }, new Date(2026, 9, 21, 10)),
      row('c', 'session_start', { song_title: 'Gravity', step: 'tune' }, new Date(2026, 9, 21, 11)),
    ]

    const metrics = computeEngagementMetrics(events, EMPTY_FEEDBACK, NOW)

    expect(metrics.totalSessions).toBe(3)
    expect(metrics.sessionsWithoutSongTitle).toBe(2)
    expect(metrics.mostPracticedSongs).toEqual([{ song_title: 'Gravity', count: 1 }])
  })

  it('keeps only the five most-practiced songs, sorted by count then title', () => {
    const events = [
      'E',
      'D',
      'C',
      'B',
      'A',
      'A',
      'A',
      'B',
      'B',
      'C',
      'C',
      'D',
      'D',
      'E',
      'E',
    ].map((title, index) =>
      row(`song-${index}`, 'session_start', { song_title: title, step: 'tune' }, new Date(2026, 9, 21, 9)),
    )

    const metrics = computeEngagementMetrics(events, EMPTY_FEEDBACK, NOW)

    expect(metrics.mostPracticedSongs.map((song) => song.song_title)).toEqual(['A', 'B', 'C', 'D', 'E'])
    expect(metrics.mostPracticedSongs[0]).toEqual({ song_title: 'A', count: 3 })
  })

  it('aggregates play-along durations and averages only completed takes', () => {
    const events = [
      row('a', 'play_along_start', { tempo_bpm: 90 }, new Date(2026, 9, 21, 9)),
      row(
        'b',
        'play_along_complete',
        { duration_sec: 42, tempo_bpm: 90, reason: 'done' },
        new Date(2026, 9, 21, 9, 1),
      ),
      row(
        'c',
        'play_along_complete',
        { duration_sec: 18, tempo_bpm: 90, reason: 'silence' },
        new Date(2026, 9, 21, 9, 2),
      ),
      row('d', 'play_along_discard', { duration_sec: 5 }, new Date(2026, 9, 21, 9, 3)),
    ]

    const metrics = computeEngagementMetrics(events, EMPTY_FEEDBACK, NOW)

    expect(metrics.totalPlayAlongSec).toBe(60)
    expect(metrics.averagePlayAlongSec).toBe(30)
  })

  it('only buckets the rolling 7 local days and excludes older sessions', () => {
    const events = [
      row('old', 'session_start', { song_title: 'Old', step: 'tune' }, new Date(2026, 9, 14, 23, 59)),
      row('first', 'session_start', { song_title: 'First', step: 'tune' }, new Date(2026, 9, 15, 0, 0)),
      row('last', 'session_start', { song_title: 'Last', step: 'tune' }, new Date(2026, 9, 21, 23, 59)),
    ]

    const metrics = computeEngagementMetrics(events, EMPTY_FEEDBACK, NOW)

    expect(metrics.sessionsThisWeek).toBe(2)
    expect(metrics.sessionsByDay[0]).toEqual({ date: '2026-10-15', count: 1 })
    expect(metrics.sessionsByDay[6]).toEqual({ date: '2026-10-21', count: 1 })
    expect(metrics.sessionsByDay.reduce((sum, day) => sum + day.count, 0)).toBe(2)
  })

  it('ignores malformed payloads and invalid timestamps', () => {
    const events = [
      rawRow('bad-json', 'session_start', '{not json', new Date(2026, 9, 21, 9)),
      rawRow('array-json', 'session_start', '[]', new Date(2026, 9, 21, 9)),
      rawRow(
        'bad-time',
        'session_start',
        JSON.stringify({ song_title: 'Gravity', step: 'tune' }),
        'not-a-date',
      ),
      row(
        'negative-duration',
        'session_complete',
        { song_title: 'Gravity', duration_sec: -10, final_step: 'review', started_at: '' },
        new Date(2026, 9, 21, 9),
      ),
    ]

    const metrics = computeEngagementMetrics(events, EMPTY_FEEDBACK, NOW)

    expect(metrics.totalSessions).toBe(3)
    expect(metrics.sessionsWithoutSongTitle).toBe(2)
    expect(metrics.mostPracticedSongs).toEqual([{ song_title: 'Gravity', count: 1 }])
    expect(metrics.completedSessions).toBe(1)
    expect(metrics.averageSessionLengthSec).toBe(0)
    expect(metrics.sessionsThisWeek).toBe(2)
  })

  it('passes the top corrected chords through from feedback stats', () => {
    const feedback: UserFeedbackStats = {
      total: 3,
      chord_corrections: 2,
      note_corrections: 1,
      wrong_chords: 2,
      most_corrected_chords: [
        { chord: 'Gmaj7', count: 2 },
        { chord: 'D', count: 1 },
      ],
    }

    const metrics = computeEngagementMetrics([], feedback, NOW)

    expect(metrics.mostCorrectedChords).toEqual(feedback.most_corrected_chords)
    expect(metrics.mostCorrectedChords).not.toBe(feedback.most_corrected_chords)
  })
})
