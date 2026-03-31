/** Metro `require()` module id for a bundled audio asset */
export type StemAssetModule = number

export type StemDefinition = {
  id: string
  label: string
  source: StemAssetModule
}

/**
 * Multi-stem playback with per-stem linear gain (0 = silent, 1 = full).
 * Implementations: parallel `expo-av` sounds (native) or Web Audio `GainNode` graph (web).
 */
export interface StemMixer {
  load(stems: StemDefinition[]): Promise<void>
  play(): Promise<void>
  pause(): Promise<void>
  setStemGain(stemId: string, linearGain: number): Promise<void>
  unload(): Promise<void>
}
