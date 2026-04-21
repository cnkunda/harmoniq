/** Decode arbitrary browser-supported audio bytes → normalized peak envelope (0–1 per bin). */
export async function peaksFromAudioUint8(bytes: Uint8Array, bins: number): Promise<number[] | null> {
  const w = globalThis as typeof globalThis & {
    AudioContext?: typeof AudioContext
    webkitAudioContext?: typeof AudioContext
  }
  const Ctor = w.AudioContext ?? w.webkitAudioContext
  if (!Ctor || bins <= 0) return null
  const ctx = new Ctor()
  try {
    const raw = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
    const buf = await new Promise<AudioBuffer>((resolve, reject) => {
      ctx.decodeAudioData(raw as ArrayBuffer, resolve, (err) => reject(err ?? new Error('decodeAudioData')))
    })
    return peaksFromAudioBuffer(buf, bins)
  } catch {
    return null
  } finally {
    await ctx.close().catch(() => {})
  }
}

export function peaksFromAudioBuffer(buf: AudioBuffer, bins: number): number[] {
  const ch0 = buf.numberOfChannels > 0 ? buf.getChannelData(0) : new Float32Array(0)
  const len = ch0.length
  const bucket = Math.max(1, Math.floor(len / bins))
  const out: number[] = []
  for (let b = 0; b < bins; b++) {
    let max = 0
    const start = b * bucket
    const end = Math.min(len, start + bucket)
    for (let i = start; i < end; i++) max = Math.max(max, Math.abs(ch0[i] ?? 0))
    out.push(max)
  }
  const m = Math.max(...out, 1e-9)
  return out.map((x) => x / m)
}
