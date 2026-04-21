export type BackingTrackId =
  | 'am-blues-70'
  | 'am-drone'
  | 'g-finger-80'
  | 'em-vamp-90'
  | 'g-ballad-65'

export type BackingTrackDefinition = {
  id: BackingTrackId
  /** Short user-facing title */
  label: string
  /** BPM for UI / metronome; `null` for ambient / no tempo */
  bpm: number | null
  /** Musical key hint for Jam Mode copy */
  key: string
  /** Bundled asset for `expo-av` / `Audio.Sound.createAsync` */
  source: number
  /** Filename stem for docs / debugging */
  fileName: string
  /**
   * Loop length in ms (measured once via `scripts/measure_jam_loops.mjs` / ffprobe).
   * Optional — for QA, sync hints, and docs; not required for playback.
   */
  durationMs?: number
}

export const BACKING_TRACKS: BackingTrackDefinition[] = [
  {
    id: 'am-blues-70',
    label: 'A minor — slow blues shuffle',
    bpm: 70,
    key: 'A minor',
    fileName: 'am-blues-70bpm.mp3',
    source: require('../../assets/backing-tracks/am-blues-70bpm.mp3'),
    durationMs: 24033,
  },
  {
    id: 'am-drone',
    label: 'A minor — open drone (ambient)',
    bpm: null,
    key: 'A minor',
    fileName: 'am-drone-ambient.mp3',
    source: require('../../assets/backing-tracks/am-drone-ambient.mp3'),
    durationMs: 24033,
  },
  {
    id: 'g-finger-80',
    label: 'G major — fingerpicking groove',
    bpm: 80,
    key: 'G major',
    fileName: 'g-major-fingerpicking-80bpm.mp3',
    source: require('../../assets/backing-tracks/g-major-fingerpicking-80bpm.mp3'),
    durationMs: 24033,
  },
  {
    id: 'em-vamp-90',
    label: 'E minor — two-chord vamp',
    bpm: 90,
    key: 'E minor',
    fileName: 'em-two-chord-90bpm.mp3',
    source: require('../../assets/backing-tracks/em-two-chord-90bpm.mp3'),
    durationMs: 24033,
  },
  {
    id: 'g-ballad-65',
    label: 'G major — slow ballad',
    bpm: 65,
    key: 'G major',
    fileName: 'g-major-ballad-65bpm.mp3',
    source: require('../../assets/backing-tracks/g-major-ballad-65bpm.mp3'),
    durationMs: 24033,
  },
]
