import { describe, expect, it } from 'vitest'

import {
  MENTOR_MIN_HISTORY_DAYS,
  buildMentorTrajectory,
  type MentorTrajectoryInput,
} from './mentorTrajectory'
import type {
  PracticePlanCompletionRow,
  SessionArchiveRow,
  SkillNodeRow,
  UserFeedbackRow,
} from '@/src/db/types'

const NOW = new Date('2026-10-26T12:00:00.000Z')

function scoreSnapshot(nodeScores: Record<string, number>, pitch = 0.6): string {
  return JSON.stringify({
    pitch_accuracy: pitch,
    note_duration_deltas: [],
    phrasing_score: 0.55,
    bend_pitch_error_cents: 0,
    rushing_score: 0.3,
    node_scores: nodeScores,
    waveform_comparison: { user_wav_base64: '', reference_wav_base64: '' },
  })
}

function session(
  id: string,
  date: string,
  nodeScores: Record<string, number> | null,
  overrides: Partial<SessionArchiveRow> = {},
): SessionArchiveRow {
  return {
    id,
    song_title: 'Blue in Green',
    artist: 'Miles Davis',
    section_label: 'Verse',
    date,
    coach_review: null,
    pitch_accuracy: nodeScores ? 0.6 : null,
    phrasing_score: nodeScores ? 0.55 : null,
    nodes_targeted: ['pitch_accuracy', 'phrasing', 'timing'],
    has_review_snapshot: nodeScores != null,
    waveform_user_path: null,
    waveform_ref_path: null,
    review_snapshot: nodeScores ? scoreSnapshot(nodeScores) : null,
    ...overrides,
  }
}

function completion(id: string, completedAt: string, planJson: string): PracticePlanCompletionRow {
  return { id, completed_at: completedAt, plan_json: planJson }
}

function skillNode(id: string, label: string, score: number): SkillNodeRow {
  return {
    id,
    label,
    score,
    sessions_count: 4,
    last_session_date: '2026-10-20T00:00:00.000Z',
    easiness_factor: 2.5,
    interval_days: 3,
    next_review_date: '2026-10-30',
    sm2_repetitions: 2,
  }
}

function feedbackRow(id: string, timestamp: string, original: string): UserFeedbackRow {
  return {
    id,
    job_id: 'job-1',
    song_id: 'song-1',
    user_id: 'user-1',
    timestamp,
    feedback_type: 'wrong_chord',
    event_index: 0,
    original_value: original,
    corrected_value: 'C7',
    reason: null,
  }
}

function baseInput(overrides: Partial<MentorTrajectoryInput> = {}): MentorTrajectoryInput {
  return {
    mode: 'plan',
    now: NOW,
    sessions: [],
    jams: [],
    completions: [],
    activePlan: null,
    skillNodes: [],
    feedback: [],
    dna: null,
    taste: null,
    learningContext: null,
    librarySongs: [],
    tasteSongCandidates: [],
    ...overrides,
  }
}

const PLAN_JSON = JSON.stringify({
  plan_id: 'plan-1',
  slots: [
    { slot_id: 's1', slot_type: 'warmup', title: 'Warmup', target_skill: 'timing' },
    { slot_id: 's2', slot_type: 'technique', title: 'Bends', target_skill: 'bend_accuracy' },
    { slot_id: 's3', slot_type: 'song_section', title: 'Verse', target_skill: 'timing' },
    { slot_id: 's4', slot_type: 'free_jam', title: 'Jam', target_skill: null },
  ],
  slot_results: [
    { slot_id: 's1', accuracy: 0.5, completion: true },
    { slot_id: 's2', accuracy: 0.7, completion: true },
  ],
  adaptation_log: [
    { slot_id: 's2', action: 'insert_remediation', reason: 'timing slipped' },
    { slot_id: 's3', action: 'skip_easier', reason: 'already strong' },
  ],
  total_duration_seconds: 1200,
})

