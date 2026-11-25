/**
 * @vitest-environment jsdom
 */
import { Blob as NodeBlob } from 'node:buffer'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createSessionRecorder } from '@/src/audio/recordSession.web'

const web = vi.hoisted(() => {
  const tracks = { first: { stop: vi.fn() }, second: { stop: vi.fn() } }
  const fakeStream = {
    getTracks: () => [tracks.first, tracks.second],
  }
  class FakeMediaRecorder {
    static instances: FakeMediaRecorder[] = []
    static isTypeSupported = vi.fn((_type: string) => true)
    ondataavailable: ((event: { data: Blob }) => void) | null = null
    onstop: (() => void) | null = null
    mimeType: string
    start = vi.fn()
    stop = vi.fn(() => {
      this.onstop?.()
    })
    constructor(public stream: unknown, options: { mimeType?: string }) {
      this.mimeType = options.mimeType ?? ''
      FakeMediaRecorder.instances.push(this)
    }
  }
  return {
    FakeMediaRecorder,
    fakeStream,
    tracks,
    getUserMedia: vi.fn(async (_constraints: MediaStreamConstraints) => fakeStream),
  }
})

const helloBytes = new Uint8Array([104, 101, 108, 108, 111])

beforeEach(() => {
  web.FakeMediaRecorder.instances.length = 0
  web.FakeMediaRecorder.isTypeSupported.mockReset().mockReturnValue(true)
  web.getUserMedia.mockClear()
  web.tracks.first.stop.mockClear()
  web.tracks.second.stop.mockClear()
  vi.stubGlobal('MediaRecorder', web.FakeMediaRecorder)
  // jsdom's Blob has no arrayBuffer(); source code needs the WHATWG methods.
  vi.stubGlobal('Blob', NodeBlob)
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: web.getUserMedia },
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: undefined })
})

describe('WebSessionRecorder', () => {
  describe('start', () => {
    it('requests microphone access and starts a MediaRecorder with opus when supported', async () => {
      const recorder = createSessionRecorder()

      await recorder.start()

      expect(web.getUserMedia).toHaveBeenCalledWith({ audio: true })
      expect(web.FakeMediaRecorder.isTypeSupported).toHaveBeenCalledWith('audio/webm;codecs=opus')
      const instance = web.FakeMediaRecorder.instances[0]!
      expect(instance.stream).toBe(web.fakeStream)
      expect(instance.mimeType).toBe('audio/webm;codecs=opus')
      expect(instance.start).toHaveBeenCalledTimes(1)
      expect(recorder.isRecording()).toBe(true)
    })

    it('falls back to plain webm when opus is unsupported', async () => {
      web.FakeMediaRecorder.isTypeSupported.mockReturnValue(false)
      const recorder = createSessionRecorder()

      await recorder.start()

      expect(web.FakeMediaRecorder.instances[0]!.mimeType).toBe('audio/webm')
      expect(recorder.isRecording()).toBe(true)
    })

    it('throws when the browser has no mediaDevices', async () => {
      Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: undefined })
      const recorder = createSessionRecorder()

      await expect(recorder.start()).rejects.toThrow('Recording unavailable in this browser')
      expect(recorder.isRecording()).toBe(false)
    })

    it('is a no-op when already recording', async () => {
      const recorder = createSessionRecorder()

      await recorder.start()
      await recorder.start()

      expect(web.getUserMedia).toHaveBeenCalledTimes(1)
      expect(web.FakeMediaRecorder.instances).toHaveLength(1)
      expect(recorder.isRecording()).toBe(true)
    })
  })

  describe('stop', () => {
    it('returns an empty take when never started', async () => {
      const recorder = createSessionRecorder()

      const take = await recorder.stop()

      expect(take).toEqual({ durationMs: 0, audioBytes: new Uint8Array(0), mimeType: 'audio/webm' })
      expect(recorder.isRecording()).toBe(false)
    })

    it('collects recorded chunks, stops the stream tracks, and returns the bytes', async () => {
      const recorder = createSessionRecorder()
      await recorder.start()
      const instance = web.FakeMediaRecorder.instances[0]!
      instance.ondataavailable!({ data: new Blob(['hello'], { type: 'audio/webm' }) })

      const take = await recorder.stop()

      expect(instance.stop).toHaveBeenCalledTimes(1)
      expect(take.audioBytes).toEqual(helloBytes)
      expect(take.mimeType).toBe('audio/webm;codecs=opus')
      expect(take.durationMs).toBeGreaterThanOrEqual(0)
      expect(web.tracks.first.stop).toHaveBeenCalledTimes(1)
      expect(web.tracks.second.stop).toHaveBeenCalledTimes(1)
      expect(recorder.isRecording()).toBe(false)
    })

    it('returns an empty byte take when no chunks arrived', async () => {
      const recorder = createSessionRecorder()
      await recorder.start()

      const take = await recorder.stop()

      expect(take.audioBytes).toEqual(new Uint8Array(0))
      expect(take.mimeType).toBe('audio/webm;codecs=opus')
      expect(take.durationMs).toBeGreaterThanOrEqual(0)
      expect(recorder.isRecording()).toBe(false)
    })

    it('returns an empty take when stopped twice', async () => {
      const recorder = createSessionRecorder()
      await recorder.start()
      instanceData()

      const first = await recorder.stop()
      const second = await recorder.stop()

      expect(first.mimeType).toBe('audio/webm;codecs=opus')
      expect(second).toEqual({ durationMs: 0, audioBytes: new Uint8Array(0), mimeType: 'audio/webm' })
      expect(web.FakeMediaRecorder.instances[0]!.stop).toHaveBeenCalledTimes(1)
    })
  })
})

function instanceData(): void {
  web.FakeMediaRecorder.instances[0]!.ondataavailable!({
    data: new Blob(['hello'], { type: 'audio/webm' }),
  })
}
