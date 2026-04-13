import { AudioManager, AudioRecorder } from 'react-native-audio-api'

import type { PitchReading, PitchStream } from '@/src/pitch/pitchTypes'

export type { PitchReading, PitchStream }

const SAMPLE_RATE_PREF = 44100
/** ~46ms of audio per native buffer — balances latency vs stable autocorrelation. */
const BUFFER_SAMPLES = 2048
const MIN_RMS_FOR_PITCH = 0.003

function getSampleStats(samples: Float32Array): { rms: number; peakAbs: number } {
  let sumSquares = 0
  let peakAbs = 0
  for (let i = 0; i < samples.length; i += 1) {
    const value = samples[i]
    const abs = Math.abs(value)
    if (abs > peakAbs) peakAbs = abs
    sumSquares += value * value
  }
  const rms = Math.sqrt(sumSquares / samples.length)
  return { rms, peakAbs }
}

function estimatePitchHz(samples: Float32Array, sampleRate: number, rms: number): number | null {
  if (rms < MIN_RMS_FOR_PITCH) return null

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

function toReading(hz: number, rms: number, peakAbs: number): PitchReading {
  const midi = hzToMidi(hz)
  const nearest = Math.round(midi)
  const cents = Math.round((midi - nearest) * 100)
  return {
    hz,
    midi: nearest,
    cents,
    noteName: midiToNoteName(midi),
    rms,
    peakAbs,
  }
}

class PitchStreamNative implements PitchStream {
  private readonly recorder = new AudioRecorder()
  private running = false
  private onPitchUser: ((reading: PitchReading) => void) | null = null
  private skipCallbacks = 0
  private callbackCount = 0
  private emittedPitchCount = 0

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
    console.log('[PitchStream.native] microphone permission status:', perm)
    if (perm !== 'Granted') {
      console.warn('[PitchStream.native] recording permission not granted:', perm)
      throw new Error('MIC_PERMISSION_DENIED')
    }

    const sessionOk = await AudioManager.setAudioSessionActivity(true)
    console.log('[PitchStream.native] audio session activation result:', sessionOk)
    if (!sessionOk) {
      throw new Error('[PitchStream.native] Could not activate audio session')
    }

    this.onPitchUser = onPitch
    this.skipCallbacks = 0
    this.callbackCount = 0
    this.emittedPitchCount = 0

    const ready = this.recorder.onAudioReady(
      {
        sampleRate: SAMPLE_RATE_PREF,
        bufferLength: BUFFER_SAMPLES,
        channelCount: 1,
      },
      ({ buffer, numFrames }) => {
        if (!this.running || !this.onPitchUser) return

        this.callbackCount += 1
        this.skipCallbacks += 1
        if (this.skipCallbacks < 2) return
        this.skipCallbacks = 0

        const ch0 = buffer.getChannelData(0)
        const frameCount = Math.min(numFrames, ch0.length)
        if (frameCount < 256) return

        const slice = frameCount === ch0.length ? ch0 : ch0.subarray(0, frameCount)
        const { rms, peakAbs } = getSampleStats(slice)
        if (this.callbackCount % 20 === 0) {
          console.log(
            `[PitchStream.native] cb=${this.callbackCount} frames=${frameCount} sr=${buffer.sampleRate} rms=${rms.toFixed(5)} peak=${peakAbs.toFixed(5)}`,
          )
        }

        const hz = estimatePitchHz(slice, buffer.sampleRate, rms)
        if (hz) {
          this.emittedPitchCount += 1
          if (this.emittedPitchCount <= 5 || this.emittedPitchCount % 10 === 0) {
            console.log(
              `[PitchStream.native] pitch hit #${this.emittedPitchCount}: ${hz.toFixed(2)}Hz (rms=${rms.toFixed(5)}, peak=${peakAbs.toFixed(5)})`,
            )
          }
          this.onPitchUser(toReading(hz, rms, peakAbs))
        } else if (this.callbackCount % 20 === 0) {
          console.log(
            `[PitchStream.native] no pitch (rms=${rms.toFixed(5)} < ${MIN_RMS_FOR_PITCH.toFixed(3)} or weak correlation)`,
          )
        }
      },
    )

    if (ready.status === 'error') {
      await AudioManager.setAudioSessionActivity(false)
      throw new Error(`[PitchStream.native] onAudioReady failed: ${ready.message}`)
    }
    console.log('[PitchStream.native] onAudioReady registered')

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
    console.log(
      `[PitchStream.native] stopping microphone stream (callbacks=${this.callbackCount}, pitchHits=${this.emittedPitchCount})`,
    )
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
