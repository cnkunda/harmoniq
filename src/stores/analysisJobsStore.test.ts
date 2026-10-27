import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  toastSuccess: vi.fn(),
  getJobStatus: vi.fn(),
  getAppPref: vi.fn(),
  setAppPref: vi.fn(),
  upsertLessonFromAnalysis: vi.fn(),
}))

vi.mock('@/src/api/analyze', () => {
  class ApiError extends Error {
    constructor(
      public status: number,
      message: string,
    ) {
      super(message)
      this.name = 'ApiError'
    }
  }
  return { ApiError, getJobStatus: mocks.getJobStatus }
})

vi.mock('@/src/db/client', () => ({
  getAppPref: mocks.getAppPref,
  setAppPref: mocks.setAppPref,
  upsertLessonFromAnalysis: mocks.upsertLessonFromAnalysis,
}))

vi.mock('@/components/ToastConfig', () => ({
  toast: { success: mocks.toastSuccess },
}))

import { getJobStatus } from '@/src/api/analyze'
import { getAppPref, setAppPref, upsertLessonFromAnalysis } from '@/src/db/client'
import { PREF_ANALYSIS_JOBS_JSON } from '@/src/db/schema'
import { useAnalysisJobsStore } from '@/src/stores/analysisJobsStore'
import type { AnalyzeJob, LessonJSON } from '@/src/types'

const getJobStatusMock = vi.mocked(getJobStatus)
const getAppPrefMock = vi.mocked(getAppPref)
const setAppPrefMock = vi.mocked(setAppPref)
const upsertLessonMock = vi.mocked(upsertLessonFromAnalysis)

function lesson(jobId = 'job-1'): LessonJSON {
  return { job_id: jobId, song_title: 'Gravity', sections: [] } as unknown as LessonJSON
}

function status(overrides: Partial<AnalyzeJob>): AnalyzeJob {
  return { status: 'processing', result: null, error: null, ...overrides }
}

function storedJob(overrides: Record<string, unknown> = {}) {
  return {
    jobId: 'job-1',
    sourceKind: 'youtube',
    sourceRef: 'https://youtube.com/watch?v=abc',
    title: 'Gravity',
    artist: null,
    submittedAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    status: 'processing',
    progress: 0.2,
    stageLabel: 'Separating stems…',
    error: null,
    errorCode: null,
    ...overrides,
  }
}

describe('useAnalysisJobsStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getJobStatus.mockReset()
    mocks.getAppPref.mockReset()
    mocks.setAppPref.mockReset()
    mocks.upsertLessonFromAnalysis.mockReset()
    mocks.toastSuccess.mockReset()
    getAppPrefMock.mockResolvedValue(null)
    setAppPrefMock.mockResolvedValue(undefined)
    upsertLessonMock.mockResolvedValue(undefined)
    useAnalysisJobsStore.setState({ jobs: [], hydrated: false })
  })

  it('hydrates persisted jobs from app prefs', async () => {
    getAppPrefMock.mockResolvedValue(JSON.stringify([storedJob()]))
    await useAnalysisJobsStore.getState().hydrate()
    expect(getAppPrefMock).toHaveBeenCalledWith(PREF_ANALYSIS_JOBS_JSON)
    expect(useAnalysisJobsStore.getState().jobs).toHaveLength(1)
    expect(useAnalysisJobsStore.getState().jobs[0]?.jobId).toBe('job-1')
  })

  it('tracks a newly submitted job and persists it', async () => {
    await useAnalysisJobsStore.getState().track({
      jobId: 'job-1',
      sourceKind: 'upload',
      sourceRef: 'take.mp3',
      title: 'take',
    })
    const [job] = useAnalysisJobsStore.getState().jobs
    expect(job?.jobId).toBe('job-1')
    expect(job?.status).toBe('queued')
    expect(setAppPrefMock).toHaveBeenCalledWith(
      PREF_ANALYSIS_JOBS_JSON,
      expect.stringContaining('job-1'),
    )
  })

  it('updates progress from Add Song status frames', async () => {
    getAppPrefMock.mockResolvedValue(JSON.stringify([storedJob()]))
    await useAnalysisJobsStore.getState().hydrate()
    await useAnalysisJobsStore.getState().applyStatus(
      'job-1',
      status({ status: 'processing', progress: 0.6, stage_label: 'Transcribing (MT3)…' }),
    )
    const [job] = useAnalysisJobsStore.getState().jobs
    expect(job?.progress).toBe(0.6)
    expect(job?.stageLabel).toBe('Transcribing (MT3)…')
  })

  it('saves a completed background job, removes it, and notifies', async () => {
    getAppPrefMock.mockResolvedValue(JSON.stringify([storedJob()]))
    getJobStatusMock.mockResolvedValue(status({ status: 'complete', result: lesson() }))
    await useAnalysisJobsStore.getState().hydrate()
    await useAnalysisJobsStore.getState().refresh()
    expect(upsertLessonMock).toHaveBeenCalledWith(expect.objectContaining({ job_id: 'job-1' }))
    expect(useAnalysisJobsStore.getState().jobs).toEqual([])
    await vi.waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledWith('Gravity is ready.'))
  })

  it('keeps failed background jobs visible with the server error', async () => {
    getAppPrefMock.mockResolvedValue(JSON.stringify([storedJob()]))
    getJobStatusMock.mockResolvedValue(
      status({ status: 'failed', error: 'No guitar stem.', error_code: 'no_usable_guitar_stem' }),
    )
    await useAnalysisJobsStore.getState().hydrate()
    await useAnalysisJobsStore.getState().refresh()
    const [job] = useAnalysisJobsStore.getState().jobs
    expect(job?.status).toBe('failed')
    expect(job?.error).toBe('No guitar stem.')
    expect(job?.errorCode).toBe('no_usable_guitar_stem')
    expect(mocks.toastSuccess).not.toHaveBeenCalled()
  })

  it('dismisses a tracked job', async () => {
    getAppPrefMock.mockResolvedValue(JSON.stringify([storedJob()]))
    await useAnalysisJobsStore.getState().hydrate()
    await useAnalysisJobsStore.getState().dismiss('job-1')
    expect(useAnalysisJobsStore.getState().jobs).toEqual([])
    expect(setAppPrefMock).toHaveBeenCalledWith(PREF_ANALYSIS_JOBS_JSON, '[]')
  })
})
