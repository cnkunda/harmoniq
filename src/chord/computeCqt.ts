import { BINS_PER_OCTAVE, CHROMA_BINS, TARGET_SR, HOP_LENGTH } from './cqtConstants'

interface CqtKernel {
  real: Float32Array
  imag: Float32Array
  halfLen: number
}

let cachedKernels: CqtKernel[] | null = null

function getKernels(): CqtKernel[] {
  if (cachedKernels) return cachedKernels

  const fmin = 32.7
  const Q = 1 / (Math.pow(2, 1 / BINS_PER_OCTAVE) - 1)
  const kernels: CqtKernel[] = []

  for (let k = 0; k < CHROMA_BINS; k++) {
    const freq = fmin * Math.pow(2, k / BINS_PER_OCTAVE)
    const kernelLen = Math.ceil(Q * TARGET_SR / freq)

    const real = new Float32Array(kernelLen)
    const imag = new Float32Array(kernelLen)

    for (let i = 0; i < kernelLen; i++) {
      const win = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (kernelLen - 1))
      const phase = -2 * Math.PI * freq * i / TARGET_SR
      real[i] = win * Math.cos(phase)
      imag[i] = win * Math.sin(phase)
    }

    kernels.push({ real, imag, halfLen: Math.floor(kernelLen / 2) })
  }

  cachedKernels = kernels
  return kernels
}

export function computeCqtFrame(audio: Float32Array, centerSample: number): Float32Array {
  const kernels = getKernels()
  const result = new Float32Array(CHROMA_BINS)

  for (let k = 0; k < CHROMA_BINS; k++) {
    const { real, imag, halfLen } = kernels[k]!
    const len = real.length
    const start = centerSample - halfLen

    let realSum = 0
    let imagSum = 0

    for (let i = 0; i < len; i++) {
      const idx = start + i
      const sample = idx >= 0 && idx < audio.length ? audio[idx]! : 0
      realSum += sample * real[i]!
      imagSum += sample * imag[i]!
    }

    result[k] = Math.sqrt(realSum * realSum + imagSum * imagSum)
  }

  return result
}

export function computeCqt(audio: Float32Array): Float32Array {
  const nFrames = Math.max(1, Math.floor(audio.length / HOP_LENGTH))
  const result = new Float32Array(nFrames * CHROMA_BINS)

  for (let f = 0; f < nFrames; f++) {
    const center = f * HOP_LENGTH
    const frame = computeCqtFrame(audio, center)
    result.set(frame, f * CHROMA_BINS)
  }

  return result
}
