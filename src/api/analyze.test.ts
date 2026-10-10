import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import {
  ApiError,
  AnalyzePollCancelledError,
  connectAnalyzeWebSocket,
  pollAnalyzeJobCancelable,
} from './analyze'
import type { AnalyzeJob, LessonJSON } from '@/src/types'

const { openAnalyzeSseMock } = vi.hoisted(() => ({ openAnalyzeSseMock: vi.fn() }))

vi.mock('@/src/api/analyzeSse', async (importOriginal) => ({
  // Keep the real pure helpers (parsePartialResult) — only the transport is stubbed.
  ...(await importOriginal<typeof import('./analyzeSse')>()),
  openAnalyzeSse: openAnalyzeSseMock,
}))
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
    const partialResult = {
      chord_timeline: { events: [{ timestamp: 0, chord: 'G:maj', confidence: 0.9 }] },
      bpm: 96.5,
      total_duration: 183.2,
    }
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ ...processingJob, partial_result: partialResult }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const onStatus = vi.fn()
    const { promise, cancel } = pollAnalyzeJobCancelable('job-1', onStatus)

    await vi.waitFor(() => expect(onStatus).toHaveBeenCalledTimes(1))
    expect(onStatus.mock.calls[0][0].analysis_stage).toBe('chords_inferring')
    // Commit 152: polling returns the whole JobStatus — partial_result flows through.
    expect(onStatus.mock.calls[0][0].partial_result).toEqual(partialResult)
    cancel()
    await expect(promise).rejects.toBeInstanceOf(AnalyzePollCancelledError)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

// ---- Commit 152: WebSocket status frames carry analysis_stage + partial_result ----

describe('connectAnalyzeWebSocket WS status mapping (Commit 152)', () => {
  class FakeWebSocket {
    static readonly OPEN = 1
    static instances: FakeWebSocket[] = []
    url: string
    readyState = 0
    onopen: (() => void) | null = null
    onmessage: ((event: { data: string }) => void) | null = null
    onerror: (() => void) | null = null
    onclose: (() => void) | null = null

    constructor(url: string) {
      this.url = url
      FakeWebSocket.instances.push(this)
      queueMicrotask(() => {
        this.readyState = FakeWebSocket.OPEN
        this.onopen?.()
      })
    }

    close() {
      this.readyState = 3
      this.onclose?.()
    }

    emit(payload: unknown) {
      this.onmessage?.({ data: JSON.stringify(payload) })
    }
  }

  let consoleLogSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    openAnalyzeSseMock.mockReset()
    openAnalyzeSseMock.mockReturnValue(null) // force the WS branch
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
    consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    consoleLogSpy.mockRestore()
  })

  it('forwards analysis_stage and partial_result from WS status frames, then resolves on complete', async () => {
    const onStatus = vi.fn()
    const { promise } = connectAnalyzeWebSocket('job-1', onStatus)

    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    const ws = FakeWebSocket.instances[0]
    await vi.waitFor(() => expect(ws.readyState).toBe(FakeWebSocket.OPEN))

    ws.emit({
      type: 'status',
      status: 'processing',
      progress: 0.6,
      stage_label: 'Transcribing with MT3…',
      analysis_stage: 'mt3_inferring',
      partial_result: {
        chord_timeline: { events: [{ timestamp: 0, chord: 'G:maj', confidence: 0.9 }] },
        bpm: 96.5,
        total_duration: 183.2,
      },
    })

    expect(onStatus).toHaveBeenCalledTimes(1)
    const job = onStatus.mock.calls[0][0] as AnalyzeJob
    expect(job.analysis_stage).toBe('mt3_inferring')
    expect(job.partial_result?.bpm).toBe(96.5)
    expect(job.partial_result?.chord_timeline.events).toHaveLength(1)

    ws.emit({ type: 'complete', result: lesson })
    await expect(promise).resolves.toEqual(lesson)
  })

  it('maps an absent partial_result to null on WS status frames', async () => {
    const onStatus = vi.fn()
    const { promise, cancel } = connectAnalyzeWebSocket('job-1', onStatus)

    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    const ws = FakeWebSocket.instances[0]
    await vi.waitFor(() => expect(ws.readyState).toBe(FakeWebSocket.OPEN))

    ws.emit({ type: 'status', status: 'processing', progress: 0.4, analysis_stage: 'stems_separating' })
    expect((onStatus.mock.calls[0][0] as AnalyzeJob).partial_result).toBeNull()

    cancel()
    await expect(promise).rejects.toBeInstanceOf(AnalyzePollCancelledError)
  })
})
