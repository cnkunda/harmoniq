export interface PitchReading {
  /** Present when a fundamental was estimated; omit on sub-threshold frames (web). */
  hz?: number
  midi: number
  cents: number
  noteName: string
  /** RMS level of the analysis frame (amplitude proxy for dynamics / ghost gating). */
  rms: number
  peakAbs?: number
}

export interface PitchStream {
  start(onPitch: (reading: PitchReading) => void): Promise<void>
  stop(): Promise<void>
  isRunning(): boolean
}
