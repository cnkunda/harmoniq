import { Asset } from 'expo-asset'

import type { StemDefinition, StemMixer } from './mixerTypes'

const LOG = '[StemMixer.web]'

function clampGain(g: number): number {
  if (Number.isNaN(g)) {
    throw new Error(`${LOG} gain is NaN`)
  }
  return Math.min(1, Math.max(0, g))
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

  async load(stems: StemDefinition[]): Promise<void> {
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
      for (const def of stems) {
        const buffer = await decodeAssetToBuffer(this.ctx, def.source)
        const gain = this.ctx.createGain()
        gain.gain.value = 1
        gain.connect(this.ctx.destination)
        this.stems.set(def.id, { label: def.label, buffer, gain, sources: [] })
        console.info(`${LOG} decoded ${def.id} (${def.label}) duration=${buffer.duration.toFixed(2)}s sr=${buffer.sampleRate}`)
      }
      console.info(`${LOG} load OK`)
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
      src.connect(state.gain)
      src.start(0)
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
    this.startLoopSources()
    console.info(`${LOG} play (looping)`)
  }

  async pause(): Promise<void> {
    if (!this.ctx || this.stems.size === 0) {
      throw new Error(`${LOG} pause() called before load()`)
    }
    this.stopLoopSources()
    console.info(`${LOG} pause (sources stopped)`)
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
