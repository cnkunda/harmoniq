import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

import { describe, it, expect } from 'vitest'

import {
  computeCqt,
  computeCqtFrame,
  CqtStreamer,
  FMIN,
  getMaxHalfLen,
} from '@/src/chord/computeCqt'
import { BINS_PER_OCTAVE, CHROMA_BINS, HOP_LENGTH, TARGET_SR } from '@/src/chord/cqtConstants'

function sine(freq: number, n: number, sr = TARGET_SR): Float32Array {
  const x = new Float32Array(n)
  for (let i = 0; i < n; i++) x[i] = Math.sin((2 * Math.PI * freq * i) / sr)
  return x
}

function argmax(v: Float32Array, offset = 0, len = v.length): number {
  let bi = 0
  let bv = v[offset] ?? -Infinity
  for (let i = 1; i < len; i++) {
    const p = v[offset + i] ?? -Infinity
    if (p > bv) {
      bv = p
      bi = i
    }
  }
  return bi
}

function cosineSim(a: number[], b: number[]): number {
  let dot = 0
  let na = 0
  let nb = 0
  for (let i = 0; i < a.length; i++) {
    dot += a[i]! * b[i]!
    na += a[i]! * a[i]!
    nb += b[i]! * b[i]!
  }
  return dot / (Math.sqrt(na) * Math.sqrt(nb) + 1e-12)
}

describe('computeCqt frequency mapping (librosa-aligned kernels)', () => {
  // A pure tone at a bin's centre frequency should peak at (or adjacent to) that bin.
  const testBins = [48, 72, 96, 120]
  const maxHalf = getMaxHalfLen()
  const len = 2 * maxHalf + 1

  for (const k of testBins) {
    it(`localizes a pure tone at bin ${k} within ±1 bin`, () => {
      const freq = FMIN * Math.pow(2, k / BINS_PER_OCTAVE)
      const frame = computeCqtFrame(sine(freq, len), maxHalf)
      const peak = argmax(frame)
      expect(Math.abs(peak - k)).toBeLessThanOrEqual(1)
    })
  }

  it('places octave-related tones one octave (24 bins) apart', () => {
    const kLow = 60
    const fLow = FMIN * Math.pow(2, kLow / BINS_PER_OCTAVE)
    const fHigh = fLow * 2
    const low = argmax(computeCqtFrame(sine(fLow, len), maxHalf))
    const high = argmax(computeCqtFrame(sine(fHigh, len), maxHalf))
    expect(Math.abs(high - low - BINS_PER_OCTAVE)).toBeLessThanOrEqual(1)
  })

  it('produces finite, non-negative magnitudes with reflect padding at edges', () => {
    const frame = computeCqtFrame(sine(220, 4096), 0) // centre at 0 → exercises reflect
    for (let i = 0; i < frame.length; i++) {
      expect(Number.isFinite(frame[i]!)).toBe(true)
      expect(frame[i]!).toBeGreaterThanOrEqual(0)
    }
  })
})

describe('computeCqt offline shape', () => {
  it('emits floor(len/hop) frames of CHROMA_BINS each', () => {
    const n = HOP_LENGTH * 5 + 123
    const out = computeCqt(sine(196, n))
    const frames = Math.floor(n / HOP_LENGTH)
    expect(out.length).toBe(frames * CHROMA_BINS)
  })
})

describe('CqtStreamer incremental path matches offline computeCqtFrame', () => {
  it('the first streamed frame (centre 0) equals the offline frame', () => {
    const maxHalf = getMaxHalfLen()
    const chunk = sine(147, maxHalf + 1) // enough to emit exactly the centre-0 frame
    const streamer = new CqtStreamer()
    streamer.push(chunk)

    expect(streamer.frameCount).toBe(1)

    const win = streamer.getWindow()
    // Last frame in the window is the most recent (only) produced frame.
    const streamed = win.subarray(win.length - CHROMA_BINS)
    const offline = computeCqtFrame(chunk, 0)

    for (let b = 0; b < CHROMA_BINS; b++) {
      expect(Math.abs(streamed[b]! - offline[b]!)).toBeLessThan(1e-4)
    }
  })

  it('reports warm state only after WINDOW frames', () => {
    const streamer = new CqtStreamer()
    expect(streamer.isWarm).toBe(false)
    expect(streamer.warmFraction).toBe(0)
  })
})

// Optional exact-value parity against a librosa-generated fixture.
// Generate with: python backend/scripts/gen_cqt_fixture.py
const fixturePath = path.resolve(__dirname, '__fixtures__/cqt_parity.json')

describe.skipIf(!existsSync(fixturePath))('librosa parity fixture', () => {
  interface FixtureCase {
    name: string
    kind: 'sine'
    freq: number
    num_samples: number
    frame_indices: number[]
    frames: number[][]
  }
  interface Fixture {
    sample_rate: number
    hop: number
    n_bins: number
    cases: FixtureCase[]
  }

  const fixture: Fixture = existsSync(fixturePath)
    ? JSON.parse(readFileSync(fixturePath, 'utf8'))
    : { sample_rate: TARGET_SR, hop: HOP_LENGTH, n_bins: CHROMA_BINS, cases: [] }

  for (const c of fixture.cases) {
    it(`matches librosa for ${c.name} (cosine ≥ 0.9, dominant bin ±1)`, () => {
      const out = computeCqt(sine(c.freq, c.num_samples, fixture.sample_rate))
      c.frame_indices.forEach((fi, j) => {
        const tsFrame = Array.from(out.subarray(fi * CHROMA_BINS, (fi + 1) * CHROMA_BINS))
        const ref = c.frames[j]!
        // L1-normalize both (the model input is L1-normalized per frame).
        const l1 = (v: number[]) => {
          const s = v.reduce((a, x) => a + Math.abs(x), 0) || 1
          return v.map((x) => x / s)
        }
        const a = l1(tsFrame)
        const b = l1(ref)
        expect(cosineSim(a, b)).toBeGreaterThanOrEqual(0.9)
        const peakA = a.indexOf(Math.max(...a))
        const peakB = b.indexOf(Math.max(...b))
        expect(Math.abs(peakA - peakB)).toBeLessThanOrEqual(1)
      })
    })
  }
})
