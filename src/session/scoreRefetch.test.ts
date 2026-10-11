import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createScoreRefetchScheduler, SCORE_REFETCH_DEBOUNCE_MS } from './scoreRefetch'

type FetchJob = ReturnType<typeof vi.fn>

function makeScheduler(overrides?: {
  fetchJob?: FetchJob
  debounceMs?: number
}) {
  const fetchJob = overrides?.fetchJob ?? vi.fn(async () => 'ok')
  const applyResult = vi.fn()
  const onError = vi.fn()
  const onStateChange = vi.fn()
  const scheduler = createScoreRefetchScheduler<string>({
    fetchJob: fetchJob as unknown as (jobId: string) => Promise<string>,
    applyResult,
    onError,
    onStateChange,
    debounceMs: overrides?.debounceMs,
  })
  return { scheduler, fetchJob, applyResult, onError, onStateChange }
}

/** Flush pending microtasks so in-flight async runs settle. */
async function flush(): Promise<void> {
  for (let i = 0; i < 10; i++) await Promise.resolve()
}

describe('createScoreRefetchScheduler (Commit 153 debounce)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('coalesces rapid successive requests into a single fetch', async () => {
    const { scheduler, fetchJob, applyResult, onError } = makeScheduler()

    for (let i = 0; i < 5; i++) scheduler.request('job-1')
    expect(fetchJob).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(SCORE_REFETCH_DEBOUNCE_MS)
    await flush()

    expect(fetchJob).toHaveBeenCalledTimes(1)
    expect(fetchJob).toHaveBeenCalledWith('job-1')
    expect(applyResult).toHaveBeenCalledTimes(1)
    expect(onError).not.toHaveBeenCalled()
  })

  it('does not fetch when requests stay inside the debounce window boundary', async () => {
    const { scheduler, fetchJob } = makeScheduler()

    scheduler.request('job-1')
    await vi.advanceTimersByTimeAsync(SCORE_REFETCH_DEBOUNCE_MS - 1)
    scheduler.request('job-1')
    await vi.advanceTimersByTimeAsync(SCORE_REFETCH_DEBOUNCE_MS - 1)
    scheduler.request('job-1')
    await vi.advanceTimersByTimeAsync(SCORE_REFETCH_DEBOUNCE_MS)
    await flush()

    expect(fetchJob).toHaveBeenCalledTimes(1)
  })

  it('emits updating=true while pending and false once idle', async () => {
    const { scheduler, onStateChange } = makeScheduler()

    scheduler.request('job-1')
    expect(onStateChange).toHaveBeenLastCalledWith(true)

    await vi.advanceTimersByTimeAsync(SCORE_REFETCH_DEBOUNCE_MS)
    await flush()
    expect(onStateChange).toHaveBeenLastCalledWith(false)
  })

  it('re-schedules one follow-up fetch when a request lands mid-flight', async () => {
    let resolveFirst: (value: string) => void = () => {}
    const fetchJob = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          if (fetchJob.mock.calls.length === 1) resolveFirst = resolve
          else resolve('second')
        }),
    )
    const { scheduler, applyResult } = makeScheduler({ fetchJob: fetchJob as unknown as FetchJob })

    scheduler.request('job-1')
    await vi.advanceTimersByTimeAsync(SCORE_REFETCH_DEBOUNCE_MS)
    expect(fetchJob).toHaveBeenCalledTimes(1)

    // Corrections land while the first fetch is still in flight — the debounce
    // window elapses mid-flight, so the run queues instead of overlapping.
    scheduler.request('job-1')
    scheduler.request('job-1')
    await vi.advanceTimersByTimeAsync(SCORE_REFETCH_DEBOUNCE_MS)
    expect(fetchJob).toHaveBeenCalledTimes(1)

    resolveFirst('first')
    await flush()
    expect(fetchJob).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(SCORE_REFETCH_DEBOUNCE_MS)
    await flush()
    expect(fetchJob).toHaveBeenCalledTimes(2)
    expect(applyResult).toHaveBeenCalledTimes(2)
  })

  it('reports fetch failures through onError and recovers for the next run', async () => {
    const fetchJob = vi
      .fn()
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce('ok')
    const { scheduler, onError, applyResult } = makeScheduler({ fetchJob: fetchJob as unknown as FetchJob })

    scheduler.request('job-1')
    await vi.advanceTimersByTimeAsync(SCORE_REFETCH_DEBOUNCE_MS)
    await flush()
    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError).toHaveBeenCalledWith('job-1', expect.objectContaining({ message: 'boom' }))
    expect(applyResult).not.toHaveBeenCalled()

    scheduler.request('job-1')
    await vi.advanceTimersByTimeAsync(SCORE_REFETCH_DEBOUNCE_MS)
    await flush()
    expect(applyResult).toHaveBeenCalledTimes(1)
  })

  it('cancel drops a pending fetch without hitting the network', async () => {
    const { scheduler, fetchJob, onStateChange } = makeScheduler()

    scheduler.request('job-1')
    scheduler.cancel()
    expect(onStateChange).toHaveBeenLastCalledWith(false)

    await vi.advanceTimersByTimeAsync(SCORE_REFETCH_DEBOUNCE_MS * 2)
    await flush()
    expect(fetchJob).not.toHaveBeenCalled()
  })
})
