import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AnalyticsEventRow } from '@/src/db/types'

const mocks = vi.hoisted(() => ({
  getAppPref: vi.fn(),
  setAppPref: vi.fn(),
  insertAnalyticsEvents: vi.fn(),
  subscribeAnalyticsBackground: vi.fn(),
}))

vi.mock('@/src/db/client', () => ({
  getAppPref: mocks.getAppPref,
  setAppPref: mocks.setAppPref,
  insertAnalyticsEvents: mocks.insertAnalyticsEvents,
}))

vi.mock('@/src/analytics/appLifecycle', () => ({
  subscribeAnalyticsBackground: mocks.subscribeAnalyticsBackground,
}))

async function loadBus() {
  vi.resetModules()
  return import('@/src/analytics/eventBus')
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getAppPref.mockImplementation(async (key: string) => {
    if (key === 'analytics_user_id') return 'user-1'
    return null
  })
  mocks.setAppPref.mockResolvedValue(undefined)
  mocks.insertAnalyticsEvents.mockResolvedValue(undefined)
  mocks.subscribeAnalyticsBackground.mockReturnValue(() => {})
})

afterEach(() => {
  vi.useRealTimers()
})

describe('analytics event bus', () => {
  it('queues emitted events and flushes them with the anonymous user id', async () => {
    const bus = await loadBus()
    bus.clearAnalyticsQueue()

    bus.emit({
      id: 'event-1',
      timestamp: '2026-10-21T10:00:00.000Z',
      type: 'play_along_start',
      payload: { tempo_bpm: 92 },
    })

    await bus.flushAnalytics()

    expect(mocks.insertAnalyticsEvents).toHaveBeenCalledTimes(1)
    expect(mocks.insertAnalyticsEvents).toHaveBeenCalledWith([
      {
        id: 'event-1',
        user_id: 'user-1',
        event_type: 'play_along_start',
        payload_json: JSON.stringify({ tempo_bpm: 92 }),
        timestamp: '2026-10-21T10:00:00.000Z',
      } satisfies AnalyticsEventRow,
    ])
  })

  it('drops new events after opting out and clears the pending queue', async () => {
    const bus = await loadBus()
    bus.clearAnalyticsQueue()

    bus.emit({ type: 'feature_usage', payload: { feature: 'practice_insights' } })
    await bus.setAnalyticsEnabled(false)
    bus.emit({ type: 'feature_usage', payload: { feature: 'analytics_export' } })

    await bus.flushAnalytics()

    expect(mocks.setAppPref).toHaveBeenCalledWith('analytics_opt_out', '1')
    expect(mocks.insertAnalyticsEvents).not.toHaveBeenCalled()
  })

  it('keeps analytics enabled when persisting the opt-out preference fails', async () => {
    const bus = await loadBus()
    bus.clearAnalyticsQueue()
    mocks.setAppPref.mockRejectedValueOnce(new Error('pref write failed'))

    await expect(bus.setAnalyticsEnabled(false)).rejects.toThrow('pref write failed')

    bus.emit({
      id: 'event-after-failure',
      timestamp: '2026-10-21T10:03:00.000Z',
      type: 'feature_usage',
      payload: { feature: 'practice_insights' },
    })
    await bus.flushAnalytics()

    expect(mocks.insertAnalyticsEvents).toHaveBeenCalledTimes(1)
  })

  it('re-queues a failed batch so a later flush can persist it', async () => {
    const bus = await loadBus()
    bus.clearAnalyticsQueue()
    mocks.insertAnalyticsEvents.mockRejectedValueOnce(new Error('disk full'))

    bus.emit({
      id: 'event-retry',
      timestamp: '2026-10-21T10:05:00.000Z',
      type: 'correction_made',
      payload: { job_id: 'job-1', feedback_type: 'chord_correction', event_index: 2 },
    })

    await expect(bus.flushAnalytics()).rejects.toThrow('disk full')
    await bus.flushAnalytics()

    expect(mocks.insertAnalyticsEvents).toHaveBeenCalledTimes(2)
    expect(mocks.insertAnalyticsEvents.mock.calls[1]?.[0]).toHaveLength(1)
  })

  it('clears queued events on start when the opt-out pref is set', async () => {
    const bus = await loadBus()
    bus.clearAnalyticsQueue()
    mocks.getAppPref.mockImplementation(async (key: string) => {
      if (key === 'analytics_opt_out') return '1'
      return null
    })

    bus.emit({ type: 'feature_usage', payload: { feature: 'practice_insights' } })
    await bus.startAnalytics()
    await bus.flushAnalytics()

    expect(mocks.insertAnalyticsEvents).not.toHaveBeenCalled()
    expect(mocks.subscribeAnalyticsBackground).not.toHaveBeenCalled()
  })

  it('flushes queued events on the 30s interval once started', async () => {
    vi.useFakeTimers()
    const bus = await loadBus()
    bus.clearAnalyticsQueue()
    await bus.startAnalytics()

    bus.emit({
      id: 'timer-event',
      timestamp: '2026-10-21T10:10:00.000Z',
      type: 'feature_usage',
      payload: { feature: 'practice_insights' },
    })

    await vi.advanceTimersByTimeAsync(29_999)
    expect(mocks.insertAnalyticsEvents).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1)
    expect(mocks.insertAnalyticsEvents).toHaveBeenCalledTimes(1)

    bus.stopAnalytics()
  })
})
