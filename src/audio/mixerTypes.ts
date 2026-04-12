/** Metro `require()` module id for a bundled audio asset */
export type StemAssetModule = number

export type StemDefinition = {
  id: string
  label: string
  /** Bundled asset from `require('…wav')` */
  source?: StemAssetModule
  /** Remote http(s) URL (lesson stems from `/lesson-file`) */
  uri?: string
}

function stemDefValid(def: StemDefinition): boolean {
  const hasSource = def.source != null
  const hasUri = def.uri != null && def.uri.length > 0
  return hasSource !== hasUri
}

export function assertStemDefinitions(stems: StemDefinition[]): void {
  for (const s of stems) {
    if (!stemDefValid(s)) {
      throw new Error(`Stem ${s.id}: provide exactly one of source (bundled) or uri`)
    }
  }
}

/**
 * Multi-stem playback with per-stem linear gain (0 = silent, 1 = full).
 * Implementations: parallel `expo-av` sounds (native) or Web Audio (web).
 */
export interface StemMixer {
  load(stems: StemDefinition[]): Promise<void>
  play(): Promise<void>
  pause(): Promise<void>
  setStemGain(stemId: string, linearGain: number): Promise<void>
  /** Seek all stems to a position in seconds (modulo duration when looping). */
  seek(positionSeconds: number): Promise<void>
  /** Playback rate (e.g. 0.75–1.25). */
  setPlaybackRate(rate: number): Promise<void>
  /** Current timeline position in seconds. */
  getPositionSeconds(): Promise<number>
  /**
   * Same axis as `getPositionSeconds` but synchronous (Web Audio clock).
   * Used by the metronome scheduler; web implements, native omits.
   */
  getPositionSecondsNow?: () => number
  /** Longest stem duration after load; 0 before load. */
  getDurationSeconds(): number
  /** Web-only: shared clock for metronome (optional). */
  getAudioContext?: () => AudioContext | null
  unload(): Promise<void>
}
