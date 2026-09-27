import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import { ApiError, AnalyzePollCancelledError, pollAnalyzeJobCancelable } from './analyze'
import type { AnalyzeJob, LessonJSON } from '@/src/types'

const { openAnalyzeSseMock } = vi.hoisted(() => ({ openAnalyzeSseMock: vi.fn() }))

vi.mock('@/src/api/analyzeSse', () => ({ openAnalyzeSse: openAnalyzeSseMock }))
vi.mock('@/src/config', () => ({ API_BASE_URL: 'http://sse-test' }))

type SseHandlers = Parameters<typeof import('./analyzeSse').openAnalyzeSse>[2]

const lesson = { job_id: 'job-1', song_title: 'Gravity' } as unknown as LessonJSON
const completeJob: AnalyzeJob = { status: 'complete', result: lesson, error: null, error_code: null }
const processingJob: AnalyzeJob = {
  status: 'processing',
  result: null,
  error: null,
  error_code: null,
  progress: 0.62,
  analysis_stage: 'chords_inferring',
}

function sseHandle() {
  return { close: vi.fn() }
}

function lastSseCall(): { jobId: string; handlers: SseHandlers } {
  const call = openAnalyzeSseMock.mock.calls.at(-1)
  expect(call).toBeDefined()
  return { jobId: call![1] as string, handlers: call![2] }
}

function stubFetch(payload: unknown) {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => payload,
  }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('pollAnalyzeJobCancelable (Commit 151 SSE chain)', () => {
  let consoleLogSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    openAnalyzeSseMock.mockReset()
    consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    consoleLogSpy.mockRestore()
    vi.useRealTimers()
  })

  it('consumes the SSE stream end-to-end and makes zero status requests', async () => {
    const handle = sseHandle()
    openAnalyzeSseMock.mockReturnValue(handle)
    const onStatus = vi.fn()

    const { promise } = pollAnalyzeJobCancelable('job-1', onStatus)
    const { jobId, handlers } = lastSseCall()
    expect(jobId).toBe('job-1')

    handlers.onJob(processingJob)
    expect(onStatus).toHaveBeenCalledTimes(1)
    expect(onStatus.mock.calls[0][0].analysis_stage).toBe('chords_inferring')

    handlers.onJob(completeJob) // terminal resolves the promise and closes the stream
    await expect(promise).resolves.toEqual(lesson)
    expect(handle.close).toHaveBeenCalled()
    expect(openAnalyzeSseMock).toHaveBeenCalledTimes(1)
  })

  it('rejects with ApiError when the stream reports a failed status', async () => {
    openAnalyzeSseMock.mockReturnValue(sseHandle())
    const { promise } = pollAnalyzeJobCancelable('job-1', vi.fn())

    lastSseCall().handlers.onJob({
      status: 'failed',
      result: null,
      error: 'Analysis failed.',
      error_code: 'analysis_failed',
    })

    const err = await promise.catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ message: 'Analysis failed.', errorCode: 'analysis_failed' })
  })

  it('cancel closes the SSE stream and ignores any late events', async () => {
    const handle = sseHandle()
    openAnalyzeSseMock.mockReturnValue(handle)
    const onStatus = vi.fn()

    const { promise, cancel } = pollAnalyzeJobCancelable('job-1', onStatus)
    const { handlers } = lastSseCall()

    cancel()
    await expect(promise).rejects.toBeInstanceOf(AnalyzePollCancelledError)
    expect(handle.close).toHaveBeenCalled()

    handlers.onJob(processingJob)
    handlers.onJob(completeJob)
    expect(onStatus).not.toHaveBeenCalled()
    await new Promise((r) => setTimeout(r, 0)) // promise already settled — nothing to resolve
  })

  it('falls back to polling when SSE is unsupported, then stops after terminal (BUG-01)', async () => {
    vi.useFakeTimers()
    openAnalyzeSseMock.mockReturnValue(null) // node/test environment: no SSE
    const fetchMock = stubFetch({ status: 'complete', result: lesson, error: null, error_code: null })
    const onStatus = vi.fn()

    const { promise } = pollAnalyzeJobCancelable('job-1', onStatus)
    await expect(promise).resolves.toEqual(lesson)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(onStatus).not.toHaveBeenCalled() // first response was already terminal

    // Any scheduled follow-up poll would fire here — BUG-01: there must be none.
    await vi.runAllTimersAsync()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('falls back to polling after the stream dies mid-flight, with identical callbacks', async () => {
    openAnalyzeSseMock.mockReturnValue(sseHandle())
    const fetchMock = stubFetch({ status: 'complete', result: lesson, error: null, error_code: null })
    const onStatus = vi.fn()

    const { promise } = pollAnalyzeJobCancelable('job-1', onStatus)
    lastSseCall().handlers.onUnavailable(new Error('connection reset'))

    expect(consoleLogSpy).toHaveBeenCalledWith(
      '[analyze] SSE unavailable, falling back to polling:',
      'connection reset',
    )
    await expect(promise).resolves.toEqual(lesson)
    expect(fetchMock).toHaveBeenCalledTimes(1) // one fallback loop, no duplicates
  })

  it('reports processing polls to onStatus and forwards analysis_stage', async () => {
    openAnalyzeSseMock.mockReturnValue(null)
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ ...processingJob }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const onStatus = vi.fn()
    const { promise, cancel } = pollAnalyzeJobCancelable('job-1', onStatus)

    await vi.waitFor(() => expect(onStatus).toHaveBeenCalledTimes(1))
    expect(onStatus.mock.calls[0][0].analysis_stage).toBe('chords_inferring')
    cancel()
    await expect(promise).rejects.toBeInstanceOf(AnalyzePollCancelledError)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
