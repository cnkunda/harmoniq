import { Audio } from 'expo-av'

import type { StemDefinition, StemMixer } from './mixerTypes'
import { assertStemDefinitions } from './mixerTypes'

const LOG = '[StemMixer.native]'

function clampGain(g: number): number {
  if (Number.isNaN(g)) {
    throw new Error(`${LOG} gain is NaN`)
  }
  return Math.min(1, Math.max(0, g))
}

function clampRate(r: number): number {
  if (Number.isNaN(r)) return 1
  /** expo-av typically supports ~0.01–32; keep listen step conservative */
  return Math.min(2, Math.max(0.25, r))
}

class ExpoParallelStemMixer implements StemMixer {
  private stems = new Map<string, { sound: Audio.Sound; gain: number }>()
  private durationSec = 0
  private playbackRate = 1

  async load(stems: StemDefinition[]): Promise<void> {
    assertStemDefinitions(stems)
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
        const source =
          def.uri != null
            ? { uri: def.uri }
            : (def.source as number)
        const { sound } = await Audio.Sound.createAsync(source, {
          shouldPlay: false,
          isLooping: true,
          volume: 1,
        })
        created.push({ id: def.id, sound })
        this.stems.set(def.id, { sound, gain: 1 })
      }

      let maxDur = 0
      for (const { sound } of created) {
        const st = await sound.getStatusAsync()
        if (st.isLoaded && st.durationMillis != null) {
          maxDur = Math.max(maxDur, st.durationMillis / 1000)
        }
      }
      this.durationSec = maxDur
      this.playbackRate = 1
      console.info(`${LOG} load OK duration≈${this.durationSec.toFixed(2)}s`)
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
        await sound.setRateAsync(this.playbackRate, true, Audio.PitchCorrectionQuality.Medium)
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

  async seek(positionSeconds: number): Promise<void> {
    if (this.stems.size === 0) return
    const d = this.durationSec || 0
    const wrapped = d > 0 ? ((positionSeconds % d) + d) % d : Math.max(0, positionSeconds)
    const ms = wrapped * 1000
    await Promise.all(
      [...this.stems.values()].map(({ sound }) => sound.setPositionAsync(ms)),
    )
  }

  async setPlaybackRate(rate: number): Promise<void> {
    this.playbackRate = clampRate(rate)
    await Promise.all(
      [...this.stems.values()].map(({ sound }) =>
        sound.setRateAsync(this.playbackRate, true, Audio.PitchCorrectionQuality.Medium),
      ),
    )
  }

  async getPositionSeconds(): Promise<number> {
    const first = [...this.stems.values()][0]
    if (!first) return 0
    const st = await first.sound.getStatusAsync()
    if (!st.isLoaded || st.positionMillis == null) return 0
    return st.positionMillis / 1000
  }

  getDurationSeconds(): number {
    return this.durationSec
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
    this.durationSec = 0
  }
}

export function createStemMixer(): StemMixer {
  return new ExpoParallelStemMixer()
}
