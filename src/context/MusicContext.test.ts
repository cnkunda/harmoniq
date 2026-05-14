/**
 * Unit tests for MusicContext reducer.
 */
import { describe, expect, it } from 'vitest'

import {
  INITIAL_MUSIC_STATE,
  musicReducer,
  type MusicAction,
  type MusicState,
} from './MusicContext'

describe('musicReducer', () => {
  it('starts with sensible defaults', () => {
    expect(INITIAL_MUSIC_STATE).toEqual({
      currentChord: null,
      activeNotes: [],
      currentBar: 0,
      positionMs: 0,
      isPlaying: false,
      playerReady: false,
    })
  })

  it('SET_PLAYING toggles isPlaying', () => {
    const next = musicReducer(INITIAL_MUSIC_STATE, { type: 'SET_PLAYING', playing: true })
    expect(next.isPlaying).toBe(true)
  })

  it('SET_PLAYING returns same reference when value unchanged (referential equality)', () => {
    const next = musicReducer(INITIAL_MUSIC_STATE, { type: 'SET_PLAYING', playing: false })
    expect(next).toBe(INITIAL_MUSIC_STATE)
  })

  it('SET_PLAYER_READY toggles playerReady', () => {
    const next = musicReducer(INITIAL_MUSIC_STATE, { type: 'SET_PLAYER_READY', ready: true })
    expect(next.playerReady).toBe(true)
  })

  it('SET_BEAT updates currentBar', () => {
    const next = musicReducer(INITIAL_MUSIC_STATE, { type: 'SET_BEAT', bar: 4 })
    expect(next.currentBar).toBe(4)
  })

  it('SET_BEAT short-circuits when bar unchanged', () => {
    const state: MusicState = { ...INITIAL_MUSIC_STATE, currentBar: 3 }
    const next = musicReducer(state, { type: 'SET_BEAT', bar: 3 })
    expect(next).toBe(state)
  })

  it('SET_POSITION updates positionMs, chord, notes, and bar together', () => {
    const action: MusicAction = {
      type: 'SET_POSITION',
      positionMs: 1234,
      currentChord: 'Am',
      activeNotes: [{ string: 3, fret: 2 }],
      currentBar: 2,
    }
    const next = musicReducer(INITIAL_MUSIC_STATE, action)
    expect(next.positionMs).toBe(1234)
    expect(next.currentChord).toBe('Am')
    expect(next.activeNotes).toEqual([{ string: 3, fret: 2 }])
    expect(next.currentBar).toBe(2)
  })

  it('SET_POSITION preserves isPlaying and playerReady flags', () => {
    const state: MusicState = { ...INITIAL_MUSIC_STATE, isPlaying: true, playerReady: true }
    const next = musicReducer(state, {
      type: 'SET_POSITION',
      positionMs: 500,
      currentChord: 'C',
      activeNotes: [],
      currentBar: 0,
    })
    expect(next.isPlaying).toBe(true)
    expect(next.playerReady).toBe(true)
  })
})
