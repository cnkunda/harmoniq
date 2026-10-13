import { useCallback, useEffect, useRef } from 'react'
import { Platform } from 'react-native'

import { FEATURE_DIM, WINDOW } from '@/src/chord/cqtConstants'
import { CqtStreamer } from '@/src/chord/computeCqt'
import { ChordSmoother } from '@/src/chord/chordSmoothing'
import { idxToChord, NUM_CLASSES_MIREX } from '@/src/chord/chordVocab'
import type { ChordDetection } from '@/src/chord/chordModelTypes'
import { useLiveChordStore } from '@/src/chord/liveChordStore'
import { globalAudioManager } from '@/src/audio/GlobalAudioManager'

/** How often to run model inference (ms). Decoupled from audio callback cadence. */
const INFERENCE_INTERVAL_MS = 500

/** Below this RMS the input is treated as silence — emit No-Chord, skip the model. */
const RMS_SILENCE_THRESHOLD = 0.01

/** Minimum real frames before running inference (front-padded until warm). */
const MIN_FRAMES_FOR_INFERENCE = 16

/** Smoothed-probability gate below which we show "—" instead of a chord. */
const CONFIDENCE_THRESHOLD = 0.5

/** Load onnxruntime-web from CDN on web (avoids bundler dynamic-import issues). */
function loadScript(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = url
    s.onload = () => resolve()
    s.onerror = () => reject(new Error(`Failed to load script: ${url}`))
    document.head.appendChild(s)
  })
}

/** Pinned CDN base (fallback when self-hosted assets aren't present). */
const ORT_VERSION = '1.27.0'
const ORT_CDN_BASE = `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/`
/** Self-hosted base — populated by scripts/copy-ort-assets.mjs into public/ort/. */
const ORT_LOCAL_BASE = '/ort/'

/**
 * Ensure onnxruntime-web is available on `window.ort`. Prefers the self-hosted
 * copy (offline-capable, version-pinned); falls back to the pinned CDN if the
 * local assets are missing. `wasmPaths` is pointed at whichever base succeeded so
 * the runtime resolves its .wasm/.mjs from the same origin.
 */
async function ensureOrtWeb(): Promise<any> {
  const w = window as any
  if (w.ort) return w.ort

  let base = ORT_LOCAL_BASE
  try {
    await loadScript(`${ORT_LOCAL_BASE}ort.all.min.js`)
    if (!w.ort) throw new Error('local ort missing')
  } catch {
    base = ORT_CDN_BASE
    await loadScript(`${ORT_CDN_BASE}ort.all.min.js`)
  }

  const ort = w.ort
  if (!ort) throw new Error('ONNX runtime failed to initialize on web')
  try {
    ort.env.wasm.wasmPaths = base
  } catch {
    // Non-fatal; runtime will use its own default resolution.
  }
  return ort
}

/** Model runner interface — abstracts TFLite (sync) and ONNX (async). */
interface ModelRunner {
  runSync(input: Float32Array): Float32Array
  runAsync?(input: Float32Array): Promise<Float32Array>
}

/** L1-normalize each CQT frame in a flattened WINDOW×FEATURE_DIM tensor. */
function normalizeWindowL1(window: Float32Array): Float32Array {
  const out = new Float32Array(window.length)
  const frames = Math.floor(window.length / FEATURE_DIM)
  for (let f = 0; f < frames; f++) {
    const off = f * FEATURE_DIM
    let sum = 0
    for (let b = 0; b < FEATURE_DIM; b++) sum += Math.abs(window[off + b] ?? 0)
    const norm = Math.max(sum, 1e-8)
    for (let b = 0; b < FEATURE_DIM; b++) out[off + b] = (window[off + b] ?? 0) / norm
  }
  return out
}

/**
 * Hook to orchestrate real-time chord detection from microphone input.
 *
 * Pipeline: mic → incremental CQT (streaming frames) → TFLite/ONNX → temporal
 * smoothing → chord label.
 *
 * The CQT is computed one frame at a time as audio arrives (`CqtStreamer`), so
 * inference reads a ready feature window instead of recomputing ~13 s of audio
 * every cycle. Inference runs on a fixed interval with an in-flight guard, is
 * gated by input level (RMS) and model confidence, and is stabilized by
 * `ChordSmoother` (EMA + hysteresis).
 */
