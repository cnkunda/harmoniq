import type { MetronomeSubdivision } from './metronomeShared'

export type BeatMetronomeParams = {
  beatGrid: number[]
  /** Bar line times (seconds) from lesson; improves downbeat vs grid phase. */
  barTimestamps?: number[]
  tempoBpm: number
  /** Same axis as stem mixer rate (updated each tick). */
  getPlaybackRate: () => number
  /** Called to read current song timeline position in seconds (same axis as beat_grid). */
  getSongPositionSeconds: () => number
  /**
   * When provided (web stem mixer), used for scheduling so clicks align with the same
   * AudioContext clock as stems. Falls back to `getSongPositionSeconds` if omitted.
   */
  getSongPositionSecondsNow?: () => number
  isPlaying: () => boolean
  /** 1 = quarters, 2 = eighths, 4 = sixteenths (relative to quarter period). */
  subdivision?: MetronomeSubdivision
  /** Visual pulse aligned with scheduled/heard clicks (Listen / Slow / Play). */
  onBeatFlash?: (info: { isDownbeat: boolean }) => void
}

export type BeatMetronome = {
  /** Start scheduling clicks; idempotent. */
  start(params: BeatMetronomeParams): void
  /** Stop all scheduled clicks and timers. */
  stop(): void
}
