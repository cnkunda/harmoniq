/** A single chord detection result from the on-device inference pipeline. */
export interface ChordDetection {
  /** Chord label in MIREX format (e.g. "C:maj", "A:min", "N"). */
  chord: string
  /** Model confidence: 0–1 (max softmax probability). */
  confidence: number
  /** Timestamp when the detection was produced (Date.now()). */
  timestamp: number
  /** Inference latency in milliseconds (CQT + model run). */
  latencyMs: number
}

/** Lifecycle status of the detector, for UX feedback. */
export type ChordDetectorStatus =
  | 'idle'
  | 'initializing'
  | 'warming'
  | 'listening'

/** State of the live chord detector. */
export interface ChordDetectorState {
  /** Whether the detector is actively listening and inferring. */
  isListening: boolean
  /** Fine-grained lifecycle status for UI (loading model, warming up, live). */
  status: ChordDetectorStatus
  /** Most recent chord detection (null before first inference). */
  currentChord: ChordDetection | null
  /** Ring buffer of recent detections (newest first, max 8). */
  history: readonly ChordDetection[]
  /** Last measured inference latency in ms. */
  latencyMs: number
  /** Error message if the detector failed to start or crashed. */
  error: string | null
  /** Underlying model type loaded (for display). */
  modelType: 'tflite' | 'onnx' | null
}

/** Maximum number of chord history entries to keep. */
export const MAX_HISTORY = 8
