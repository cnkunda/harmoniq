export type RecordedTake = {
  durationMs: number
  audioBytes: Uint8Array
  mimeType: string
}

export interface SessionRecorder {
  start(): Promise<void>
  stop(): Promise<RecordedTake>
  isRecording(): boolean
}
