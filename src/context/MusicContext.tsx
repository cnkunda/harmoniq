/**
 * MusicContext - Shared synchronized state for playback, AlphaTab, and fretboard.
 *
 * Uses useReducer + React Context to hold state that all music-related components
 * read from. This ensures playback position, current chord, active notes, and bar
 * position stay synchronized across the AlphaTab score view, the fretboard diagram,
 * and the audio playback controls.
 *
 * Producers (dispatch actions):
 *   - SessionStemAndTab (audio playback) → SET_POSITION, SET_PLAYING
 *   - AlphaTab/ScoreViewer → SET_PLAYER_READY, SET_BEAT (on beat events)
 *
 * Consumers (read state):
 *   - FretboardDiagram → currentChord, activeNotes
 *   - ScoreViewer (AlphaTab) → currentBar (for cursor sync), isPlaying
 *   - Playback UI → isPlaying, playerReady
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type Dispatch,
  type ReactNode,
} from 'react'

import { allCellsForMidi } from '@/src/music/fretboardCell'

/** A single sounding note on the guitar. */
export type ActiveNote = {
  string: number // 1-6 (1 = high E)
  fret: number // 0-24
  midi?: number
}

/** A chord event in time (timestamp in seconds). */
export type ChordEvent = {
  timestamp: number
  chord: string
  confidence?: number
}

/** A solo note event (start time/duration in seconds, MIDI pitch). */
export type SoloNoteEvent = {
  start_time: number
  duration: number
  pitch: number
  velocity?: number
}

export type MusicState = {
  /** Current chord symbol at playhead, e.g. "Am", "Dm". Null when in "no chord" region. */
  currentChord: string | null
  /** Currently sounding notes (string/fret positions). */
  activeNotes: ActiveNote[]
  /** 0-indexed bar position at playhead. */
  currentBar: number
  /** Current playback position in milliseconds. */
  positionMs: number
  /** True while audio is playing. */
  isPlaying: boolean
  /** True after AlphaTab finishes loading its soundfont. */
  playerReady: boolean
}

export const INITIAL_MUSIC_STATE: MusicState = {
  currentChord: null,
  activeNotes: [],
  currentBar: 0,
  positionMs: 0,
  isPlaying: false,
  playerReady: false,
}

export type MusicAction =
  | { type: 'SET_BEAT'; bar: number }
  | { type: 'SET_PLAYING'; playing: boolean }
  | { type: 'SET_PLAYER_READY'; ready: boolean }
  | {
      type: 'SET_POSITION'
      positionMs: number
      currentChord: string | null
      activeNotes: ActiveNote[]
      currentBar: number
    }

export function musicReducer(state: MusicState, action: MusicAction): MusicState {
  switch (action.type) {
    case 'SET_BEAT':
      if (state.currentBar === action.bar) return state
      return { ...state, currentBar: action.bar }
    case 'SET_PLAYING':
      if (state.isPlaying === action.playing) return state
      return { ...state, isPlaying: action.playing }
    case 'SET_PLAYER_READY':
      if (state.playerReady === action.ready) return state
      return { ...state, playerReady: action.ready }
    case 'SET_POSITION':
      return {
        ...state,
        positionMs: action.positionMs,
        currentChord: action.currentChord,
        activeNotes: action.activeNotes,
        currentBar: action.currentBar,
      }
    default:
      return state
  }
}

/**
 * Helper actions exposed alongside the raw dispatch. These compute derived
 * state (current chord, active notes, current bar) from the timeline data
 * the provider was configured with.
 */
type MusicActions = {
  /** Update playback position; computes current chord, active notes, and current bar. */
  setPosition: (positionMs: number) => void
  /** Toggle playback. */
  setPlaying: (playing: boolean) => void
  /** Mark AlphaTab as ready. */
  setPlayerReady: (ready: boolean) => void
  /** Set current bar (typically from AlphaTab beat events). */
  setBeat: (bar: number) => void
}

type MusicContextValue = {
  state: MusicState
  dispatch: Dispatch<MusicAction>
  actions: MusicActions
}

