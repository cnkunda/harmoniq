import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { JamSummaryBundle } from '@/src/api/jam'
import type { JamSnapshotRow } from '@/src/db/types'

vi.mock('@/src/api/jam', () => ({
  submitJamSummary: vi.fn(),
}))
vi.mock('@/src/db/client', () => ({
  getAppPref: vi.fn(),
  getAllSkillNodes: vi.fn(),
  updateJamSnapshotSummary: vi.fn(),
}))
vi.mock('@/src/api/analyze', () => ({
  buildPlayerProfileFromSkillNodes: vi.fn(),
  loadLearningContextFromPrefs: vi.fn(),
  parseTasteProfileJson: vi.fn(),
}))

import { submitJamSummary } from '@/src/api/jam'
import { getAppPref, updateJamSnapshotSummary } from '@/src/db/client'
import {
  persistJamSummary,
  requestJamSummary,
  retryJamSummary,
  runJamSummary,
} from '@/src/jam/jamSummaryRunner'

const submitMock = vi.mocked(submitJamSummary)
const getPrefMock = vi.mocked(getAppPref)
const updateMock = vi.mocked(updateJamSnapshotSummary)

function bundle(): JamSummaryBundle {
  return {
    chord: 'A minor pentatonic',
    clarity: 0.8,
    intonation_cents: {},
    timing_ms: 0,
    transition_from: null,
    transition_gap_ms: 0,
    grade: 'B',
    grade_score: 84,
    grade_breakdown: { intonation: 90 },
    phrase_feedback: [],
    weakest_phrase_index: 0,
    phrase_count: 1,
    total_notes: 4,
    avg_notes_per_second: 2,
    dominant_contour: 'mixed',
    pitch_class_distribution: {},
    vocabulary_patterns: [],
    vocabulary_diversity: 0.5,
    coach_summary: 'Solid work.',
    coach_strengths: [],
    coach_focus_areas: [],
    coach_next_step: 'Keep going.',
    persona: 'learner',
    duration_seconds: 30,
    inferred_scale_label: 'A minor pentatonic',
    inference_confidence: 'high',
  }
}

function context() {
  return {
    duration_seconds: 30,
    pitch_class_weight_map: { pc_A: 1 },
    inferred_scale_label: 'A minor pentatonic',
    inference_confidence: 'high' as const,
    track_id: 'am-blues-70',
    track_label: 'Slow blues',
    track_key: 'A minor',
    track_bpm: 70,
    phrases: [
      {
        duration_ms: 1000,
        notes_per_second: 2,
        unique_pitch_classes: 3,
        midi_span: 5,
        contour: 'rising' as const,
      },
    ],
    personaChoice: 'encouraging' as const,
    weak_areas: [],
  }
}

function jamRow(): JamSnapshotRow {
  return {
    id: 'jam-1',
    date: '2026-10-20T10:00:00.000Z',
    duration_seconds: 30,
    scale_position_map: { pc_A: 0.6 },
    pitch_class_weight_map: { pc_A: 0.6 },
    position_weight_map: {},
    inferred_scale_label: 'A minor pentatonic',
    inference_confidence: 'high',
    track_id: 'am-blues-70',
    track_label: 'A minor — slow blues shuffle',
    track_key: 'A minor',
    track_bpm: 70,
    reliability_tags: [],
    reliability_confidence: 'high',
    reliability_signal_quality: 0.9,
    recurring_gestures: [],
    coach_summary: 'Previous summary.',
    summary_bundle_json: null,
    phrases_json: JSON.stringify([
      {
        duration_ms: 1000,
        notes_per_second: 2,
        unique_pitch_classes: 3,
        midi_span: 5,
        contour: 'rising',
        note_count: 4,
        intonation_cents: 12,
        backing_start_ms: 1000,
        backing_end_ms: 2000,
      },
    ]),
    summary_status: 'failed',
  }
}

describe('jamSummaryRunner', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    submitMock.mockResolvedValue({ bundle: bundle(), coach_summary: 'Solid work.' })
    updateMock.mockResolvedValue(undefined)
    getPrefMock.mockResolvedValue('technical')
  })

  it('builds the request with persona and phrase fields', () => {
    const request = requestJamSummary({
      duration_seconds: 30,
      pitch_class_weight_map: { pc_A: 1 },
      inferred_scale_label: 'A minor pentatonic',
      inference_confidence: 'high',
      track_id: 'am-blues-70',
      track_label: 'Slow blues',
      track_key: 'A minor',
      track_bpm: 70,
      phrases: [
        {
          duration_ms: 1000,
          notes_per_second: 2,
          unique_pitch_classes: 3,
          midi_span: 5,
          contour: 'rising',
          note_count: 4,
          intonation_cents: 12,
          backing_start_ms: 1000,
          backing_end_ms: 2000,
        },
      ],
      personaChoice: 'technical',
      weak_areas: ['bending'],
    })

    expect(request.persona).toBe('transcriber')
    expect(request.phrases?.[0]?.note_count).toBe(4)
    expect(request.phrases?.[0]?.intonation_cents).toBe(12)
    expect(request.phrases?.[0]?.backing_start_ms).toBe(1000)
    expect(request.weak_areas).toEqual(['bending'])
  })

  it('persists a successful summary as ready', async () => {
    const result = await persistJamSummary('jam-1', requestJamSummary(context()))

    expect(result.grade).toBe('B')
    expect(submitMock).toHaveBeenCalledTimes(1)
    expect(updateMock).toHaveBeenCalledWith('jam-1', {
      summary_bundle_json: JSON.stringify(bundle()),
      coach_summary: 'Solid work.',
      summary_status: 'ready',
    })
  })

  it('marks the row failed when the request fails', async () => {
    submitMock.mockRejectedValue(new Error('network down'))

    await expect(runJamSummary('jam-1', requestJamSummary(context()), 'Fallback.')).rejects.toThrow(
      'network down',
    )

    expect(updateMock).toHaveBeenCalledWith('jam-1', {
      summary_bundle_json: null,
      coach_summary: 'Fallback.',
      summary_status: 'failed',
    })
  })

  it('reconstructs a retry from the persisted row', async () => {
    const row = jamRow()
    await retryJamSummary(row, { weakAreas: ['timing'] })

    expect(submitMock).toHaveBeenCalledTimes(1)
    const body = submitMock.mock.calls[0]![0]
    expect(body.duration_seconds).toBe(30)
    expect(body.persona).toBe('transcriber')
    expect(body.track_id).toBe('am-blues-70')
    expect(body.phrases).toHaveLength(1)
    expect(body.phrases?.[0]?.backing_start_ms).toBe(1000)
    expect(body.weak_areas).toEqual(['timing'])
    expect(updateMock).toHaveBeenNthCalledWith(1, 'jam-1', {
      summary_bundle_json: null,
      coach_summary: 'Previous summary.',
      summary_status: 'pending',
    })
  })

  it('skips retry when the row has no phrase data', async () => {
    const row = { ...jamRow(), phrases_json: null }
    await expect(retryJamSummary(row, { weakAreas: [] })).rejects.toThrow('no phrase data')
    expect(submitMock).not.toHaveBeenCalled()
    expect(updateMock).toHaveBeenCalledWith('jam-1', {
      summary_bundle_json: null,
      coach_summary: 'Previous summary.',
      summary_status: 'skipped',
    })
  })
})
