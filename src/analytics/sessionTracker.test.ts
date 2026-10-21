import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  emit: vi.fn(),
  getAppPref: vi.fn(),
}))

vi.mock('@/src/analytics/eventBus', () => ({
  emit: mocks.emit,
}))

vi.mock('@/src/db/client', () => ({
  getAppPref: mocks.getAppPref,
}))

async function loadTracker() {
  vi.resetModules()
  return import('@/src/analytics/sessionTracker')
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-21T10:00:00.000Z'))
  vi.clearAllMocks()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('session tracker', () => {
  it('starts once, reports step changes, and completes the session', async () => {
    const tracker = await loadTracker()

    tracker.trackSessionPathname('/session/listen', { songTitle: ' Gravity ' })
    tracker.trackSessionPathname('/session/listen', { songTitle: 'Gravity' })

    expect(mocks.emit).toHaveBeenCalledTimes(1)
    expect(mocks.emit).toHaveBeenNthCalledWith(1, {
      type: 'session_start',
      payload: { song_title: 'Gravity', step: 'listen' },
    })

    vi.setSystemTime(new Date('2026-10-21T10:00:10.000Z'))
    tracker.trackSessionPathname('/session/study')
    expect(mocks.emit).toHaveBeenNthCalledWith(2, {
      type: 'session_step_progress',
      payload: { from_step: 'listen', to_step: 'study', elapsed_sec: 10 },
    })

    tracker.completeSession(new Date('2026-10-21T10:01:05.000Z'))
    expect(mocks.emit).toHaveBeenNthCalledWith(3, {
      type: 'session_complete',
      payload: {
        song_title: 'Gravity',
        duration_sec: 65,
        final_step: 'study',
        started_at: '2026-10-21T10:00:00.000Z',
      },
    })

    tracker.handleSessionLayoutUnmount()
    await vi.advanceTimersByTimeAsync(1000)
    expect(mocks.emit).toHaveBeenCalledTimes(3)
  })

  it('abandons an active session after the leave grace period', async () => {
    const tracker = await loadTracker()
    tracker.trackSessionPathname('/session/tune')
    mocks.emit.mockClear()

    tracker.handleSessionLayoutUnmount()
    await vi.advanceTimersByTimeAsync(299)
    expect(mocks.emit).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1)
    expect(mocks.emit).toHaveBeenCalledWith({
      type: 'session_abandon',
      payload: { song_title: null, duration_sec: 0, last_step: 'tune' },
    })
  })

  it('cancels a pending abandon when a StrictMode remount revisits the session', async () => {
    const tracker = await loadTracker()
    tracker.trackSessionPathname('/session/listen')
    mocks.emit.mockClear()

    tracker.handleSessionLayoutUnmount()
    await vi.advanceTimersByTimeAsync(200)
    tracker.trackSessionPathname('/session/listen')
    await vi.advanceTimersByTimeAsync(1000)

    expect(mocks.emit).not.toHaveBeenCalled()
  })

  it('uses a song title learned after the session started', async () => {
    const tracker = await loadTracker()
    tracker.trackSessionPathname('/session/listen')
    tracker.trackSessionPathname('/session/study', { songTitle: 'Neon' })
    mocks.emit.mockClear()

    tracker.completeSession(new Date('2026-10-21T10:02:00.000Z'))

    expect(mocks.emit).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'session_complete',
        payload: expect.objectContaining({ song_title: 'Neon' }),
      }),
    )
  })

  it('ignores non-session pathnames', async () => {
    const tracker = await loadTracker()
    tracker.trackSessionPathname('/settings')
    tracker.trackSessionPathname('/session/unknown')

    expect(mocks.emit).not.toHaveBeenCalled()
  })
})
