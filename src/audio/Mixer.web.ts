import { Asset } from 'expo-asset'

import type { StemDefinition, StemMixer } from './mixerTypes'
import { assertStemDefinitions } from './mixerTypes'

const LOG = '[StemMixer.web]'

function clampGain(g: number): number {
  if (Number.isNaN(g)) {
    throw new Error(`${LOG} gain is NaN`)
  }
  return Math.min(1, Math.max(0, g))
}

function clampRate(r: number): number {
  if (Number.isNaN(r)) return 1
  return Math.min(2, Math.max(0.25, r))
}

function getAudioContextClass(): typeof AudioContext {
  const w = globalThis as typeof globalThis & {
    AudioContext?: typeof AudioContext
    webkitAudioContext?: typeof AudioContext
  }
  const Ctor = w.AudioContext ?? w.webkitAudioContext
  if (!Ctor) {
    throw new Error(`${LOG} Web Audio API not available`)
  }
  return Ctor
}

async function decodeAssetToBuffer(ctx: AudioContext, sourceModule: number): Promise<AudioBuffer> {
  const asset = Asset.fromModule(sourceModule)
  await asset.downloadAsync()
  const uri = asset.localUri ?? asset.uri
  if (!uri) {
    throw new Error(`${LOG} asset has no URI after downloadAsync()`)
  }

  const res = await fetch(uri)
  if (!res.ok) {
    throw new Error(`${LOG} fetch failed ${res.status} for ${uri}`)
  }
  const raw = await res.arrayBuffer()

  return await new Promise<AudioBuffer>((resolve, reject) => {
    ctx.decodeAudioData(raw.slice(0), resolve, (err) => {
      reject(err ?? new Error(`${LOG} decodeAudioData failed`))
    })
  })
}

async function decodeUrlToBuffer(ctx: AudioContext, uri: string): Promise<AudioBuffer> {
  const res = await fetch(uri)
  if (!res.ok) {
    throw new Error(`${LOG} fetch stem failed ${res.status}`)
  }
  const raw = await res.arrayBuffer()
  return await new Promise<AudioBuffer>((resolve, reject) => {
    ctx.decodeAudioData(raw.slice(0), resolve, (err) => {
      reject(err ?? new Error(`${LOG} decodeAudioData (url) failed`))
    })
  })
}

type StemWebState = {
  label: string
  buffer: AudioBuffer
  gain: GainNode
  /** Active loop sources; cleared on pause */
  sources: AudioBufferSourceNode[]
}

class WebAudioStemMixer implements StemMixer {
  private ctx: AudioContext | null = null
  private stems = new Map<string, StemWebState>()
  private durationSec = 0
  private playbackRate = 1
  private pausedAt = 0
  private playStartCtxTime = 0
  private playing = false

  /** Exposed for metronome scheduling on the same clock. */
  getAudioContext(): AudioContext | null {
    return this.ctx
  }

  async load(stems: StemDefinition[]): Promise<void> {
    assertStemDefinitions(stems)
    if (this.stems.size > 0) {
      throw new Error(`${LOG} already loaded — call unload() first`)
    }
    if (stems.length === 0) {
      throw new Error(`${LOG} load() requires at least one stem`)
    }

    const Ctor = getAudioContextClass()
    this.ctx = new Ctor()
    console.info(`${LOG} AudioContext state=${this.ctx.state}, loading ${stems.length} stem(s)`)

    try {
      let maxDur = 0
      for (const def of stems) {
        const buffer =
          def.uri != null
            ? await decodeUrlToBuffer(this.ctx, def.uri)
            : await decodeAssetToBuffer(this.ctx, def.source as number)
        maxDur = Math.max(maxDur, buffer.duration)
        const gain = this.ctx.createGain()
        gain.gain.value = 1
        gain.connect(this.ctx.destination)
        this.stems.set(def.id, { label: def.label, buffer, gain, sources: [] })
        console.info(
          `${LOG} decoded ${def.id} (${def.label}) duration=${buffer.duration.toFixed(2)}s sr=${buffer.sampleRate}`,
        )
      }
      this.durationSec = maxDur
      this.pausedAt = 0
      this.playbackRate = 1
      this.playing = false
      console.info(`${LOG} load OK duration=${this.durationSec.toFixed(2)}s`)
    } catch (e) {
      console.error(`${LOG} load failed`, e)
      await this.unload()
      throw e
    }
  }

