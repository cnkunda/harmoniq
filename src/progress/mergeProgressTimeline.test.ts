import { describe, expect, it } from 'vitest'

import type { JamSnapshotRow, PracticePlanCompletionRow, SessionJournalRow } from '@/src/db/types'

import { mergeProgressTimeline } from './mergeProgressTimeline'

function sessionRow(id: string, date: string): SessionJournalRow {
  return {
    id,
    song_title: null,
    artist: null,
    section_label: null,
    date,
    coach_review: null,
    pitch_accuracy: null,
    phrasing_score: null,
    nodes_targeted: [],
    has_review_snapshot: false,
    waveform_user_path: null,
    waveform_ref_path: null,
  }
}

function jamRow(id: string, date: string): JamSnapshotRow {
  return {
    id,
    date,
    duration_seconds: 30,
    scale_position_map: {},
    pitch_class_weight_map: {},
    position_weight_map: {},
    inferred_scale_label: null,
    inference_confidence: null,
    track_id: null,
    track_label: null,
    track_key: null,
    track_bpm: null,
    reliability_tags: [],
    reliability_confidence: null,
    reliability_signal_quality: null,
    recurring_gestures: [],
    coach_summary: '',
    summary_bundle_json: null,
    phrases_json: null,
  }
}

function completionRow(id: string, completed_at: string): PracticePlanCompletionRow {
  return {
    id,
    completed_at,
    plan_json: '{"slots":[]}',
  }
}

describe('mergeProgressTimeline', () => {
  it('orders newest-first by ISO timestamp across kinds', () => {
    const sessions = [sessionRow('s-old', '2026-02-01T10:00:00.000Z')]
    const jams = [jamRow('j-mid', '2026-03-01T10:00:00.000Z')]
    const completions = [completionRow('p-new', '2026-04-01T10:00:00.000Z')]
    const merged = mergeProgressTimeline(sessions, jams, completions)
    expect(merged.map((i) => i.tie)).toEqual(['p-new', 'j-mid', 's-old'])
  })

  it('breaks ties by tie id (lexicographic tie-break)', () => {
    const t = '2026-05-01T12:00:00.000Z'
    const sessions = [sessionRow('sb', t), sessionRow('sa', t)]
    const merged = mergeProgressTimeline(sessions, [], [])
    expect(merged).toHaveLength(2)
    expect(merged.map((i) => i.tie)).toEqual(['sb', 'sa'])
  })
})
