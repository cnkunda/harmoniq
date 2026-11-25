import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Platform } from 'react-native'

const expoAv = vi.hoisted(() => ({
  setAudioModeAsync: vi.fn(),
}))

vi.mock('expo-av', () => ({
  Audio: { setAudioModeAsync: expoAv.setAudioModeAsync },
}))

type AudioManager = typeof import('@/src/audio/GlobalAudioManager')['globalAudioManager']

const originalPlatformOS = Platform.OS

async function loadManager(): Promise<AudioManager> {
  vi.resetModules()
  const mod = await import('@/src/audio/GlobalAudioManager')
  return mod.globalAudioManager
}

beforeEach(() => {
  expoAv.setAudioModeAsync.mockReset()
  Platform.OS = originalPlatformOS
  vi.spyOn(console, 'info').mockImplementation(() => {})
  vi.spyOn(console, 'debug').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  Platform.OS = originalPlatformOS
  vi.restoreAllMocks()
})

describe('GlobalAudioManager', () => {
  it('registers instances and counts them by type', async () => {
    const manager = await loadManager()
    manager.registerInstance('a', 'expo-sound', { id: 'a' }, async () => {})
    manager.registerInstance('b', 'expo-recording', { id: 'b' }, async () => {})
    manager.registerInstance('c', 'expo-sound', { id: 'c' }, async () => {})

    expect(manager.getInstanceCount()).toBe(3)
    expect(manager.getInstanceCount('expo-sound')).toBe(2)
    expect(manager.getInstanceCount('expo-recording')).toBe(1)
    expect(manager.getInstanceCount('audio-api-manager')).toBe(0)
  })

  it('reports diagnostic info for all registered instances', async () => {
    const manager = await loadManager()
    manager.registerInstance('a', 'expo-sound', { id: 'a' }, async () => {})
    manager.registerInstance('b', 'audio-api-recorder', { id: 'b' }, async () => {})

    const info = manager.getDiagnosticInfo()
    expect(info.totalInstances).toBe(2)
    expect(info.instancesByType['expo-sound']).toBe(1)
    expect(info.instancesByType['audio-api-recorder']).toBe(1)
    expect(info.instancesByType['expo-recording']).toBe(0)
    expect(info.instancesByType['audio-api-manager']).toBe(0)
    expect(info.instanceIds).toEqual(['a', 'b'])
    expect(info.currentAudioMode).toBeNull()
  })

  it('cleans up the previous entry when the same id is registered again', async () => {
    const firstCleanup = vi.fn(async () => {})
    const secondCleanup = vi.fn(async () => {})
    const manager = await loadManager()

    manager.registerInstance('dup', 'expo-sound', { n: 1 }, firstCleanup)
    manager.registerInstance('dup', 'expo-sound', { n: 2 }, secondCleanup)

    await vi.waitFor(() => expect(firstCleanup).toHaveBeenCalledTimes(1))
    expect(manager.getInstanceCount()).toBe(1)
    expect(manager.getInstanceCount('expo-sound')).toBe(1)
    expect(secondCleanup).not.toHaveBeenCalled()
  })

  it('unregisters an instance and runs its cleanup', async () => {
    const cleanup = vi.fn(async () => {})
    const manager = await loadManager()
    manager.registerInstance('a', 'expo-sound', {}, cleanup)

    await manager.unregisterInstance('a')

    expect(cleanup).toHaveBeenCalledTimes(1)
    expect(manager.getInstanceCount()).toBe(0)
  })

  it('warns without throwing when unregistering an unknown id', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const manager = await loadManager()

    await manager.unregisterInstance('missing')

    expect(warnSpy).toHaveBeenCalledTimes(1)
    expect(manager.getInstanceCount()).toBe(0)
  })

  it('still removes the entry when its cleanup rejects', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const manager = await loadManager()
    manager.registerInstance(
      'bad',
      'expo-sound',
      {},
      async () => {
        throw new Error('cleanup boom')
      },
    )

    await manager.unregisterInstance('bad')

    expect(errorSpy).toHaveBeenCalledTimes(1)
    expect(manager.getInstanceCount()).toBe(0)
  })

  describe('setAudioMode', () => {
    it('no-ops on web', async () => {
      Platform.OS = 'web'
      const manager = await loadManager()

      await manager.setAudioMode({ allowsRecordingIOS: true })

      expect(expoAv.setAudioModeAsync).not.toHaveBeenCalled()
      expect(manager.getDiagnosticInfo().currentAudioMode).toBeNull()
    })

    it('applies the mode once and skips an identical mode', async () => {
      const manager = await loadManager()
      const mode = { playsInSilentModeIOS: true, allowsRecordingIOS: true }

      await manager.setAudioMode(mode)
      await manager.setAudioMode({ ...mode })

      expect(expoAv.setAudioModeAsync).toHaveBeenCalledTimes(1)
      expect(expoAv.setAudioModeAsync).toHaveBeenCalledWith(mode)
      expect(manager.getDiagnosticInfo().currentAudioMode).toEqual(mode)
    })

    it('applies a changed mode again', async () => {
      const manager = await loadManager()

      await manager.setAudioMode({ playsInSilentModeIOS: true })
      await manager.setAudioMode({ playsInSilentModeIOS: true, allowsRecordingIOS: true })

      expect(expoAv.setAudioModeAsync).toHaveBeenCalledTimes(2)
    })

    it('rethrows when expo-av rejects', async () => {
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      expoAv.setAudioModeAsync.mockRejectedValueOnce(new Error('mode boom'))
      const manager = await loadManager()

      await expect(manager.setAudioMode({ playsInSilentModeIOS: true })).rejects.toThrow('mode boom')
      expect(errorSpy).toHaveBeenCalledTimes(1)
      expect(manager.getDiagnosticInfo().currentAudioMode).toBeNull()
    })
  })

  describe('cleanupAll', () => {
    it('cleans up every registered instance', async () => {
      const first = vi.fn(async () => {})
      const second = vi.fn(async () => {})
      const manager = await loadManager()
      manager.registerInstance('a', 'expo-sound', {}, first)
      manager.registerInstance('b', 'expo-recording', {}, second)

      await manager.cleanupAll()

      expect(first).toHaveBeenCalledTimes(1)
      expect(second).toHaveBeenCalledTimes(1)
      expect(manager.getInstanceCount()).toBe(0)
    })

    it('keeps instances whose type is skipped', async () => {
      const kept = vi.fn(async () => {})
      const removed = vi.fn(async () => {})
      const manager = await loadManager()
      manager.registerInstance('a', 'expo-sound', {}, kept)
      manager.registerInstance('b', 'audio-api-recorder', {}, removed)

      await manager.cleanupAll({ skipTypes: ['audio-api-recorder'] })

      expect(kept).toHaveBeenCalledTimes(1)
      expect(removed).not.toHaveBeenCalled()
      expect(manager.getInstanceCount()).toBe(1)
      expect(manager.getInstanceCount('audio-api-recorder')).toBe(1)
    })

    it('continues past a failing cleanup and logs it', async () => {
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      const healthy = vi.fn(async () => {})
      const manager = await loadManager()
      manager.registerInstance(
        'bad',
        'expo-sound',
        {},
        async () => {
          throw new Error('cleanup boom')
        },
      )
      manager.registerInstance('good', 'expo-sound', {}, healthy)

      await manager.cleanupAll()

      expect(errorSpy).toHaveBeenCalledTimes(1)
      expect(healthy).toHaveBeenCalledTimes(1)
      expect(manager.getInstanceCount()).toBe(0)
    })

    it('skips a concurrent cleanup while one is already running', async () => {
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      let releaseCleanup!: () => void
      const gate = new Promise<void>((resolve) => {
        releaseCleanup = resolve
      })
      const manager = await loadManager()
      manager.registerInstance('slow', 'expo-sound', {}, async () => {
        await gate
      })

      const firstRun = manager.cleanupAll()
      const secondRun = await manager.cleanupAll()

      expect(secondRun).toBeUndefined()
      expect(warnSpy).toHaveBeenCalledTimes(1)

      releaseCleanup()
      await firstRun
      expect(manager.getInstanceCount()).toBe(0)
    })
  })

  describe('mode helpers', () => {
    it('resetToPlaybackMode disables recording', async () => {
      const manager = await loadManager()

      await manager.resetToPlaybackMode()

      expect(expoAv.setAudioModeAsync).toHaveBeenCalledWith({
        playsInSilentModeIOS: true,
        allowsRecordingIOS: false,
        staysActiveInBackground: false,
      })
    })

    it('setRecordingMode enables recording', async () => {
      const manager = await loadManager()

      await manager.setRecordingMode()

      expect(expoAv.setAudioModeAsync).toHaveBeenCalledWith({
        playsInSilentModeIOS: true,
        allowsRecordingIOS: true,
        staysActiveInBackground: false,
      })
    })

    it('reuses the mode set by a helper when called twice', async () => {
      const manager = await loadManager()

      await manager.setRecordingMode()
      await manager.setRecordingMode()

      expect(expoAv.setAudioModeAsync).toHaveBeenCalledTimes(1)
    })
  })
})
