import { Audio } from 'expo-av'

import type { StemDefinition, StemMixer } from './mixerTypes'

const LOG = '[StemMixer.native]'

function clampGain(g: number): number {
  if (Number.isNaN(g)) {
    throw new Error(`${LOG} gain is NaN`)
  }
  return Math.min(1, Math.max(0, g))
}

class ExpoParallelStemMixer implements StemMixer {
  private stems = new Map<string, { sound: Audio.Sound; gain: number }>()

  async load(stems: StemDefinition[]): Promise<void> {
    if (this.stems.size > 0) {
      throw new Error(`${LOG} already loaded — call unload() first`)
    }
    if (stems.length === 0) {
      throw new Error(`${LOG} load() requires at least one stem`)
    }

    await Audio.setAudioModeAsync({
      playsInSilentModeIOS: true,
      allowsRecordingIOS: false,
    })

    console.info(`${LOG} loading ${stems.length} stem(s):`, stems.map((s) => s.id).join(', '))

    const created: { id: string; sound: Audio.Sound }[] = []

    try {
      for (const def of stems) {
        const { sound } = await Audio.Sound.createAsync(def.source, {
          shouldPlay: false,
          isLooping: true,
          volume: 1,
        })
        created.push({ id: def.id, sound })
        this.stems.set(def.id, { sound, gain: 1 })
      }
      console.info(`${LOG} load OK`)
    } catch (e) {
      console.error(`${LOG} load failed, unloading partial`, e)
      for (const { sound } of created) {
        await sound.unloadAsync().catch(() => {})
      }
      this.stems.clear()
      throw e
    }
  }

  async play(): Promise<void> {
    if (this.stems.size === 0) {
      throw new Error(`${LOG} play() called before load()`)
    }
    console.info(`${LOG} play`)
    await Promise.all(
      [...this.stems.values()].map(async ({ sound, gain }) => {
        await sound.setVolumeAsync(gain)
        await sound.playAsync()
      }),
    )
  }

  async pause(): Promise<void> {
    if (this.stems.size === 0) {
      throw new Error(`${LOG} pause() called before load()`)
    }
    console.info(`${LOG} pause`)
    await Promise.all([...this.stems.values()].map(({ sound }) => sound.pauseAsync()))
  }

  async setStemGain(stemId: string, linearGain: number): Promise<void> {
    const entry = this.stems.get(stemId)
    if (!entry) {
      throw new Error(`${LOG} unknown stem id: ${stemId}`)
    }
    const g = clampGain(linearGain)
    entry.gain = g
    console.info(`${LOG} setStemGain ${stemId} -> ${g}`)
    await entry.sound.setVolumeAsync(g)
  }

  async unload(): Promise<void> {
    if (this.stems.size === 0) {
      console.info(`${LOG} unload (no-op, empty)`)
      return
    }
    console.info(`${LOG} unload ${this.stems.size} sound(s)`)
    await Promise.all(
      [...this.stems.values()].map(({ sound }) =>
        sound.unloadAsync().catch((err) => {
          console.error(`${LOG} unloadAsync error`, err)
        }),
      ),
    )
    this.stems.clear()
  }
}

export function createStemMixer(): StemMixer {
  return new ExpoParallelStemMixer()
}
