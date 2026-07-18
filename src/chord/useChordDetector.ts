import { useCallback, useEffect, useRef } from 'react'
import { Platform } from 'react-native'

import {
  CHROMA_BINS,
  FEATURE_DIM,
  HOP_LENGTH,
  TARGET_SR,
  WINDOW,
} from '@/src/chord/cqtConstants'
import { idxToChord } from '@/src/chord/chordVocab'
import type { ChordDetection } from '@/src/chord/chordModelTypes'
import { useLiveChordStore } from '@/src/chord/liveChordStore'
import { globalAudioManager } from '@/src/audio/GlobalAudioManager'

/** Number of raw audio samples for the full CQT window (12.8s at 44.1kHz). */
const WINDOW_SAMPLES = WINDOW * HOP_LENGTH

/** Dynamically load a script tag — used to load onnxruntime-web from CDN on web. */
function loadScript(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = url
    s.onload = () => resolve()
    s.onerror = () => reject(new Error(`Failed to load script: ${url}`))
    document.head.appendChild(s)
  })
}

/** Ring buffer stores extra for the symmetric padding. */
const PADDING_SAMPLES = HOP_LENGTH * (WINDOW / 2)

/** Model runner interface — abstracts TFLite (sync) and ONNX (async). */
interface ModelRunner {
  runSync(input: Float32Array): Float32Array
  runAsync?(input: Float32Array): Promise<Float32Array>
}

/**
 * Hook to orchestrate real-time chord detection from microphone input.
 *
 * Pipeline: mic → ring buffer → CQT → TFLite/ONNX → chord label
 *
 * Uses `react-native-fast-tflite` on mobile and `onnxruntime-web` on web.
 * CQT features computed via TypeScript port of librosa.cqt.
 */