  private startLoopSources(): void {
    if (!this.ctx) {
      throw new Error(`${LOG} internal: missing context`)
    }
    for (const state of this.stems.values()) {
      if (state.sources.length > 0) {
        continue
      }
      const src = this.ctx.createBufferSource()
      src.buffer = state.buffer
      src.loop = true
      src.loopStart = 0
      src.loopEnd = state.buffer.duration
      src.playbackRate.value = this.playbackRate
      src.connect(state.gain)
      src.start(0, this.pausedAt)
      state.sources.push(src)
    }
  }

  private stopLoopSources(): void {
    for (const state of this.stems.values()) {
      for (const src of state.sources) {
        try {
          src.stop(0)
        } catch {
          /* already stopped */
        }
        src.disconnect()
      }
      state.sources = []
    }
  }

  async play(): Promise<void> {
    if (!this.ctx || this.stems.size === 0) {
      throw new Error(`${LOG} play() called before load()`)
    }
    if (this.ctx.state === 'suspended') {
      await this.ctx.resume()
      console.info(`${LOG} AudioContext resumed -> ${this.ctx.state}`)
    }
    this.stopLoopSources()
    this.playStartCtxTime = this.ctx.currentTime
    this.playing = true
    this.startLoopSources()
    console.info(`${LOG} play from ${this.pausedAt.toFixed(3)}s rate=${this.playbackRate}`)
  }

  async pause(): Promise<void> {
    if (!this.ctx || this.stems.size === 0) {
      throw new Error(`${LOG} pause() called before load()`)
    }
    if (this.playing) {
      const elapsed = (this.ctx.currentTime - this.playStartCtxTime) * this.playbackRate
      const d = this.durationSec || 1
      this.pausedAt = (this.pausedAt + elapsed) % d
    }
    this.stopLoopSources()
    this.playing = false
    console.info(`${LOG} pause at ${this.pausedAt.toFixed(3)}s`)
  }

  async seek(positionSeconds: number): Promise<void> {
    if (!this.ctx || this.stems.size === 0) {
      return
    }
    const d = this.durationSec || 0
    if (d <= 0) return
    const wrapped = ((positionSeconds % d) + d) % d
    const wasPlaying = this.playing
    if (wasPlaying) {
      this.stopLoopSources()
      this.playing = false
    }
    this.pausedAt = wrapped
    if (wasPlaying) {
      await this.play()
    }
  }

  async setPlaybackRate(rate: number): Promise<void> {
    this.playbackRate = clampRate(rate)
    if (!this.ctx || !this.playing) {
      return
    }
    const pos = await this.getPositionSeconds()
    this.stopLoopSources()
    this.playing = false
    this.pausedAt = pos
    await this.play()
  }

  getPositionSecondsNow(): number {
    if (!this.ctx || this.stems.size === 0) {
      return this.pausedAt
    }
    const d = this.durationSec || 1
    if (this.playing) {
      const elapsed = (this.ctx.currentTime - this.playStartCtxTime) * this.playbackRate
      return (this.pausedAt + elapsed) % d
    }
    return this.pausedAt
  }

  async getPositionSeconds(): Promise<number> {
    return this.getPositionSecondsNow()
  }

  getDurationSeconds(): number {
    return this.durationSec
  }

  async setStemGain(stemId: string, linearGain: number): Promise<void> {
    const state = this.stems.get(stemId)
    if (!state) {
      throw new Error(`${LOG} unknown stem id: ${stemId}`)
    }
    const g = clampGain(linearGain)
    state.gain.gain.value = g
    console.info(`${LOG} setStemGain ${stemId} -> ${g}`)
  }

  async unload(): Promise<void> {
    this.stopLoopSources()
    for (const state of this.stems.values()) {
      state.gain.disconnect()
    }
    this.stems.clear()
    this.durationSec = 0
    this.pausedAt = 0
    this.playing = false
    if (this.ctx) {
      await this.ctx.close().catch((err) => console.error(`${LOG} context.close`, err))
      console.info(`${LOG} AudioContext closed`)
    }
    this.ctx = null
  }
}

export function createStemMixer(): StemMixer {
  return new WebAudioStemMixer()
}
