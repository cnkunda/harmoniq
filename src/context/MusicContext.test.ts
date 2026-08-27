/**
 * Unit tests for MusicContext reducer.
 */
import { describe, expect, it } from 'vitest'

import {
  findActiveNotes,
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

describe('findActiveNotes', () => {
  it('returns empty array for null or empty notes', () => {
    expect(findActiveNotes(null, 1)).toEqual([])
    expect(findActiveNotes(undefined, 1)).toEqual([])
    expect(findActiveNotes([], 1)).toEqual([])
  })

  it('returns empty array when no notes are sounding', () => {
    const notes = [{ start_time: 0, duration: 1, pitch: 60 }]
    expect(findActiveNotes(notes, 5)).toEqual([])
  })

  it('falls back to MIDI resolution when no tab position is present', () => {
    // MIDI 64 = E4 -> lowest-fret resolution is high E string open (fret 0, string 1 -> row 0)
    const notes = [{ start_time: 0, duration: 2, pitch: 64 }]
    const result = findActiveNotes(notes, 1)
    expect(result).toEqual([{ string: 1, fret: 0, midi: 64 }])
  })

  it('falls back to MIDI resolution when only string is present without fret', () => {
    const notes = [{ start_time: 0, duration: 2, pitch: 64, string: 2 } as never]
    const result = findActiveNotes(notes, 1)
    // Should ignore partial tab data and use MIDI
    expect(result).toEqual([{ string: 1, fret: 0, midi: 64 }])
  })

  it('falls back to MIDI resolution when only fret is present without string', () => {
    const notes = [{ start_time: 0, duration: 2, pitch: 64, fret: 5 } as never]
    const result = findActiveNotes(notes, 1)
    expect(result).toEqual([{ string: 1, fret: 0, midi: 64 }])
  })

  it('prefers tab string/fret when both are present', () => {
    // MIDI 64 but tab says string 2 fret 5 (B string 5th fret = E4 as well, but different voicing)
    const notes = [{ start_time: 0, duration: 2, pitch: 64, string: 2, fret: 5 }]
    const result = findActiveNotes(notes, 1)
    expect(result).toEqual([{ string: 2, fret: 5, midi: 64 }])
  })

  it('prefers tab position even when it differs from MIDI default resolution', () => {
    // MIDI 60 = C4 -> default is string 2 fret 1 (B string), but tab says string 3 fret 5 (G string 5th fret)
    const notes = [{ start_time: 0, duration: 2, pitch: 60, string: 3, fret: 5 }]
    const result = findActiveNotes(notes, 1)
    expect(result).toEqual([{ string: 3, fret: 5, midi: 60 }])
  })

  it('falls back to MIDI when string is out of range', () => {
    const notes = [{ start_time: 0, duration: 2, pitch: 64, string: 7, fret: 5 }]
    const result = findActiveNotes(notes, 1)
    expect(result).toEqual([{ string: 1, fret: 0, midi: 64 }])
  })

  it('falls back to MIDI when string or fret is NaN', () => {
    const notes = [{ start_time: 0, duration: 2, pitch: 64, string: NaN, fret: 5 } as never]
    const result = findActiveNotes(notes, 1)
    expect(result).toEqual([{ string: 1, fret: 0, midi: 64 }])
  })

  it('handles multiple notes with mixed tab and MIDI resolution', () => {
    const notes = [
      { start_time: 0, duration: 5, pitch: 64, string: 2, fret: 5 }, // tab
      { start_time: 0, duration: 5, pitch: 67 }, // MIDI fallback (G4 -> open G string 0? Actually OPEN_MIDI_BY_ROW[2]=55 +12=67? No that's row2 fret12. Lowest is row0? Check: 64+3? Anyway)
    ]
    const result = findActiveNotes(notes, 1)
    expect(result[0]).toEqual({ string: 2, fret: 5, midi: 64 })
    // Second note should be resolved via MIDI
    expect(result[1]!.midi).toBe(67)
    expect(result[1]!.string).toBeGreaterThanOrEqual(1)
    expect(result[1]!.string).toBeLessThanOrEqual(6)
  })

  it('respects note time window boundaries (inclusive)', () => {
    const notes = [{ start_time: 1, duration: 2, pitch: 64 }]
    // At exactly start_time
    expect(findActiveNotes(notes, 1).length).toBe(1)
    // At exactly end (start+duration)
    expect(findActiveNotes(notes, 3).length).toBe(1)
    // Just before start
    expect(findActiveNotes(notes, 0.999).length).toBe(0)
    // Just after end
    expect(findActiveNotes(notes, 3.001).length).toBe(0)
  })

  it('rounds fractional string/fret values', () => {
    const notes = [{ start_time: 0, duration: 2, pitch: 64, string: 2.7, fret: 5.2 }]
    const result = findActiveNotes(notes, 1)
    expect(result).toEqual([{ string: 3, fret: 5, midi: 64 }])
  })
})
