export type BeatMetronomeParams = {
  beatGrid: number[]
  tempoBpm: number
  /** Same axis as stem mixer rate (updated each tick). */
  getPlaybackRate: () => number
  /** Called to read current song timeline position in seconds (same axis as beat_grid). */
  getSongPositionSeconds: () => number
  isPlaying: () => boolean
}

export type BeatMetronome = {
  /** Start scheduling clicks; idempotent. */
  start(params: BeatMetronomeParams): void
  /** Stop all scheduled clicks and timers. */
  stop(): void
}
