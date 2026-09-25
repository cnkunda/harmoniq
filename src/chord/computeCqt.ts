import { BINS_PER_OCTAVE, CHROMA_BINS, TARGET_SR, HOP_LENGTH, WINDOW } from './cqtConstants'

/**
 * Constant-Q Transform for on-device chord detection.
 *
 * Mirrors the training-time features produced by `backend/app/chord_inference.py`
 * (`librosa.cqt` → magnitude → per-frame L1 normalization). To stay close to
 * librosa's output distribution the kernels use:
 *   - fmin = librosa.note_to_hz('C1') (32.70319566 Hz)
 *   - Q    = 1 / (2^(1/bins_per_octave) - 1)
 *   - a Hann window
 *   - per-filter L1 normalization (librosa `norm=1`)
 *   - reflect padding at signal edges (librosa `pad_mode='reflect'`)
 *
 * Two consumers:
 *   - `computeCqt` / `computeCqtFrame`: pure, offline helpers used by the
 *     librosa parity test.
 *   - `CqtStreamer`: incremental frame producer for the live mic pipeline. It
 *     computes each 0.1 s frame exactly once (as audio arrives) and keeps a ring
 *     of the most recent `WINDOW` frames, so inference never recomputes the whole
 *     window.
 */

/** librosa.note_to_hz('C1'). */
export const FMIN = 32.70319566257483

/** Constant-Q quality factor. */
const Q = 1 / (Math.pow(2, 1 / BINS_PER_OCTAVE) - 1)

interface CqtKernel {
  real: Float32Array
  imag: Float32Array
  /** Offset from the frame center to the first kernel sample. */
  halfLen: number
}

let cachedKernels: CqtKernel[] | null = null
let cachedMaxHalfLen = 0

/** Build (and cache) the per-bin complex CQT kernels. */
export function getKernels(): CqtKernel[] {
  if (cachedKernels) return cachedKernels

  const kernels: CqtKernel[] = []
  let maxHalfLen = 0

  for (let k = 0; k < CHROMA_BINS; k++) {
    const freq = FMIN * Math.pow(2, k / BINS_PER_OCTAVE)
    const kernelLen = Math.max(2, Math.ceil((Q * TARGET_SR) / freq))

    const real = new Float32Array(kernelLen)
    const imag = new Float32Array(kernelLen)

    // Complex exponential windowed by a Hann window.
    let l1 = 0
    for (let i = 0; i < kernelLen; i++) {
      const win = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (kernelLen - 1))
      const phase = (-2 * Math.PI * freq * i) / TARGET_SR
      const re = win * Math.cos(phase)
      const im = win * Math.sin(phase)
      real[i] = re
      imag[i] = im
      l1 += Math.sqrt(re * re + im * im)
    }

    // Per-filter L1 normalization (librosa norm=1).
    const inv = l1 > 1e-12 ? 1 / l1 : 0
    for (let i = 0; i < kernelLen; i++) {
      real[i] *= inv
      imag[i] *= inv
    }

    const halfLen = Math.floor(kernelLen / 2)
    if (halfLen > maxHalfLen) maxHalfLen = halfLen
    kernels.push({ real, imag, halfLen })
  }

  cachedKernels = kernels
  cachedMaxHalfLen = maxHalfLen
  return kernels
}

/** Largest kernel half-length (defines the streamer look-ahead / ring size). */
export function getMaxHalfLen(): number {
  if (!cachedKernels) getKernels()
  return cachedMaxHalfLen
}

/** Reflect-index a sample (numpy 'reflect' / librosa pad_mode='reflect'). */
function reflectSample(audio: Float32Array, idx: number, len: number): number {
  if (idx >= 0 && idx < len) return audio[idx]!
  if (len === 1) return audio[0]!
  const period = 2 * (len - 1)
  let m = ((idx % period) + period) % period
  if (m >= len) m = period - m
  return audio[m]!
}

/** Compute a single 144-bin CQT magnitude frame centered at `centerSample`. */
export function computeCqtFrame(audio: Float32Array, centerSample: number): Float32Array {
  const kernels = getKernels()
  const result = new Float32Array(CHROMA_BINS)
  const len = audio.length

  for (let k = 0; k < CHROMA_BINS; k++) {
    const { real, imag, halfLen } = kernels[k]!
    const klen = real.length
    const start = centerSample - halfLen

    let realSum = 0
    let imagSum = 0
    for (let i = 0; i < klen; i++) {
      const sample = reflectSample(audio, start + i, len)
      realSum += sample * real[i]!
      imagSum += sample * imag[i]!
    }
    result[k] = Math.sqrt(realSum * realSum + imagSum * imagSum)
  }

  return result
}

/**
 * Offline CQT over a full signal: frames centered at multiples of HOP_LENGTH
 * with reflect padding (matches librosa center=True). Used by the parity test.
 */
