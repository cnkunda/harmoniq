import { AudioManager, AudioRecorder } from 'react-native-audio-api'

import type { PitchReading, PitchStream } from '@/src/pitch/pitchTypes'

export type { PitchReading, PitchStream }

const SAMPLE_RATE_PREF = 44100
/** ~46ms of audio per native buffer — balances latency vs stable autocorrelation. */
const BUFFER_SAMPLES = 2048

function estimatePitchHz(samples: Float32Array, sampleRate: number): number | null {
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

class PitchStreamNative implements PitchStream {
  private readonly recorder = new AudioRecorder()
  private running = false
  private onPitchUser: ((reading: PitchReading) => void) | null = null
  private skipCallbacks = 0

  isRunning(): boolean {
    return this.running
  }

  async start(onPitch: (reading: PitchReading) => void): Promise<void> {
    if (this.running) {
      console.log('[PitchStream.native] start skipped; already running')
      return
    }

    AudioManager.setAudioSessionOptions({
      iosCategory: 'record',
      iosMode: 'default',
      iosOptions: [],
    })

    console.log('[PitchStream.native] requesting microphone permission')
    const perm = await AudioManager.requestRecordingPermissions()
    if (perm !== 'Granted') {
      console.warn('[PitchStream.native] recording permission not granted:', perm)
      throw new Error('MIC_PERMISSION_DENIED')
    }

    const sessionOk = await AudioManager.setAudioSessionActivity(true)
    if (!sessionOk) {
      throw new Error('[PitchStream.native] Could not activate audio session')
    }

    this.onPitchUser = onPitch
    this.skipCallbacks = 0

    const ready = this.recorder.onAudioReady(
      {
        sampleRate: SAMPLE_RATE_PREF,
        bufferLength: BUFFER_SAMPLES,
        channelCount: 1,
      },
      ({ buffer, numFrames }) => {
        if (!this.running || !this.onPitchUser) return

        this.skipCallbacks += 1
        if (this.skipCallbacks < 2) return
        this.skipCallbacks = 0

        const ch0 = buffer.getChannelData(0)
        const frameCount = Math.min(numFrames, ch0.length)
        if (frameCount < 256) return

        const slice = frameCount === ch0.length ? ch0 : ch0.subarray(0, frameCount)
        const hz = estimatePitchHz(slice, buffer.sampleRate)
        if (hz) {
          this.onPitchUser(toReading(hz))
        }
      },
    )

    if (ready.status === 'error') {
      await AudioManager.setAudioSessionActivity(false)
      throw new Error(`[PitchStream.native] onAudioReady failed: ${ready.message}`)
    }

    const started = this.recorder.start()
    if (started.status === 'error') {
      this.recorder.clearOnAudioReady()
      await AudioManager.setAudioSessionActivity(false)
      throw new Error(`[PitchStream.native] start failed: ${started.message}`)
    }

    this.running = true
    console.log('[PitchStream.native] microphone stream started')
  }

  async stop(): Promise<void> {
    console.log('[PitchStream.native] stopping microphone stream')
    this.running = false
    this.onPitchUser = null

    if (this.recorder.isRecording()) {
      const result = this.recorder.stop()
      if (result.status === 'error') {
        console.error('[PitchStream.native] stop result error:', result.message)
      }
    }

    this.recorder.clearOnAudioReady()
    await AudioManager.setAudioSessionActivity(false)
    console.log('[PitchStream.native] resources released')
  }
}

export function createPitchStream(): PitchStream {
  return new PitchStreamNative()
}