const MusicContext = createContext<MusicContextValue | null>(null)

export type MusicProviderProps = {
  children: ReactNode
  /** Beat-aligned chord events (typically from lesson.chord_timeline). */
  chordEvents?: ChordEvent[] | null
  /** Solo note events (typically from lesson.solo_notes). */
  soloNotes?: SoloNoteEvent[] | null
  /** Bar start timestamps in seconds (typically from lesson.bar_timestamps). */
  barTimestamps?: number[] | null
}

/**
 * Find the chord active at the given time. Returns null if no chord or in an "N"
 * (no chord) region.
 */
function findCurrentChord(events: ChordEvent[] | null | undefined, timeSec: number): string | null {
  if (!events || events.length === 0) return null
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i]!
    if (e.timestamp <= timeSec) {
      if (!e.chord || e.chord === 'N') return null
      return e.chord
    }
  }
  return null
}

/**
 * Find all notes sounding at the given time.
 */
function findActiveNotes(
  notes: SoloNoteEvent[] | null | undefined,
  timeSec: number,
): ActiveNote[] {
  if (!notes || notes.length === 0) return []
  const out: ActiveNote[] = []
  for (const note of notes) {
    const end = note.start_time + note.duration
    if (note.start_time <= timeSec && end >= timeSec) {
      const cells = allCellsForMidi(note.pitch)
      const cell = cells[0]
      if (cell) {
        out.push({ string: cell.row + 1, fret: cell.fret, midi: note.pitch })
      }
    }
  }
  return out
}

/**
 * Find the current bar (0-indexed) given an array of bar start timestamps.
 */
function findCurrentBar(barTimestamps: number[] | null | undefined, timeSec: number): number {
  if (!barTimestamps || barTimestamps.length === 0) return 0
  for (let i = barTimestamps.length - 1; i >= 0; i--) {
    if (barTimestamps[i]! <= timeSec) return i
  }
  return 0
}

export function MusicProvider({
  children,
  chordEvents,
  soloNotes,
  barTimestamps,
}: MusicProviderProps) {
  const [state, dispatch] = useReducer(musicReducer, INITIAL_MUSIC_STATE)

  const setPosition = useCallback(
    (positionMs: number) => {
      const timeSec = positionMs / 1000
      const currentChord = findCurrentChord(chordEvents, timeSec)
      const activeNotes = findActiveNotes(soloNotes, timeSec)
      const currentBar = findCurrentBar(barTimestamps, timeSec)
      dispatch({
        type: 'SET_POSITION',
        positionMs,
        currentChord,
        activeNotes,
        currentBar,
      })
    },
    [chordEvents, soloNotes, barTimestamps],
  )

  const setPlaying = useCallback((playing: boolean) => {
    dispatch({ type: 'SET_PLAYING', playing })
  }, [])

  const setPlayerReady = useCallback((ready: boolean) => {
    dispatch({ type: 'SET_PLAYER_READY', ready })
  }, [])

  const setBeat = useCallback((bar: number) => {
    dispatch({ type: 'SET_BEAT', bar })
  }, [])

  const actions = useMemo<MusicActions>(
    () => ({ setPosition, setPlaying, setPlayerReady, setBeat }),
    [setPosition, setPlaying, setPlayerReady, setBeat],
  )

  const value = useMemo<MusicContextValue>(() => ({ state, dispatch, actions }), [state, actions])

  return <MusicContext.Provider value={value}>{children}</MusicContext.Provider>
}

/** Hook to access the music context. Must be used inside <MusicProvider>. */
export function useMusic(): MusicContextValue {
  const ctx = useContext(MusicContext)
  if (!ctx) {
    throw new Error('useMusic must be used inside <MusicProvider>')
  }
  return ctx
}

/** Hook to access just the state (read-only consumers). */
export function useMusicState(): MusicState {
  return useMusic().state
}

/** Hook to access just the actions (dispatchers). */
export function useMusicActions(): MusicActions {
  return useMusic().actions
}