export function computeCqt(audio: Float32Array): Float32Array {
  const nFrames = Math.max(1, Math.floor(audio.length / HOP_LENGTH))
  const result = new Float32Array(nFrames * CHROMA_BINS)
  for (let f = 0; f < nFrames; f++) {
    const frame = computeCqtFrame(audio, f * HOP_LENGTH)
    result.set(frame, f * CHROMA_BINS)
  }
  return result
}

/** Next power of two ≥ n. */
function nextPow2(n: number): number {
  let p = 1
  while (p < n) p <<= 1
  return p
}

/**
 * Incremental CQT frame producer for the live mic pipeline.
 *
 * Call `push(samples)` with raw mono audio as it arrives; the streamer computes
 * each frame exactly once (when enough look-ahead is available) and stores it in
 * a ring of the most recent `WINDOW` frames. `getWindow()` returns the flattened
 * `WINDOW × CHROMA_BINS` tensor (oldest-first, zero-padded until warmed up).
 */
export class CqtStreamer {
  private readonly maxHalfLen: number
  private readonly ringLen: number
  private readonly audioRing: Float32Array
  private readonly scratch: Float32Array
  private readonly featureRing: Float32Array
  private totalSamples = 0
  private nextFrameCenter = 0
  private frameWritePos = 0
  private framesProduced = 0

  constructor() {
    getKernels()
    this.maxHalfLen = getMaxHalfLen()
    this.ringLen = nextPow2(2 * this.maxHalfLen + 2 * HOP_LENGTH)
    this.audioRing = new Float32Array(this.ringLen)
    this.scratch = new Float32Array(2 * this.maxHalfLen + 1)
    this.featureRing = new Float32Array(WINDOW * CHROMA_BINS)
  }

  /** Number of frames produced so far (capped conceptually at WINDOW for readiness). */
  get frameCount(): number {
    return this.framesProduced
  }

  /** True once a full WINDOW of real frames has been produced. */
  get isWarm(): boolean {
    return this.framesProduced >= WINDOW
  }

  /** Fraction (0–1) of the window filled with real frames. */
  get warmFraction(): number {
    return Math.min(1, this.framesProduced / WINDOW)
  }

  /** Append audio and compute any frames that have become available. */
  push(samples: Float32Array): void {
    const mask = this.ringLen - 1
    for (let i = 0; i < samples.length; i++) {
      this.audioRing[(this.totalSamples + i) & mask] = samples[i]!
    }
    this.totalSamples += samples.length

    // Compute every frame whose full right-half look-ahead is now available.
    while (this.nextFrameCenter + this.maxHalfLen < this.totalSamples) {
      this.computeFrameAt(this.nextFrameCenter)
      this.nextFrameCenter += HOP_LENGTH
    }
  }

  private computeFrameAt(center: number): void {
    const mask = this.ringLen - 1
    const radius = this.maxHalfLen
    const oldest = this.totalSamples - this.ringLen
    // Fill scratch (length 2*radius+1) centered on `center`, reflecting at t<0.
    for (let i = 0; i < this.scratch.length; i++) {
      const abs = center - radius + i
      if (abs >= 0 && abs < this.totalSamples && abs >= oldest) {
        this.scratch[i] = this.audioRing[abs & mask]!
      } else if (abs < 0) {
        const r = -abs // reflect across 0
        this.scratch[i] = r < this.totalSamples && r >= oldest ? this.audioRing[r & mask]! : 0
      } else {
        this.scratch[i] = 0
      }
    }

    const frame = computeCqtFrame(this.scratch, radius)
    this.featureRing.set(frame, this.frameWritePos * CHROMA_BINS)
    this.frameWritePos = (this.frameWritePos + 1) % WINDOW
    this.framesProduced++
  }

  /** Flattened WINDOW×CHROMA_BINS tensor, oldest frame first (front-padded with zeros while warming). */
  getWindow(): Float32Array {
    const out = new Float32Array(WINDOW * CHROMA_BINS)
    const have = Math.min(this.framesProduced, WINDOW)
    // Oldest retained frame is at (frameWritePos - have) mod WINDOW.
    const startFrame = (this.frameWritePos - have + WINDOW) % WINDOW
    const dstOffset = (WINDOW - have) * CHROMA_BINS
    for (let f = 0; f < have; f++) {
      const src = ((startFrame + f) % WINDOW) * CHROMA_BINS
      out.set(this.featureRing.subarray(src, src + CHROMA_BINS), dstOffset + f * CHROMA_BINS)
    }
    return out
  }

  reset(): void {
    this.audioRing.fill(0)
    this.featureRing.fill(0)
    this.totalSamples = 0
    this.nextFrameCenter = 0
    this.frameWritePos = 0
    this.framesProduced = 0
  }
}