export function useChordDetector() {
  const store = useLiveChordStore()
  const setListening = useLiveChordStore((s) => s.setListening)
  const setStatus = useLiveChordStore((s) => s.setStatus)
  const setCurrentChord = useLiveChordStore((s) => s.setCurrentChord)
  const setError = useLiveChordStore((s) => s.setError)
  const setModelType = useLiveChordStore((s) => s.setModelType)
  const reset = useLiveChordStore((s) => s.reset)

  const recorderRef = useRef<{ stop(): unknown; clearOnAudioReady(): void } | null>(null)
  const runningRef = useRef(false)
  const modelRef = useRef<ModelRunner | null>(null)
  const modelTypeRef = useRef<'tflite' | 'onnx' | null>(null)
  const streamerRef = useRef<CqtStreamer | null>(null)
  const smootherRef = useRef<ChordSmoother | null>(null)
  const inferInFlightRef = useRef(false)
  const inferTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const latestRmsRef = useRef(0)

  /** Load the TFLite or ONNX model. */
  const loadModel = useCallback(async (): Promise<'tflite' | 'onnx'> => {
    // Try react-native-fast-tflite first (native mobile path — C++ TFLite core)
    try {
      const { loadTensorflowModel } = await import('react-native-fast-tflite')
      const modelAsset: number = require('@/assets/models/chord_model.tflite')
      const tfliteModel = await loadTensorflowModel(modelAsset, [])
      modelRef.current = {
        runSync(input: Float32Array): Float32Array {
          const buf = input.buffer.slice(input.byteOffset, input.byteOffset + input.byteLength) as ArrayBuffer
          const output = tfliteModel.runSync([buf])
          return new Float32Array(output[0]!)
        },
      }
      modelTypeRef.current = 'tflite'
      setModelType('tflite')
      console.log('[ChordDetector] TFLite model loaded (native)')
      return 'tflite'
    } catch {
      // Not on mobile or TFLite unavailable — fall through to ONNX
    }

    // Fall back to ONNX (web path — onnxruntime-web)
    try {
      let ort: any

      if (Platform.OS === 'web') {
        // Self-hosted (with CDN fallback) to avoid a hard runtime CDN dependency.
        ort = await ensureOrtWeb()
      } else {
        const mod: any = await import('onnxruntime-web')
        ort = mod
      }

      const modelUrl: number = require('@/assets/models/chord_model.onnx')
      const session = await ort.InferenceSession.create(String(modelUrl))
      modelRef.current = {
        runSync(): Float32Array {
          return new Float32Array(NUM_CLASSES_MIREX)
        },
        async runAsync(input: Float32Array): Promise<Float32Array> {
          const tensor = new ort.Tensor('float32', input, [1, WINDOW, FEATURE_DIM])
          const result = await session.run({ input: tensor })
          const outputKey = session.outputNames[0]!
          const output = result[outputKey]
          // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
          return new Float32Array((output as unknown as { data: Float32Array }).data)
        },
      }
      modelTypeRef.current = 'onnx'
      setModelType('onnx')
      console.log('[ChordDetector] ONNX model loaded')
      return 'onnx'
    } catch (e) {
      throw new Error(`Failed to load chord model: ${e instanceof Error ? e.message : String(e)}`)
    }
  }, [setModelType])

  /** Run inference on the current feature window (interval-driven, guarded). */
  const runInference = useCallback(async () => {
    if (!runningRef.current || inferInFlightRef.current) return

    const model = modelRef.current
    const streamer = streamerRef.current
    const smoother = smootherRef.current
    if (!model || !streamer || !smoother) return

    // Promote to "listening" once the feature window is fully warmed.
    const status = useLiveChordStore.getState().status
    if (streamer.isWarm) {
      if (status !== 'listening') setStatus('listening')
    } else if (status !== 'warming') {
      setStatus('warming')
    }

    // Silence gate — emit No-Chord and skip the model (also saves CPU).
    if (latestRmsRef.current < RMS_SILENCE_THRESHOLD) {
      smoother.reset()
      setCurrentChord({ chord: 'N', confidence: 0, timestamp: Date.now(), latencyMs: 0 })
      return
    }

    if (streamer.frameCount < MIN_FRAMES_FOR_INFERENCE) return

    inferInFlightRef.current = true
    try {
      const startMs = performance.now()
      const modelInput = normalizeWindowL1(streamer.getWindow())
      const probs = model.runAsync ? await model.runAsync(modelInput) : model.runSync(modelInput)
      const latencyMs = performance.now() - startMs

      if (latencyMs > 120) {
        console.warn(
          `[ChordDetector] Slow inference: ${latencyMs.toFixed(1)}ms ` +
            `(threshold: 120ms, model: ${modelTypeRef.current ?? 'unknown'})`,
        )
      }

      const result = smoother.update(probs)
      const chord = result.index >= 0 ? idxToChord(result.index) : 'N'
      const detection: ChordDetection = {
        chord,
        confidence: result.confidence,
        timestamp: Date.now(),
        latencyMs: Math.round(latencyMs),
      }
      setCurrentChord(detection)
    } catch (e) {
      console.error('[ChordDetector] inference failed:', e instanceof Error ? e.message : String(e))
    } finally {
      inferInFlightRef.current = false
    }
  }, [setCurrentChord, setStatus])

  /** Handle incoming audio buffer from the mic: track RMS + feed the CQT streamer. */
  const handleAudioBuffer = useCallback(
    ({ buffer: inputBuffer, numFrames }: { buffer: { getChannelData(ch: number): Float32Array }; numFrames: number }) => {
      if (!runningRef.current) return
      const ch0 = inputBuffer.getChannelData(0)
      const frameCount = Math.min(numFrames, ch0.length)
      if (frameCount < 1) return
      const samples = frameCount === ch0.length ? ch0 : ch0.subarray(0, frameCount)

      let sum = 0
      for (let i = 0; i < frameCount; i++) {
        const v = samples[i]!
        sum += v * v
      }
      latestRmsRef.current = Math.sqrt(sum / frameCount)

      streamerRef.current?.push(samples)
    },
    [],
  )

  /** Stop listening: release mic, clear buffers. */
  const stopListening = useCallback(async () => {
    runningRef.current = false

    if (inferTimerRef.current) {
      clearInterval(inferTimerRef.current)
      inferTimerRef.current = null
    }

    const recorder = recorderRef.current
    if (recorder) {
      if ('isRecording' in recorder && typeof recorder.isRecording === 'function' && recorder.isRecording()) {
        recorder.stop()
      }
      recorder.clearOnAudioReady()
      recorderRef.current = null
    }

    await globalAudioManager.unregisterInstance('chord-detector')

    if (Platform.OS !== 'web') {
      try {
        const { AudioManager } = await import('react-native-audio-api')
        await AudioManager.setAudioSessionActivity(false)
      } catch {
        // Best-effort cleanup
      }
    }

    streamerRef.current?.reset()
    streamerRef.current = null
    smootherRef.current = null
    inferInFlightRef.current = false
    latestRmsRef.current = 0

    setStatus('idle')
    setListening(false)
    console.log('[ChordDetector] Listening stopped')
  }, [setListening, setStatus])

  /** Start listening: load models, start mic, begin inference loop. */
  const startListening = useCallback(async () => {
    if (runningRef.current) return

    try {
      setError(null)
      setListening(true)
      setStatus('initializing')

      await loadModel()

      // Fresh feature streamer + smoother for this session.
      streamerRef.current = new CqtStreamer()
      smootherRef.current = new ChordSmoother({
        numClasses: NUM_CLASSES_MIREX,
        confidenceThreshold: CONFIDENCE_THRESHOLD,
      })
      inferInFlightRef.current = false
      latestRmsRef.current = 0

      // Request mic permission and start audio capture.
      // Web has no native `AudioRecorder`, so use the Web Audio API path.
      if (Platform.OS === 'web') {
        const { WebMicRecorder } = await import('@/src/chord/webMicRecorder')
        const recorder = new WebMicRecorder()
        recorderRef.current = recorder

        recorder.onAudioReady(
          {
            sampleRate: 44100,
            bufferLength: 2048,
            channelCount: 1,
          },
          handleAudioBuffer,
        )

        // Throws 'MIC_PERMISSION_DENIED' or a descriptive error on failure.
        await recorder.start()
      } else {
        const { AudioManager, AudioRecorder } = await import('react-native-audio-api')

        AudioManager.setAudioSessionOptions({
          iosCategory: 'record',
          iosMode: 'default',
          iosOptions: [],
        })

        const perm = await AudioManager.requestRecordingPermissions()
        if (perm !== 'Granted') {
          throw new Error('MIC_PERMISSION_DENIED')
        }

        const sessionOk = await AudioManager.setAudioSessionActivity(true)
        if (!sessionOk) {
          throw new Error('Could not activate audio session')
        }

        const recorder = new AudioRecorder()
        recorderRef.current = recorder

        const ready = recorder.onAudioReady(
          {
            sampleRate: 44100,
            bufferLength: 2048,
            channelCount: 1,
          },
          handleAudioBuffer,
        )

        if (ready.status === 'error') {
          await AudioManager.setAudioSessionActivity(false)
          throw new Error(`onAudioReady failed: ${ready.message}`)
        }

        const started = recorder.start()
        if (started.status === 'error') {
          recorder.clearOnAudioReady()
          await AudioManager.setAudioSessionActivity(false)
          throw new Error(`start failed: ${started.message}`)
        }
      }

      runningRef.current = true
      setStatus('warming')
      console.log('[ChordDetector] Listening started')

      // Drive inference on a fixed interval (guarded against overlap).
      inferTimerRef.current = setInterval(() => {
        void runInference()
      }, INFERENCE_INTERVAL_MS)

      // Register with GlobalAudioManager
      globalAudioManager.registerInstance(
        'chord-detector',
        'audio-api-recorder',
        recorderRef.current,
        async () => {
          if (runningRef.current) {
            await stopListening()
          }
        },
      )
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      console.error('[ChordDetector] start failed:', msg)
      setError(msg)
      setStatus('idle')
      setListening(false)
      runningRef.current = false
      if (inferTimerRef.current) {
        clearInterval(inferTimerRef.current)
        inferTimerRef.current = null
      }
    }
  }, [loadModel, handleAudioBuffer, runInference, setError, setListening, setStatus, stopListening])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (runningRef.current) {
        void stopListening()
      }
      if (inferTimerRef.current) {
        clearInterval(inferTimerRef.current)
        inferTimerRef.current = null
      }
      streamerRef.current = null
      modelRef.current = null
      smootherRef.current = null
    }
  }, [stopListening])

  return {
    isListening: store.isListening,
    status: store.status,
    currentChord: store.currentChord,
    history: store.history,
    latencyMs: store.latencyMs,
    error: store.error,
    modelType: store.modelType,
    startListening,
    stopListening,
    reset,
  }
}
