import type { BeatMetronome, BeatMetronomeParams } from './beatMetronome.types'
import { collectClickTimesInRange, type MetronomeSubdivision } from './metronomeShared'

const LOOKAHEAD_MS = 25
const HORIZON_SONG_SEC = 0.12
const CLICK_S = 0.026

function playOscClick(
  audioContext: AudioContext,
  whenCtx: number,
  freqHz: number,
): void {
  const g = audioContext.createGain()
  g.gain.setValueAtTime(0.0001, whenCtx)
  g.gain.exponentialRampToValueAtTime(0.2, whenCtx + 0.003)
  g.gain.exponentialRampToValueAtTime(0.0001, whenCtx + CLICK_S)
  g.connect(audioContext.destination)

  const osc = audioContext.createOscillator()
  osc.type = 'square'
  osc.frequency.setValueAtTime(freqHz, whenCtx)
  osc.connect(g)
  osc.start(whenCtx)
  osc.stop(whenCtx + CLICK_S + 0.002)
}

/**
 * Web: lookahead scheduler on AudioContext clock (25ms tick, ~120ms song-ahead horizon).
 */
export function createWebBeatMetronome(audioContext: AudioContext): BeatMetronome {
  let params: BeatMetronomeParams | null = null
  let timer: ReturnType<typeof setInterval> | null = null
  const firedSongMs = new Set<number>()
  let lastPos = -1

  const tick = () => {
    if (!params || !params.isPlaying()) return

    const pos = params.getSongPositionSecondsNow?.() ?? params.getSongPositionSeconds()
    if (lastPos >= 0 && Math.abs(pos - lastPos) > 0.35) {
      firedSongMs.clear()
    }
    lastPos = pos

    const grid = params.beatGrid
    if (grid.length === 0) return

    const rate = Math.max(0.05, params.getPlaybackRate())
    const tempo = params.tempoBpm > 0 ? params.tempoBpm : 120
    const subdiv = (params.subdivision ?? 1) as MetronomeSubdivision
    const nowCtx = audioContext.currentTime
    const toSong = pos + HORIZON_SONG_SEC

    const clicks = collectClickTimesInRange(grid, tempo, pos - 1e-4, toSong, subdiv, {
      barTimestamps: params.barTimestamps,
    })
    for (const { songTime, isDownbeat } of clicks) {
      const deltaSong = songTime - pos
      if (deltaSong < -0.02) continue
      const whenCtx = nowCtx + deltaSong / rate
      if (whenCtx < nowCtx + 0.004 || whenCtx > nowCtx + 2.8) continue

      const key = Math.round(songTime * 1000)
      if (firedSongMs.has(key)) continue
      firedSongMs.add(key)

      const freq = isDownbeat ? 1880 : 1040
      playOscClick(audioContext, whenCtx, freq)
      params.onBeatFlash?.({ isDownbeat })
    }

    if (firedSongMs.size > 400) firedSongMs.clear()
  }

  return {
    start(p: BeatMetronomeParams) {
      params = p
      firedSongMs.clear()
      lastPos = -1
      if (timer) clearInterval(timer)
      timer = setInterval(tick, LOOKAHEAD_MS)
      tick()
    },
    stop() {
      params = null
      firedSongMs.clear()
      lastPos = -1
      if (timer) clearInterval(timer)
      timer = null
    },
  }
}
