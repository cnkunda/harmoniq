import { describe, expect, it } from 'vitest'

import type { UserFeedbackRow } from '@/src/db/types'
import {
  buildFeedbackStats,
  buildLocalFeedbackExport,
  dedupeFeedbackRows,
  findSoloNoteIndexForSelection,
  parseFeedbackValues,
  summarizeFeedbackRows,
} from '@/src/utils/feedback'

function row(overrides: Partial<UserFeedbackRow>): UserFeedbackRow {
  return {
    id: 'row-1',
    job_id: 'job-1',
    song_id: 'job-1',
    user_id: 'user-1',
    timestamp: '2026-01-01T00:00:00.000Z',
    feedback_type: 'chord_correction',
    event_index: 0,
    original_value: JSON.stringify({ chord: 'C' }),
    corrected_value: JSON.stringify({ chord: 'Cmaj7' }),
    reason: null,
    ...overrides,
  }
}

describe('feedback helpers', () => {
  it('parses only object JSON values', () => {
    expect(parseFeedbackValues('{"chord":"C"}')).toEqual({ chord: 'C' })
    expect(parseFeedbackValues('[]')).toBeNull()
    expect(parseFeedbackValues('not-json')).toBeNull()
    expect(parseFeedbackValues(null)).toBeNull()
  })

  it('dedupes latest record per job, type, and event', () => {
    const older = row({ id: 'older', timestamp: '2026-01-01T00:00:00.000Z' })
    const newer = row({ id: 'newer', timestamp: '2026-01-02T00:00:00.000Z' })
    const note = row({
      id: 'note',
      feedback_type: 'note_correction',
      event_index: 0,
      timestamp: '2026-01-03T00:00:00.000Z',
    })

    expect(dedupeFeedbackRows([older, newer, note]).map((item) => item.id)).toEqual(['note', 'newer'])
  })

  it('summarizes feedback counts by type', () => {
    const rows = [
      row({ id: '1' }),
      row({ id: '2', feedback_type: 'note_correction', event_index: 1 }),
      row({ id: '3', feedback_type: 'wrong_chord', event_index: 2, corrected_value: null }),
    ]
    expect(summarizeFeedbackRows(rows)).toEqual({
      total: 3,
      chord_corrections: 1,
      note_corrections: 1,
      wrong_chords: 1,
    })
  })

  it('builds top corrected chord stats from corrected chord symbols', () => {
    const rows = [
      row({ id: '1', event_index: 0, corrected_value: JSON.stringify({ chord: 'G7' }) }),
      row({ id: '2', event_index: 1, corrected_value: JSON.stringify({ chord: 'G7' }) }),
      row({ id: '3', event_index: 2, corrected_value: JSON.stringify({ chord: 'Am' }) }),
      row({ id: '4', event_index: 3, feedback_type: 'wrong_chord', corrected_value: null }),
    ]
    expect(buildFeedbackStats(rows).most_corrected_chords).toEqual([
      { chord: 'G7', count: 2 },
      { chord: 'Am', count: 1 },
    ])
  })

  it('builds a deduped local export with parsed values', () => {
    const rows = [
      row({ id: 'older', timestamp: '2026-01-01T00:00:00.000Z' }),
      row({
        id: 'newer',
        timestamp: '2026-01-02T00:00:00.000Z',
        corrected_value: JSON.stringify({ chord: 'Dm7' }),
      }),
    ]
    const exported = buildLocalFeedbackExport(rows, 'user-1', '2026-02-01T00:00:00.000Z')
    expect(exported.exported_at).toBe('2026-02-01T00:00:00.000Z')
    expect(exported.user_id).toBe('user-1')
    expect(exported.records).toHaveLength(1)
    expect(exported.records[0]).toMatchObject({
      feedback_type: 'chord_correction',
      original: { chord: 'C' },
      corrected: { chord: 'Dm7' },
      timestamp: '2026-01-02T00:00:00.000Z',
    })
  })

  it('matches a selection to the closest solo note by pitch and time', () => {
    const notes = [
      { pitch: 64, start_time: 0.0 },
      { pitch: 67, start_time: 0.5 },
      { pitch: 67, start_time: 2.0 },
      { pitch: 69, start_time: 3.0 },
    ]
    expect(findSoloNoteIndexForSelection(notes, { midi: 67, timeSec: 1.9 })).toBe(2)
    expect(findSoloNoteIndexForSelection(notes, { midi: 67.4, timeSec: 0.1 })).toBe(1)
    expect(findSoloNoteIndexForSelection(notes, { midi: 60, timeSec: 1 })).toBe(-1)
    expect(findSoloNoteIndexForSelection(notes, { midi: null, timeSec: 1 })).toBe(-1)
    expect(findSoloNoteIndexForSelection(notes, { midi: 69 })).toBe(3)
  })
})
