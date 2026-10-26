import { AudioManager, AudioRecorder } from 'react-native-audio-api'
import { TurboModuleRegistry } from 'react-native'

import { globalAudioManager } from '@/src/audio/GlobalAudioManager'
import { isPitchJsiEnabled } from '@/src/config'
import type { PitchReading, PitchStream } from '@/src/pitch/pitchTypes'

export type { PitchReading, PitchStream }

const SAMPLE_RATE_PREF = 44100
/** ~46ms of audio per native buffer — balances latency vs stable autocorrelation. */
const BUFFER_SAMPLES = 2048
/** ~23ms buffers feed the native 2048-sample sliding window every callback. */
const JSI_BUFFER_SAMPLES = 1024
const MIN_RMS_FOR_PITCH = 0.003

interface PitchDetectorBridge {
  start(): void
  processPcm(samples: Float32Array, sampleRate: number): void
  getPitchHz(): number
  getRms(): number
  getPeakAbs(): number
  stop(): void
}

type PitchDetectorGlobal = typeof globalThis & {
  __harmoniqPitch?: PitchDetectorBridge
}

let cachedPitchDetector: PitchDetectorBridge | null | undefined

/**
 * Commit 178: the native modules install `__harmoniqPitch` through JSI. Accessing
 * the TurboModule triggers that installation; the global avoids copying PCM through
 * the bridge.
 */
function getPitchDetector(): PitchDetectorBridge | null {
  if (cachedPitchDetector !== undefined) return cachedPitchDetector

  let nativeModule: unknown = null
  try {
    nativeModule = TurboModuleRegistry.get('HarmoniqPitchDetector')
  } catch (error) {
    console.warn(
      '[PitchStream.native] pitch detector module lookup failed; falling back to the JS estimator',
      error instanceof Error ? error.message : String(error),
    )
    cachedPitchDetector = null
    return cachedPitchDetector
  }

  if (!nativeModule) {
    cachedPitchDetector = null
    return cachedPitchDetector
  }

  const bridge = (globalThis as PitchDetectorGlobal).__harmoniqPitch
  if (!bridge) {
    console.warn('[PitchStream.native] pitch detector JSI bridge missing; falling back to the JS estimator')
    cachedPitchDetector = null
    return cachedPitchDetector
  }

  cachedPitchDetector = bridge
  return cachedPitchDetector
}

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
  private detector: PitchDetectorBridge | null = null
  private readonly updateIntervalsMs: number[] = []
  private lastPitchEmitMs = 0
  private streamInstanceId = `pitch-stream-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`

  isRunning(): boolean {
    return this.running
  }

  /** Commit 178: dev-only evidence for the <30ms update-interval acceptance criterion. */
  private recordJsiUpdateInterval(): void {
    if (!__DEV__) return
    const now = Date.now()
    if (this.lastPitchEmitMs > 0) {
      this.updateIntervalsMs.push(now - this.lastPitchEmitMs)
    }
    this.lastPitchEmitMs = now
    if (this.updateIntervalsMs.length < 60) return

    const sorted = [...this.updateIntervalsMs].sort((a, b) => a - b)
    const percentile = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * q))]!
    console.log(
      `[PitchStream.native] jsi update interval p50=${percentile(0.5)}ms p95=${percentile(0.95)}ms n=${sorted.length}`,
    )
    this.updateIntervalsMs.length = 0
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
    this.updateIntervalsMs.length = 0
    this.lastPitchEmitMs = 0

    const jsiEnabled = isPitchJsiEnabled()
    this.detector = jsiEnabled ? getPitchDetector() : null
    if (jsiEnabled && !this.detector) {
      console.warn(
        '[PitchStream.native] EXPO_PUBLIC_HARMONIQ_PITCH_JSI=1 but the native detector is unavailable; using the JS estimator',
      )
    }
    const useJsi = this.detector != null
    const bufferSamples = useJsi ? JSI_BUFFER_SAMPLES : BUFFER_SAMPLES
    this.detector?.start()

    const ready = this.recorder.onAudioReady(
      {
        sampleRate: SAMPLE_RATE_PREF,
        bufferLength: bufferSamples,
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
        const detector = this.detector
        if (detector) {
          detector.processPcm(slice, buffer.sampleRate)
          const hz = detector.getPitchHz()
          const rms = detector.getRms()
          const peakAbs = detector.getPeakAbs()
          if (this.callbackCount % 20 === 0) {
            console.log(
              `[PitchStream.native] jsi cb=${this.callbackCount} frames=${frameCount} sr=${buffer.sampleRate} rms=${rms.toFixed(5)} peak=${peakAbs.toFixed(5)} hz=${hz.toFixed(2)}`,
            )
          }
          if (hz > 0 && Number.isFinite(hz)) {
            this.emittedPitchCount += 1
            if (this.emittedPitchCount <= 5 || this.emittedPitchCount % 10 === 0) {
              console.log(
                `[PitchStream.native] jsi pitch hit #${this.emittedPitchCount}: ${hz.toFixed(2)}Hz (rms=${rms.toFixed(5)}, peak=${peakAbs.toFixed(5)})`,
              )
            }
            this.recordJsiUpdateInterval()
            this.onPitchUser(toReading(hz, rms, peakAbs))
          }
          return
        }

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
      this.detector?.stop()
      this.detector = null
      await AudioManager.setAudioSessionActivity(false)
      throw new Error(`[PitchStream.native] onAudioReady failed: ${ready.message}`)
    }
    console.log('[PitchStream.native] onAudioReady registered')

    const started = this.recorder.start()
    if (started.status === 'error') {
      this.detector?.stop()
      this.detector = null
      this.recorder.clearOnAudioReady()
      await AudioManager.setAudioSessionActivity(false)
      throw new Error(`[PitchStream.native] start failed: ${started.message}`)
    }

    this.running = true
    console.log(`[PitchStream.native] microphone stream started (jsi=${useJsi}, buffer=${bufferSamples})`)

    // Register pitch stream with GlobalAudioManager
    globalAudioManager.registerInstance(
      this.streamInstanceId,
      'audio-api-recorder',
      this.recorder,
      async () => {
        if (this.running) {
          await this.stop()
        }
      },
    )
  }

  async stop(): Promise<void> {
    console.log(
      `[PitchStream.native] stopping microphone stream (callbacks=${this.callbackCount}, pitchHits=${this.emittedPitchCount})`,
    )
    this.running = false
    this.onPitchUser = null
    this.detector?.stop()
    this.detector = null
    this.updateIntervalsMs.length = 0
    this.lastPitchEmitMs = 0

    if (this.recorder.isRecording()) {
      const result = this.recorder.stop()
      if (result.status === 'error') {
        console.error('[PitchStream.native] stop result error:', result.message)
      }
    }

    this.recorder.clearOnAudioReady()
    await AudioManager.setAudioSessionActivity(false)
    console.log('[PitchStream.native] resources released')

    // Unregister from GlobalAudioManager
    void globalAudioManager.unregisterInstance(this.streamInstanceId)
  }
}

export function createPitchStream(): PitchStream {
  return new PitchStreamNative()
}
