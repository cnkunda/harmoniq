import * as React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'

import type { StemMixer } from '@/src/audio/mixerTypes'
import { useLoopAudio } from '@/src/audio/useLoopAudio'

const rafQueue: FrameRequestCallback[] = []
function flushNextRaf() {
  const cb = rafQueue.shift()
  if (cb) cb(0)
}

function stubRaf() {
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    rafQueue.push(cb)
    return rafQueue.length
  })
  vi.stubGlobal('cancelAnimationFrame', () => {
    rafQueue.length = 0
  })
}

function Harness({
  active,
  mixerRef,
}: {
  active: boolean
  mixerRef: React.RefObject<StemMixer | null>
}) {
  useLoopAudio({
    active,
    startSec: 0,
    endSec: 2,
    mixerRef,
  })
  return null
}

function minimalMixer(partial: Partial<StemMixer> & Pick<StemMixer, 'seek' | 'getPositionSeconds'>): StemMixer {
  return partial as StemMixer
}

describe('useLoopAudio', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    rafQueue.length = 0
  })

  it('uses getPositionSecondsNow for wrap check and does not call getPositionSeconds when sync is available', async () => {
    stubRaf()
    const getPositionSeconds = vi.fn(() => Promise.reject(new Error('async position should not be used')))
    let now = 1.99
    const seek = vi.fn(async (sec: number) => {
      now = sec
    })
    const mixerRef: React.RefObject<StemMixer | null> = {
      current: minimalMixer({
        getPositionSecondsNow: () => now,
        getPositionSeconds,
        seek,
        load: vi.fn(),
        play: vi.fn(),
        pause: vi.fn(),
        setStemGain: vi.fn(),
        setPlaybackRate: vi.fn(),
        getDurationSeconds: () => 10,
        unload: vi.fn(),
      }),
    }

    await act(async () => {
      TestRenderer.create(React.createElement(Harness, { active: true, mixerRef }))
    })

    flushNextRaf()
    expect(seek).not.toHaveBeenCalled()
    expect(getPositionSeconds).not.toHaveBeenCalled()

    now = 2.01
    flushNextRaf()
    expect(seek).toHaveBeenCalledTimes(1)
    expect(seek).toHaveBeenCalledWith(0)
    expect(getPositionSeconds).not.toHaveBeenCalled()

    await act(async () => {
      await Promise.resolve()
    })
  })

  it('falls back to getPositionSeconds when getPositionSecondsNow is missing', async () => {
    stubRaf()
    const seek = vi.fn(async () => {})
    const mixerRef: React.RefObject<StemMixer | null> = {
      current: minimalMixer({
        getPositionSeconds: () => Promise.resolve(2.05),
        seek,
        load: vi.fn(),
        play: vi.fn(),
        pause: vi.fn(),
        setStemGain: vi.fn(),
        setPlaybackRate: vi.fn(),
        getDurationSeconds: () => 10,
        unload: vi.fn(),
      }),
    }

    await act(async () => {
      TestRenderer.create(React.createElement(Harness, { active: true, mixerRef }))
    })

    flushNextRaf()
    await act(async () => {
      await Promise.resolve()
    })

    expect(seek).toHaveBeenCalledWith(0)
  })
})
