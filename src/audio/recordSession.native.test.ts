import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const av = vi.hoisted(() => {
  const state = { prepareError: null as Error | null }
  class FakeRecording {
    static instances: FakeRecording[] = []
    prepareToRecordAsync = vi.fn(async (_options: unknown) => {
      if (state.prepareError) throw state.prepareError
    })
    startAsync = vi.fn(async () => {})
    stopAndUnloadAsync = vi.fn(async () => {})
    getURI = vi.fn((): string | null => 'file:///recording.m4a')
    constructor() {
      FakeRecording.instances.push(this)
    }
  }
  return {
    FakeRecording,
    state,
    requestPermissionsAsync: vi.fn(
      async (): Promise<{ granted: boolean; status: string }> => ({ granted: true, status: 'granted' }),
    ),
    setAudioModeAsync: vi.fn(async (_config: unknown) => {}),
    highQualityPreset: { quality: 'high' as const },
  }
})

vi.mock('expo-av', () => ({
  Audio: {
    Recording: av.FakeRecording,
    requestPermissionsAsync: av.requestPermissionsAsync,
    setAudioModeAsync: av.setAudioModeAsync,
    RecordingOptionsPresets: { HIGH_QUALITY: av.highQualityPreset },
  },
}))

type NativeRecorder = ReturnType<typeof import('@/src/audio/recordSession.native')['createSessionRecorder']>

async function loadRecorder(): Promise<{
  recorder: NativeRecorder
  manager: typeof import('@/src/audio/GlobalAudioManager')['globalAudioManager']
}> {
  vi.resetModules()
  const recorderModule = await import('@/src/audio/recordSession.native')
  const managerModule = await import('@/src/audio/GlobalAudioManager')
  return { recorder: recorderModule.createSessionRecorder(), manager: managerModule.globalAudioManager }
}

const emptyBytes = new Uint8Array(0)

beforeEach(() => {
  av.requestPermissionsAsync.mockReset().mockResolvedValue({ granted: true, status: 'granted' })
  av.setAudioModeAsync.mockReset()
  av.FakeRecording.instances.length = 0
  av.state.prepareError = null
  vi.spyOn(console, 'info').mockImplementation(() => {})
  vi.spyOn(console, 'debug').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('NativeSessionRecorder', () => {
  describe('start', () => {
    it('requests permission, records in high quality, and registers with the audio manager', async () => {
      const { recorder, manager } = await loadRecorder()

      await recorder.start()

      expect(av.requestPermissionsAsync).toHaveBeenCalledTimes(1)
      expect(av.FakeRecording.instances).toHaveLength(1)
      const recording = av.FakeRecording.instances[0]!
      expect(recording.prepareToRecordAsync).toHaveBeenCalledWith(av.highQualityPreset)
      expect(recording.startAsync).toHaveBeenCalledTimes(1)
      expect(recorder.isRecording()).toBe(true)
      expect(av.setAudioModeAsync).toHaveBeenCalledWith(expect.objectContaining({ allowsRecordingIOS: true }))
      expect(manager.getInstanceCount('expo-recording')).toBe(1)
    })

    it('is a no-op when already recording', async () => {
      const { recorder } = await loadRecorder()

      await recorder.start()
      await recorder.start()

      expect(av.requestPermissionsAsync).toHaveBeenCalledTimes(1)
      expect(av.FakeRecording.instances).toHaveLength(1)
      expect(recorder.isRecording()).toBe(true)
    })

    it('throws MIC_PERMISSION_DENIED when permission is refused', async () => {
      av.requestPermissionsAsync.mockResolvedValue({ granted: false, status: 'denied' })
      const { recorder, manager } = await loadRecorder()

      await expect(recorder.start()).rejects.toThrow('MIC_PERMISSION_DENIED')
      expect(recorder.isRecording()).toBe(false)
      expect(av.setAudioModeAsync).not.toHaveBeenCalled()
      expect(av.FakeRecording.instances).toHaveLength(0)
      expect(manager.getInstanceCount()).toBe(0)
    })

    it('propagates a prepare failure and leaves the recorder inactive', async () => {
      av.state.prepareError = new Error('prepare boom')
      const { recorder, manager } = await loadRecorder()

      await expect(recorder.start()).rejects.toThrow('prepare boom')
      expect(recorder.isRecording()).toBe(false)
      expect(manager.getInstanceCount()).toBe(0)
    })
  })

  describe('stop', () => {
    it('returns an empty take when never started', async () => {
      const { recorder } = await loadRecorder()

      const take = await recorder.stop()

      expect(take).toEqual({ durationMs: 0, audioBytes: emptyBytes, mimeType: 'audio/m4a' })
      expect(recorder.isRecording()).toBe(false)
    })

    it('returns fetched bytes, resets the audio mode, and unregisters the instance', async () => {
      const fetchMock = vi.fn(async () => ({
        arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
      }))
      vi.stubGlobal('fetch', fetchMock)
      const { recorder, manager } = await loadRecorder()
      await recorder.start()

      const take = await recorder.stop()

      expect(fetchMock).toHaveBeenCalledWith('file:///recording.m4a')
      expect(take.audioBytes).toEqual(new Uint8Array([1, 2, 3]))
      expect(take.mimeType).toBe('audio/m4a')
      expect(take.durationMs).toBeGreaterThanOrEqual(0)
      expect(recorder.isRecording()).toBe(false)
      expect(av.setAudioModeAsync).toHaveBeenCalledWith(expect.objectContaining({ allowsRecordingIOS: false }))
      await vi.waitFor(() => expect(manager.getInstanceCount('expo-recording')).toBe(0))
    })

    it('returns an empty byte take when the recording has no URI', async () => {
      const fetchMock = vi.fn()
      vi.stubGlobal('fetch', fetchMock)
      const { recorder } = await loadRecorder()
      await recorder.start()
      av.FakeRecording.instances[0]!.getURI.mockReturnValue(null)

      const take = await recorder.stop()

      expect(take.audioBytes).toEqual(emptyBytes)
      expect(take.mimeType).toBe('audio/m4a')
      expect(take.durationMs).toBeGreaterThanOrEqual(0)
      expect(fetchMock).not.toHaveBeenCalled()
      expect(recorder.isRecording()).toBe(false)
    })

    it('returns an empty take when stopped twice', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => ({ arrayBuffer: async () => new Uint8Array([9]).buffer })),
      )
      const { recorder } = await loadRecorder()
      await recorder.start()

      const first = await recorder.stop()
      const second = await recorder.stop()

      expect(first.mimeType).toBe('audio/m4a')
      expect(second).toEqual({ durationMs: 0, audioBytes: emptyBytes, mimeType: 'audio/m4a' })
      expect(av.FakeRecording.instances[0]!.stopAndUnloadAsync).toHaveBeenCalledTimes(1)
    })
  })

  describe('GlobalAudioManager integration', () => {
    it('cleanupAll stops an active recording through the registered cleanup', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => ({ arrayBuffer: async () => new Uint8Array([7]).buffer })),
      )
      const { recorder, manager } = await loadRecorder()
      await recorder.start()
      expect(manager.getInstanceCount('expo-recording')).toBe(1)

      await manager.cleanupAll()

      expect(recorder.isRecording()).toBe(false)
      expect(manager.getInstanceCount('expo-recording')).toBe(0)
      expect(av.FakeRecording.instances[0]!.stopAndUnloadAsync).toHaveBeenCalledTimes(1)
    })
  })
})
