import type { PitchReading, PitchStream } from '@/src/pitch/pitchTypes'

export type { PitchReading, PitchStream }

const WORKLET_PROCESSOR_NAME = 'harmoniq-pitch-detector'

const WORKLET_SOURCE = `
class HarmoniqPitchDetectorProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this._buffer = new Float32Array(2048)
    this._cursor = 0
    this._throttle = 0
  }

  _estimatePitch(samples, sampleRate) {
    let rms = 0
    for (let i = 0; i < samples.length; i += 1) {
      const value = samples[i]
      rms += value * value
    }
    rms = Math.sqrt(rms / samples.length)
    if (rms < 0.01) return null

    const minFreq = 70
    const maxFreq = 1000
    const minLag = Math.floor(sampleRate / maxFreq)
    const maxLag = Math.floor(sampleRate / minFreq)

    let bestLag = -1
    let bestCorr = 0

    for (let lag = minLag; lag <= maxLag; lag += 1) {
      let corr = 0
      for (let i = 0; i < samples.length - lag; i += 1) {
        corr += samples[i] * samples[i + lag]
      }
      if (corr > bestCorr) {
        bestCorr = corr
        bestLag = lag
      }
    }

    if (bestLag <= 0 || bestCorr < 0.05) return null
    const hz = sampleRate / bestLag
    if (!Number.isFinite(hz)) return null
    return hz
  }

  process(inputs) {
    const input = inputs[0]
    const channelData = input && input[0]
    if (!channelData) return true

    for (let i = 0; i < channelData.length; i += 1) {
      this._buffer[this._cursor] = channelData[i]
      this._cursor = (this._cursor + 1) % this._buffer.length
    }

    this._throttle += 1
    if (this._throttle < 3) return true
    this._throttle = 0

    const ordered = new Float32Array(this._buffer.length)
    const tail = this._buffer.length - this._cursor
    ordered.set(this._buffer.subarray(this._cursor), 0)
    ordered.set(this._buffer.subarray(0, this._cursor), tail)

    const hz = this._estimatePitch(ordered, sampleRate)
    if (hz) {
      this.port.postMessage({ type: 'pitch', hz })
    }
    return true
  }
}

registerProcessor('${WORKLET_PROCESSOR_NAME}', HarmoniqPitchDetectorProcessor)
`

function hzToMidi(hz: number): number {
  return 69 + 12 * Math.log2(hz / 440)
}

function midiToNoteName(midi: number): string {
  const rounded = Math.round(midi)
  const names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
  const octave = Math.floor(rounded / 12) - 1
  return `${names[((rounded % 12) + 12) % 12]}${octave}`
}

function toReading(hz: number): PitchReading {
  const midi = hzToMidi(hz)
  const nearest = Math.round(midi)
  const cents = Math.round((midi - nearest) * 100)
  return {
    hz,
    midi: nearest,
    cents,
    noteName: midiToNoteName(midi),
  }
}

class PitchStreamWeb implements PitchStream {
  private context: AudioContext | null = null
  private stream: MediaStream | null = null
  private sourceNode: MediaStreamAudioSourceNode | null = null
  private workletNode: AudioWorkletNode | null = null
  private moduleUrl: string | null = null
  private running = false

  async start(onPitch: (reading: PitchReading) => void): Promise<void> {
    if (this.running) {
      console.log('[PitchStream.web] start skipped; already running')
      return
    }
    if (typeof window === 'undefined' || typeof navigator === 'undefined') {
      throw new Error('[PitchStream.web] Browser APIs are not available')
    }
    if (!window.isSecureContext && window.location.hostname !== 'localhost') {
      throw new Error('[PitchStream.web] Mic capture needs HTTPS (or localhost) on web')
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('[PitchStream.web] getUserMedia is unavailable in this browser')
    }

    console.log('[PitchStream.web] requesting microphone access')
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      })
    } catch (error) {
      const err = error as DOMException
      if (err?.name === 'NotAllowedError' || err?.name === 'SecurityError') {
        throw new Error('MIC_PERMISSION_DENIED')
      }
      throw new Error(`[PitchStream.web] Unable to access microphone: ${err?.message ?? String(error)}`)
    }

    this.context = new AudioContext({ latencyHint: 'interactive' })
    if (this.context.state === 'suspended') {
      await this.context.resume()
    }

    const blob = new Blob([WORKLET_SOURCE], { type: 'application/javascript' })
    this.moduleUrl = URL.createObjectURL(blob)
    await this.context.audioWorklet.addModule(this.moduleUrl)

    this.sourceNode = this.context.createMediaStreamSource(this.stream)
    this.workletNode = new AudioWorkletNode(this.context, WORKLET_PROCESSOR_NAME, { numberOfOutputs: 0 })
    this.workletNode.port.onmessage = (event: MessageEvent<{ type: string; hz: number }>) => {
      if (event.data?.type !== 'pitch') return
      onPitch(toReading(event.data.hz))
    }

    this.sourceNode.connect(this.workletNode)
    this.running = true
    console.log('[PitchStream.web] microphone stream started')
  }

  async stop(): Promise<void> {
    console.log('[PitchStream.web] stopping microphone stream')
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
      await this.context.close()
      this.context = null
    }
    if (this.moduleUrl) {
      URL.revokeObjectURL(this.moduleUrl)
      this.moduleUrl = null
    }
    console.log('[PitchStream.web] resources released')
  }

  isRunning(): boolean {
    return this.running
  }
}

export function createPitchStream(): PitchStream {
  return new PitchStreamWeb()
}
