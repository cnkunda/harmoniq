/**
 * Web microphone recorder for the chord detector.
 *
 * `react-native-audio-api`'s `AudioRecorder` is a native-only module — it is not
 * exported by the package's web build, so `new AudioRecorder()` throws
 * "AudioRecorder is not a constructor" on web. This class provides an equivalent
 * mic-capture path using the Web Audio API (getUserMedia + AudioWorklet) and
 * mirrors the small slice of the `AudioRecorder` interface that
 * `useChordDetector` relies on (`onAudioReady` / `start` / `stop` /
 * `clearOnAudioReady` / `isRecording`).
 */

const WORKLET_PROCESSOR_NAME = 'harmoniq-chord-recorder'

/**
 * Accumulates raw mic samples and posts fixed-size chunks back to the main
 * thread, matching the cadence of the native recorder's `bufferLength`.
 */
const WORKLET_SOURCE = `
class HarmoniqChordRecorderProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super()
    const opts = (options && options.processorOptions) || {}
    this._chunkSize = opts.chunkSize || 2048
    this._buffer = new Float32Array(this._chunkSize)
    this._cursor = 0
  }

  process(inputs) {
    const input = inputs[0]
    const channel = input && input[0]
    if (!channel) return true
    for (let i = 0; i < channel.length; i += 1) {
      this._buffer[this._cursor] = channel[i]
      this._cursor += 1
      if (this._cursor >= this._chunkSize) {
        this.port.postMessage(this._buffer.slice(0, this._chunkSize))
        this._cursor = 0
      }
    }
    return true
  }
}

registerProcessor('${WORKLET_PROCESSOR_NAME}', HarmoniqChordRecorderProcessor)
`

/**
 * Streaming linear resampler. Used only when the browser cannot grant a 44.1kHz
 * `AudioContext` (rare) — the chord model's CQT assumes 44100 Hz, so mic audio
 * captured at another rate must be resampled before it reaches the pipeline.
 */
class LinearResampler {
  private readonly ratio: number
  private readIndex = 0
  private inputCount = 0
  private prev = 0
  private started = false

  constructor(srcRate: number, dstRate: number) {
    this.ratio = srcRate / dstRate
  }

  process(input: Float32Array): Float32Array {
    const len = input.length
    if (len === 0) return new Float32Array(0)
    const blockStart = this.inputCount
    if (!this.started) {
      this.readIndex = blockStart
      this.started = true
    }
    const out: number[] = []
    while (true) {
      const p = this.readIndex
      const i = Math.floor(p)
      if (i + 1 > blockStart + len - 1) break
      const frac = p - i
      const s0 = i < blockStart ? this.prev : input[i - blockStart]!
      const s1 = i + 1 < blockStart ? this.prev : input[i + 1 - blockStart]!
      out.push(s0 * (1 - frac) + s1 * frac)
      this.readIndex += this.ratio
    }
    this.prev = input[len - 1]!
    this.inputCount += len
    return Float32Array.from(out)
  }
}

interface AudioBufferLike {
  getChannelData(channel: number): Float32Array
}

export interface WebMicRecorderConfig {
  sampleRate: number
  bufferLength: number
  channelCount: number
}

export type AudioReadyCallback = (payload: { buffer: AudioBufferLike; numFrames: number }) => void

export class WebMicRecorder {
  private context: AudioContext | null = null
  private stream: MediaStream | null = null
  private sourceNode: MediaStreamAudioSourceNode | null = null
  private workletNode: AudioWorkletNode | null = null
  private moduleUrl: string | null = null
  private running = false
  private config: WebMicRecorderConfig | null = null
  private callback: AudioReadyCallback | null = null
  private resampler: LinearResampler | null = null

  /** Store the capture config + callback. Mirrors `AudioRecorder.onAudioReady`. */
  onAudioReady(config: WebMicRecorderConfig, callback: AudioReadyCallback): { status: 'ok' } {
    this.config = config
    this.callback = callback
    return { status: 'ok' }
  }

  /** Request the mic and begin streaming audio chunks to the callback. */
  async start(): Promise<void> {
    if (this.running) return
    if (typeof window === 'undefined' || typeof navigator === 'undefined') {
      throw new Error('Browser APIs are not available')
    }
    if (!window.isSecureContext && window.location.hostname !== 'localhost') {
      throw new Error('Mic capture needs HTTPS (or localhost) on web')
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('getUserMedia is unavailable in this browser')
    }

    const config = this.config ?? { sampleRate: 44100, bufferLength: 2048, channelCount: 1 }

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
          channelCount: config.channelCount,
        },
      })
    } catch (error) {
      const err = error as DOMException
      if (err?.name === 'NotAllowedError' || err?.name === 'SecurityError') {
        throw new Error('MIC_PERMISSION_DENIED')
      }
      throw new Error(`Unable to access microphone: ${err?.message ?? String(error)}`)
    }

    // Request the model's target sample rate so the CQT pipeline sees 44.1kHz.
    // Browsers that cannot honor the rate fall back to the hardware rate.
    try {
      this.context = new AudioContext({ latencyHint: 'interactive', sampleRate: config.sampleRate })
    } catch {
      this.context = new AudioContext({ latencyHint: 'interactive' })
    }
    if (this.context.state === 'suspended') {
      await this.context.resume()
    }

    // If the browser could not honor the requested rate, resample to it so the
    // CQT/model always see the expected sample rate.
    this.resampler =
      this.context.sampleRate !== config.sampleRate
        ? new LinearResampler(this.context.sampleRate, config.sampleRate)
        : null
    if (this.resampler) {
      console.warn(
        `[WebMicRecorder] AudioContext sampleRate ${this.context.sampleRate}Hz != ${config.sampleRate}Hz; resampling`,
      )
    }

    const blob = new Blob([WORKLET_SOURCE], { type: 'application/javascript' })
    this.moduleUrl = URL.createObjectURL(blob)
    await this.context.audioWorklet.addModule(this.moduleUrl)

    this.sourceNode = this.context.createMediaStreamSource(this.stream)
    this.workletNode = new AudioWorkletNode(this.context, WORKLET_PROCESSOR_NAME, {
      numberOfOutputs: 0,
      processorOptions: { chunkSize: config.bufferLength },
    })
    this.workletNode.port.onmessage = (event: MessageEvent<Float32Array>) => {
      const raw = event.data
      if (!this.running || !this.callback || !raw) return
      const samples = this.resampler ? this.resampler.process(raw) : raw
      if (samples.length === 0) return
      this.callback({
        buffer: { getChannelData: () => samples },
        numFrames: samples.length,
      })
    }

    this.sourceNode.connect(this.workletNode)
    this.running = true
  }

  isRecording(): boolean {
    return this.running
  }

  /** Stop capture and release the mic + audio graph. */
  stop(): void {
    this.running = false
    if (this.workletNode) {
      this.workletNode.port.onmessage = null
      this.workletNode.disconnect()
      this.workletNode = null
    }
    if (this.sourceNode) {
      this.sourceNode.disconnect()
      this.sourceNode = null
    }
    if (this.stream) {
      for (const track of this.stream.getTracks()) {
        track.stop()
      }
      this.stream = null
    }
    if (this.context) {
      void this.context.close()
      this.context = null
    }
    if (this.moduleUrl) {
      URL.revokeObjectURL(this.moduleUrl)
      this.moduleUrl = null
    }
    this.resampler = null
  }

  clearOnAudioReady(): void {
    this.callback = null
  }
}