describe('buildMentorTrajectory', () => {
  it('marks a 45-day history eligible and builds trajectory data', () => {
    const sessions = [
      session('s1', '2026-09-12T10:00:00.000Z', { pitch_accuracy: 0.4, phrasing: 0.38, timing: 0.35 }),
      session('s2', '2026-09-18T10:00:00.000Z', { pitch_accuracy: 0.42, phrasing: 0.4, timing: 0.38 }),
      session('s3', '2026-09-27T10:00:00.000Z', { pitch_accuracy: 0.45, phrasing: 0.44, timing: 0.42 }),
      session('s4', '2026-10-05T10:00:00.000Z', { pitch_accuracy: 0.58, phrasing: 0.56, timing: 0.52 }),
      session('s5', '2026-10-15T10:00:00.000Z', { pitch_accuracy: 0.62, phrasing: 0.6, timing: 0.58 }),
      session('s6', '2026-10-25T10:00:00.000Z', { pitch_accuracy: 0.66, phrasing: 0.63, timing: 0.61 }),
    ]
    const result = buildMentorTrajectory(
      baseInput({
        sessions,
        completions: [completion('c1', '2026-10-20T10:00:00.000Z', PLAN_JSON)],
        skillNodes: [
          skillNode('pitch_accuracy', 'Pitch accuracy', 0.66),
          skillNode('timing', 'Timing', 0.35),
          skillNode('bend_accuracy', 'Bend accuracy', 0.42),
        ],
        feedback: [
          feedbackRow('f1', '2026-10-01T10:00:00.000Z', 'G7'),
          feedbackRow('f2', '2026-10-02T10:00:00.000Z', 'G7'),
          feedbackRow('f3', '2026-10-03T10:00:00.000Z', 'Am7'),
        ],
        tasteSongCandidates: ['Autumn Leaves'],
      }),
    )

    expect(result.eligible).toBe(true)
    expect(result.historyDays).toBeGreaterThanOrEqual(MENTOR_MIN_HISTORY_DAYS)
    expect(result.payload.history.session_count).toBe(6)
    expect(result.payload.history.correction_count).toBe(3)
    expect(result.payload.accuracy_points).toHaveLength(6)
    expect(result.payload.skill_deltas.map((delta) => delta.id)).toEqual(['pitch_accuracy', 'phrasing', 'timing'])
    for (const delta of result.payload.skill_deltas) {
      expect(delta.delta).toBeGreaterThan(0)
    }
    expect(result.payload.weak_nodes[0]?.id).toBe('timing')
    expect(result.payload.corrections.most_corrected_chords[0]).toEqual({ chord: 'G7', count: 2 })
    expect(result.payload.plan?.slot_count).toBe(4)
    expect(result.payload.plan?.slot_types).toEqual(['warmup', 'technique', 'song_section', 'free_jam'])
    expect(result.payload.plan?.target_skills.sort()).toEqual(['bend_accuracy', 'timing'])
    expect(result.payload.plan?.remediation_count).toBe(1)
    expect(result.payload.plan?.skip_count).toBe(1)
    expect(result.payload.plan?.avg_slot_accuracy).toBeCloseTo(0.6)
    expect(result.payload.taste_song_candidates).toEqual(['Autumn Leaves'])
  })

  it('is ineligible before 30 days of history', () => {
    const sessions = [
      session('s1', '2026-10-16T10:00:00.000Z', { pitch_accuracy: 0.4 }),
      session('s2', '2026-10-20T10:00:00.000Z', { pitch_accuracy: 0.45 }),
      session('s3', '2026-10-24T10:00:00.000Z', { pitch_accuracy: 0.5 }),
    ]
    const result = buildMentorTrajectory(baseInput({ sessions }))
    expect(result.eligible).toBe(false)
    expect(result.evidenceCount).toBe(3)
    expect(result.payload.history.confidence).toBe('low')
  })

  it('handles sessions without review snapshots or score data', () => {
    const sessions = [
      session('s1', '2026-09-12T10:00:00.000Z', null),
      session('s2', '2026-09-20T10:00:00.000Z', null),
      session('s3', '2026-10-25T10:00:00.000Z', null),
    ]
    const result = buildMentorTrajectory(baseInput({ sessions }))
    expect(result.eligible).toBe(true)
    expect(result.payload.accuracy_points).toEqual([])
    expect(result.payload.skill_deltas).toEqual([])
    expect(result.payload.corrections.total).toBe(0)
  })
})