export function useChordDetector() {
  const store = useLiveChordStore()
  const setListening = useLiveChordStore((s) => s.setListening)
  const setCurrentChord = useLiveChordStore((s) => s.setCurrentChord)
  const setError = useLiveChordStore((s) => s.setError)
  const setModelType = useLiveChordStore((s) => s.setModelType)
  const reset = useLiveChordStore((s) => s.reset)

  const audioBufferRef = useRef<Float32Array | null>(null)
  const writePosRef = useRef(0)
  const frameCountRef = useRef(0)
  const recorderRef = useRef<{ stop(): unknown; clearOnAudioReady(): void } | null>(null)
  const runningRef = useRef(false)
  const modelRef = useRef<ModelRunner | null>(null)
  const cqtRef = useRef<{ compute(audio: Float32Array): Float32Array } | null>(null)
  const modelTypeRef = useRef<'tflite' | 'onnx' | null>(null)

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
          const output = tfliteModel.run([buf])
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
        // On web, load from CDN to avoid bundler dynamic-import issues in ort.bundle.min.mjs
        await loadScript('https://cdn.jsdelivr.net/npm/onnxruntime-web@1.27.0/dist/ort.all.min.js')
        ort = (window as any).ort
        if (!ort) throw new Error('ONNX runtime failed to initialize on web')
      } else {
        const mod: any = await import('onnxruntime-web')
        ort = mod
      }

      const modelUrl: number = require('@/assets/models/chord_model.onnx')
      const session = await ort.InferenceSession.create(String(modelUrl))
      modelRef.current = {
        runSync(input: Float32Array): Float32Array {
          return new Float32Array(WINDOW * FEATURE_DIM)
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

/** Load the CQT processor. */
  const loadCqt = useCallback(async () => {
    try {
      const { computeCqt } = await import('@/src/chord/computeCqt')
      cqtRef.current = { compute: computeCqt }
      console.log('[ChordDetector] CQT processor loaded')
    } catch (e) {
      throw new Error(`Failed to load CQT processor: ${e instanceof Error ? e.message : String(e)}`)
    }
  }, [])

  /** Build the model input tensor from CQT features. */
  const buildModelInput = useCallback((cqtFeatures: Float32Array): Float32Array => {
    const nFrames = Math.floor(cqtFeatures.length / CHROMA_BINS)
    const modelInput = new Float32Array(WINDOW * FEATURE_DIM)

    // Use the most recent WINDOW frames (or pad with zeros if fewer)
    const startFrame = Math.max(0, nFrames - WINDOW)
    for (let f = 0; f < WINDOW; f++) {
      const srcFrame = startFrame + f
      const srcOffset = srcFrame * CHROMA_BINS
      const dstOffset = f * FEATURE_DIM
      if (srcFrame < nFrames) {
        // Row-normalize (L1)
        let sum = 0
        for (let b = 0; b < CHROMA_BINS; b++) {
          sum += Math.abs(cqtFeatures[srcOffset + b] ?? 0)
        }
        const norm = Math.max(sum, 1e-8)
        for (let b = 0; b < CHROMA_BINS; b++) {
          modelInput[dstOffset + b] = (cqtFeatures[srcOffset + b] ?? 0) / norm
        }
      }
    }
    return modelInput
  }, [])

  /** Parse model output probabilities into a chord detection. */
  const parseOutput = useCallback(
    (probs: Float32Array, latencyMs: number): ChordDetection => {
      let maxIdx = 0
      let maxProb = probs[0] ?? 0
      for (let i = 1; i < probs.length; i++) {
        if ((probs[i] ?? 0) > maxProb) {
          maxProb = probs[i]!
          maxIdx = i
        }
      }
      return {
        chord: idxToChord(maxIdx),
        confidence: maxProb,
        timestamp: Date.now(),
        latencyMs: Math.round(latencyMs),
      }
    },
    [],
  )

  /** Run inference on the current ring buffer contents. */
  const runInference = useCallback(async () => {
    const model = modelRef.current
    const cqt = cqtRef.current
    const buffer = audioBufferRef.current
    if (!model || !cqt || !buffer) return

    const startMs = performance.now()

    // Extract the 12.8s window from the ring buffer
    const writePos = writePosRef.current
    const windowSamples = WINDOW_SAMPLES + PADDING_SAMPLES
    const windowData = new Float32Array(windowSamples)
    for (let i = 0; i < windowSamples; i++) {
      const idx = (writePos - windowSamples + i + buffer.length) % buffer.length
      windowData[i] = buffer[idx]!
    }

    // Compute CQT features → (nFrames, 144)
    const cqtFeatures = cqt.compute(windowData)
    const modelInput = buildModelInput(cqtFeatures)

    // Run model inference (async if available, sync fallback)
    const probs = model.runAsync
      ? await model.runAsync(modelInput)
      : model.runSync(modelInput)

    const latencyMs = performance.now() - startMs

    // AC 6: warn when on-device inference exceeds 120ms threshold
    if (latencyMs > 120) {
      console.warn(
        `[ChordDetector] Slow inference: ${latencyMs.toFixed(1)}ms ` +
        `(threshold: 120ms, model: ${modelTypeRef.current ?? 'unknown'})`,
      )
    }

    const detection = parseOutput(probs, latencyMs)
    setCurrentChord(detection)
  }, [buildModelInput, parseOutput, setCurrentChord])

  /** Handle incoming audio buffer from the mic. */
  const handleAudioBuffer = useCallback(
    ({ buffer: inputBuffer, numFrames }: { buffer: { getChannelData(ch: number): Float32Array }; numFrames: number }) => {
      if (!runningRef.current) return

      const ch0 = inputBuffer.getChannelData(0)
      const frameCount = Math.min(numFrames, ch0.length)
      if (frameCount < 256) return

      // Write into ring buffer
      const ringBuffer = audioBufferRef.current
      if (!ringBuffer) return

      for (let i = 0; i < frameCount; i++) {
        ringBuffer[writePosRef.current] = ch0[i]!
        writePosRef.current = (writePosRef.current + 1) % ringBuffer.length
      }
      frameCountRef.current += 1

      // Run inference every 32 callbacks (~1.5s of audio at 46ms per callback)
      if (frameCountRef.current % 32 === 0) {
        void runInference()
      }
    },
    [runInference],
  )

  /** Stop listening: release mic, clear buffers. */
  const stopListening = useCallback(async () => {
    runningRef.current = false

    const recorder = recorderRef.current
    if (recorder) {
      if ('isRecording' in recorder && typeof recorder.isRecording === 'function' && recorder.isRecording()) {
        recorder.stop()
      }
      recorder.clearOnAudioReady()
      recorderRef.current = null
    }

    await globalAudioManager.unregisterInstance('chord-detector')

    try {
      const { AudioManager } = await import('react-native-audio-api')
      await AudioManager.setAudioSessionActivity(false)
    } catch {
      // Best-effort cleanup
    }

    audioBufferRef.current = null
    writePosRef.current = 0
    frameCountRef.current = 0

    setListening(false)
    console.log('[ChordDetector] Listening stopped')
  }, [setListening])

  /** Start listening: load models, start mic, begin inference loop. */
  const startListening = useCallback(async () => {
    if (runningRef.current) return

    try {
      setError(null)
      setListening(true)

      // Load models in parallel
      await Promise.all([loadCqt(), loadModel()])

      // Initialize ring buffer
      audioBufferRef.current = new Float32Array(WINDOW_SAMPLES + PADDING_SAMPLES)
      writePosRef.current = 0
      frameCountRef.current = 0

      // Request mic permission and start audio capture
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
          sampleRate: TARGET_SR,
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

      runningRef.current = true
      console.log('[ChordDetector] Listening started')

      // Register with GlobalAudioManager
      globalAudioManager.registerInstance(
        'chord-detector',
        'audio-api-recorder',
        recorder,
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
      setListening(false)
      runningRef.current = false
    }
  }, [loadModel, loadCqt, handleAudioBuffer, setError, setListening, stopListening])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (runningRef.current) {
        void stopListening()
      }
      cqtRef.current = null
      modelRef.current = null
    }
  }, [stopListening])

  return {
    isListening: store.isListening,
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
