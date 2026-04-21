import type { StemDefinition } from '@/src/audio/mixerTypes'

import { GHOST_STEM_ID } from '@/src/audio/ghostConstants'

function getAudioContextClass(): typeof AudioContext {
  const w = globalThis as typeof globalThis & {
    AudioContext?: typeof AudioContext
    webkitAudioContext?: typeof AudioContext
  }
  const Ctor = w.AudioContext ?? w.webkitAudioContext
  if (!Ctor) {
    throw new Error('[ghostStem.web] Web Audio API not available')
  }
  return Ctor
}

async function decodeUrlToBuffer(ctx: AudioContext, uri: string): Promise<AudioBuffer> {
  const res = await fetch(uri)
  if (!res.ok) {
    throw new Error(`[ghostStem.web] fetch failed ${res.status}`)
  }
  const raw = await res.arrayBuffer()
  return await new Promise<AudioBuffer>((resolve, reject) => {
    ctx.decodeAudioData(raw.slice(0), resolve, (err) => reject(err ?? new Error('decodeAudioData')))
  })
}

function mixDownToMono(buffer: AudioBuffer): Float32Array {
  const ch = buffer.numberOfChannels
  const len = buffer.length
  const out = new Float32Array(len)
  for (let c = 0; c < ch; c++) {
    const d = buffer.getChannelData(c)
    for (let i = 0; i < len; i++) out[i] += d[i]
  }
  if (ch > 1) {
    for (let i = 0; i < len; i++) out[i] /= ch
  }
  return out
}

function writeString(view: DataView, offset: number, str: string) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i))
  }
}

function floatTo16BitPCM(view: DataView, offset: number, input: Float32Array) {
  for (let i = 0; i < input.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, input[i] ?? 0))
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
}

function encodeWavMono(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  writeString(view, 0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeString(view, 8, 'WAVE')
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(view, 36, 'data')
  view.setUint32(40, samples.length * 2, true)
  floatTo16BitPCM(view, 44, samples)
  return new Blob([buffer], { type: 'audio/wav' })
}

/**
 * Places ghost samples starting at `anchorSec` on a timeline as long as the backing mixer,
 * then encodes WAV so `StemMixer.web` loop stays phase-locked without drift.
 */
export async function buildPaddedGhostStemBlobUrl(opts: {
  ghostPlaybackUri: string
  anchorSec: number
  masterDurationSec: number
}): Promise<string | null> {
  const Ctor = getAudioContextClass()
  const ctx = new Ctor()
  try {
    const ghostBuf = await decodeUrlToBuffer(ctx, opts.ghostPlaybackUri)
    const rate = ghostBuf.sampleRate
    const masterSamples = Math.max(1, Math.ceil(opts.masterDurationSec * rate))
    const monoGhost = mixDownToMono(ghostBuf)
    const padded = new Float32Array(masterSamples)
    const startSample = Math.max(0, Math.floor(opts.anchorSec * rate))
    for (let i = 0; i < monoGhost.length && startSample + i < masterSamples; i++) {
      padded[startSample + i] = monoGhost[i] ?? 0
    }
    const wav = encodeWavMono(padded, rate)
    return URL.createObjectURL(wav)
  } catch (e) {
    console.error('[ghostStem.web] pad/re-encode failed', e)
    return null
  } finally {
    await ctx.close().catch(() => {})
  }
}

export function ghostStemDefinition(uri: string): StemDefinition {
  return { id: GHOST_STEM_ID, label: 'Ghost take', uri }
}
