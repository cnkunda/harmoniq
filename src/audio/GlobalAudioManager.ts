import { Audio } from 'expo-av'
import { Platform } from 'react-native'

import { createLogger } from '@/src/utils/logger'

const log = createLogger('[GlobalAudioManager]')

type AudioInstanceType = 'expo-sound' | 'expo-recording' | 'audio-api-recorder' | 'audio-api-manager'

interface AudioInstance {
  id: string
  type: AudioInstanceType
  instance: unknown
  cleanup: () => Promise<void>
  createdAt: number
}

interface AudioModeConfig {
  playsInSilentModeIOS?: boolean
  allowsRecordingIOS?: boolean
  staysActiveInBackground?: boolean
}

class GlobalAudioManager {
  private static instance: GlobalAudioManager | null = null
  private audioInstances = new Map<string, AudioInstance>()
  private currentAudioMode: AudioModeConfig | null = null
  private cleanupInProgress = false

  private constructor() {
    log.info(`singleton initialized`)
  }

  static getInstance(): GlobalAudioManager {
    if (!GlobalAudioManager.instance) {
      GlobalAudioManager.instance = new GlobalAudioManager()
    }
    return GlobalAudioManager.instance
  }

  /**
   * Register an audio instance with the manager.
   * @param id Unique identifier for the instance
   * @param type Type of audio instance
   * @param instance The actual audio instance object
   * @param cleanup Async cleanup function to unload/stop the instance
   */
  registerInstance(
    id: string,
    type: AudioInstanceType,
    instance: unknown,
    cleanup: () => Promise<void>,
  ): void {
    if (this.audioInstances.has(id)) {
      log.warn(`instance ${id} already registered, replacing`)
      void this.unregisterInstance(id)
    }

    this.audioInstances.set(id, {
      id,
      type,
      instance,
      cleanup,
      createdAt: Date.now(),
    })
    log.info(`registered ${type} instance: ${id} (total: ${this.audioInstances.size})`)
  }

  /**
   * Unregister and cleanup a specific audio instance.
   */
  async unregisterInstance(id: string): Promise<void> {
    const entry = this.audioInstances.get(id)
    if (!entry) {
      log.warn(`instance ${id} not found for unregistration`)
      return
    }

    log.info(`unregistering ${entry.type} instance: ${id}`)
    try {
      await entry.cleanup()
    } catch (err) {
      log.error(`cleanup failed for ${id}:`, err)
    }
    // A re-registration while cleanup was in flight owns this id now — only
    // remove the entry if it is still the one we just cleaned up.
    if (this.audioInstances.get(id) === entry) {
      this.audioInstances.delete(id)
    }
    log.info(`unregistered ${id} (remaining: ${this.audioInstances.size})`)
  }

  /**
   * Centralized Audio.setAudioModeAsync to prevent conflicts.
   * Only updates if the mode differs from current mode.
   */
  async setAudioMode(config: AudioModeConfig): Promise<void> {
    if (Platform.OS === 'web') {
      // Web doesn't use expo-av audio mode
      return
    }

    const configStr = JSON.stringify(config)
    const currentStr = this.currentAudioMode ? JSON.stringify(this.currentAudioMode) : null

    if (configStr === currentStr) {
      log.debug(`audio mode unchanged, skipping setAudioModeAsync`)
      return
    }

    log.info(`setting audio mode:`, config)
    try {
      await Audio.setAudioModeAsync(config)
      this.currentAudioMode = config
      log.info(`audio mode set successfully`)
    } catch (err) {
      log.error(`failed to set audio mode:`, err)
      throw err
    }
  }

  /**
   * Cleanup all audio instances for hot-swap scenarios (e.g., deep-linking).
   * This is called when navigating between different audio contexts.
   */
  async cleanupAll(options?: { skipTypes?: AudioInstanceType[] }): Promise<void> {
    if (this.cleanupInProgress) {
      log.warn(`cleanup already in progress, skipping`)
      return
    }

    this.cleanupInProgress = true
    log.info(`starting cleanup of all instances (total: ${this.audioInstances.size})`)

    const skipTypes = options?.skipTypes ?? []
    const entries = Array.from(this.audioInstances.entries())

    for (const [id, entry] of entries) {
      if (skipTypes.includes(entry.type)) {
        log.debug(`skipping ${entry.type} instance: ${id}`)
        continue
      }

      try {
        await entry.cleanup()
        log.info(`cleaned up ${entry.type} instance: ${id}`)
      } catch (err) {
        log.error(`cleanup failed for ${id}:`, err)
      }
      this.audioInstances.delete(id)
    }

    this.cleanupInProgress = false
    log.info(`cleanup complete (remaining: ${this.audioInstances.size})`)
  }

  /**
   * Get count of registered instances by type.
   */
  getInstanceCount(type?: AudioInstanceType): number {
    if (!type) {
      return this.audioInstances.size
    }
    return Array.from(this.audioInstances.values()).filter((e) => e.type === type).length
  }

  /**
   * Get diagnostic info for debugging audio state.
   */
  getDiagnosticInfo(): {
    totalInstances: number
    instancesByType: Record<AudioInstanceType, number>
    currentAudioMode: AudioModeConfig | null
    instanceIds: string[]
  } {
    const instancesByType: Record<AudioInstanceType, number> = {
      'expo-sound': 0,
      'expo-recording': 0,
      'audio-api-recorder': 0,
      'audio-api-manager': 0,
    }

    for (const entry of this.audioInstances.values()) {
      instancesByType[entry.type] += 1
    }

    return {
      totalInstances: this.audioInstances.size,
      instancesByType,
      currentAudioMode: this.currentAudioMode,
      instanceIds: Array.from(this.audioInstances.keys()),
    }
  }

  /**
   * Reset audio mode to default playback mode.
   * Useful when switching from recording to playback contexts.
   */
  async resetToPlaybackMode(): Promise<void> {
    await this.setAudioMode({
      playsInSilentModeIOS: true,
      allowsRecordingIOS: false,
      staysActiveInBackground: false,
    })
  }

  /**
   * Set audio mode for recording contexts.
   */
  async setRecordingMode(): Promise<void> {
    await this.setAudioMode({
      playsInSilentModeIOS: true,
      allowsRecordingIOS: true,
      staysActiveInBackground: false,
    })
  }
}

export const globalAudioManager = GlobalAudioManager.getInstance()
