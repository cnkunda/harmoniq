import { describe, expect, it } from 'vitest'

import {
  TRACKED_ACTIVE_MAX_MS,
  TRACKED_FAILED_TTL_MS,
  applyTrackedJobProgress,
  createTrackedAnalysisJob,
  markTrackedJobFailed,
  parseTrackedAnalysisJobs,
  pruneTrackedAnalysisJobs,
  removeTrackedAnalysisJob,
  upsertTrackedAnalysisJob,
  type TrackedAnalysisJob,
} from '@/src/analysis/trackedAnalysisJobs'
import type { AnalyzeJob } from '@/src/types'

const NOW = Date.parse('2026-10-27T12:00:00.000Z')

function tracked(overrides: Partial<TrackedAnalysisJob> = {}): TrackedAnalysisJob {
  return {
    ...createTrackedAnalysisJob(
      {
        jobId: 'job-1',
        sourceKind: 'youtube',
        sourceRef: 'https://youtube.com/watch?v=abc',
        title: 'Gravity',
      },
      NOW,
    ),
    ...overrides,
  }
}

function status(overrides: Partial<AnalyzeJob>): AnalyzeJob {
  return {
    status: 'processing',
    result: null,
    error: null,
    ...overrides,
  }
}

describe('createTrackedAnalysisJob', () => {
  it('starts queued with a stable timestamp', () => {
    const job = tracked()
    expect(job.status).toBe('queued')
    expect(job.submittedAt).toBe('2026-10-27T12:00:00.000Z')
    expect(job.updatedAt).toBe(job.submittedAt)
    expect(job.title).toBe('Gravity')
  })

  it('falls back to the source reference when the title is blank', () => {
    const job = createTrackedAnalysisJob(
      { jobId: 'j', sourceKind: 'upload', sourceRef: 'take.mp3', title: '   ' },
      NOW,
    )
    expect(job.title).toBe('take.mp3')
  })
})

describe('parseTrackedAnalysisJobs', () => {
  it('returns an empty list for malformed JSON', () => {
    expect(parseTrackedAnalysisJobs('not-json', NOW)).toEqual([])
    expect(parseTrackedAnalysisJobs('{"jobId":"x"}', NOW)).toEqual([])
    expect(parseTrackedAnalysisJobs(null, NOW)).toEqual([])
  })

  it('keeps valid rows and drops invalid ones', () => {
    const raw = JSON.stringify([
      tracked(),
      { jobId: '', status: 'processing', sourceKind: 'youtube' },
      { jobId: 'job-2', status: 'unknown', sourceKind: 'youtube' },
      { jobId: 'job-3', status: 'processing', sourceKind: 'spotify' },
    ])
    const jobs = parseTrackedAnalysisJobs(raw, NOW)
    expect(jobs).toHaveLength(1)
    expect(jobs[0]?.jobId).toBe('job-1')
  })

  it('clamps progress and defaults invalid timestamps', () => {
    const raw = JSON.stringify([
      {
        jobId: 'job-1',
        status: 'processing',
        sourceKind: 'upload',
        sourceRef: 'take.mp3',
        progress: 4,
        submittedAt: 'not-a-date',
        updatedAt: 'also-not-a-date',
      },
    ])
    const [job] = parseTrackedAnalysisJobs(raw, NOW)
    expect(job?.progress).toBe(1)
    expect(job?.submittedAt).toBe('2026-10-27T12:00:00.000Z')
    expect(job?.updatedAt).toBe('2026-10-27T12:00:00.000Z')
  })
})

describe('upsertTrackedAnalysisJob / removeTrackedAnalysisJob', () => {
  it('replaces an existing job and sorts newest first', () => {
    const first = tracked()
    const second = tracked({ jobId: 'job-2', submittedAt: '2026-10-27T13:00:00.000Z' })
    const updated = { ...first, title: 'Gravity (live)' }
    const jobs = upsertTrackedAnalysisJob([first], updated)
    expect(jobs).toHaveLength(1)
    expect(jobs[0]?.title).toBe('Gravity (live)')
    expect(upsertTrackedAnalysisJob([first, second], first)[0]?.jobId).toBe('job-2')
  })

  it('removes by job id', () => {
    expect(removeTrackedAnalysisJob([tracked(), tracked({ jobId: 'job-2' })], 'job-1')).toHaveLength(1)
  })
})

describe('applyTrackedJobProgress', () => {
  it('updates progress and stage for processing jobs', () => {
    const next = applyTrackedJobProgress(
      tracked(),
      status({ status: 'processing', progress: 0.42, stage_label: 'Separating stems…' }),
      NOW + 1000,
    )
    expect(next.status).toBe('processing')
    expect(next.progress).toBe(0.42)
    expect(next.stageLabel).toBe('Separating stems…')
    expect(next.updatedAt).toBe('2026-10-27T12:00:01.000Z')
  })

  it('keeps the previous progress when the server omits it', () => {
    const next = applyTrackedJobProgress(
      tracked({ progress: 0.3 }),
      status({ status: 'processing', progress: null, stage_label: null }),
      NOW + 1000,
    )
    expect(next.progress).toBe(0.3)
  })

  it('marks failed jobs with the server error', () => {
    const next = applyTrackedJobProgress(
      tracked(),
      status({ status: 'failed', error: 'No guitar stem.', error_code: 'no_usable_guitar_stem' }),
      NOW + 1000,
    )
    expect(next.status).toBe('failed')
    expect(next.error).toBe('No guitar stem.')
    expect(next.errorCode).toBe('no_usable_guitar_stem')
  })

  it('leaves complete jobs untouched for the caller to persist', () => {
    const job = tracked({ status: 'processing' })
    expect(applyTrackedJobProgress(job, status({ status: 'complete' }), NOW + 1000)).toBe(job)
  })
})

describe('pruneTrackedAnalysisJobs', () => {
  it('expires jobs still active after the backend TTL', () => {
    const job = tracked({ status: 'processing' })
    const [next] = pruneTrackedAnalysisJobs([job], NOW + TRACKED_ACTIVE_MAX_MS + 1)
    expect(next?.status).toBe('failed')
    expect(next?.errorCode).toBe('analysis_expired')
  })

  it('drops old failed jobs', () => {
    const failed = markTrackedJobFailed(tracked(), 'Nope', 'analysis_failed', NOW)
    expect(pruneTrackedAnalysisJobs([failed], NOW + TRACKED_FAILED_TTL_MS + 1)).toEqual([])
  })

  it('keeps recent failed jobs', () => {
    const failed = markTrackedJobFailed(tracked(), 'Nope', 'analysis_failed', NOW)
    expect(pruneTrackedAnalysisJobs([failed], NOW + 1000)).toHaveLength(1)
  })
})
