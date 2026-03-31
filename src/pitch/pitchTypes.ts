export interface PitchReading {
  hz: number
  midi: number
  cents: number
  noteName: string
}

export interface PitchStream {
  start(onPitch: (reading: PitchReading) => void): Promise<void>
  stop(): Promise<void>
  isRunning(): boolean
}
