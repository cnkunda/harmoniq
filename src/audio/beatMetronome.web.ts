import type { BeatMetronome, BeatMetronomeParams } from './beatMetronome.types'

const CLICK_S = 0.028
const FREQ_HZ = 1560

function beatPeriodSeconds(grid: number[], tempoBpm: number): number {
  const sorted = [...grid].filter((t) => Number.isFinite(t)).sort((a, b) => a - b)
  if (sorted.length >= 2) {
    return Math.max(0.04, sorted[1]! - sorted[0]!)
  }
  if (tempoBpm > 0) return 60 / tempoBpm
  return 0.5
}

function iterBeatsFrom(
  grid: number[],
  fromSongTime: number,
  tempoBpm: number,
  maxSongAhead: number,
): number[] {
  const sorted = [...grid].filter((t) => Number.isFinite(t)).sort((a, b) => a - b)
  const out: number[] = []
  const period = beatPeriodSeconds(grid, tempoBpm)

  if (sorted.length === 0) return out

  let i = 0
  while (i < sorted.length && sorted[i]! < fromSongTime - 1e-3) i += 1
  for (; i < sorted.length; i += 1) {
    const b = sorted[i]!
    if (b >= fromSongTime - 1e-3 && b <= fromSongTime + maxSongAhead) out.push(b)
  }

  let t = sorted[sorted.length - 1]! + period
  while (t <= fromSongTime + maxSongAhead) {
    if (t >= fromSongTime - 1e-3) out.push(t)
    t += period
  }
  return out
}

/**
 * Web Audio metronome: schedules short clicks aligned to `beat_grid` + shared transport.
 */
export function createWebBeatMetronome(audioContext: AudioContext): BeatMetronome {
  let params: BeatMetronomeParams | null = null
  let raf = 0
  const firedBeatMs = new Set<number>()
  let lastPos = -1

  const playClick = (whenCtx: number) => {
    const g = audioContext.createGain()
    g.gain.setValueAtTime(0.0001, whenCtx)
    g.gain.exponentialRampToValueAtTime(0.22, whenCtx + 0.004)
    g.gain.exponentialRampToValueAtTime(0.0001, whenCtx + CLICK_S)
    g.connect(audioContext.destination)

    const osc = audioContext.createOscillator()
    osc.type = 'square'
    osc.frequency.setValueAtTime(FREQ_HZ, whenCtx)
    osc.connect(g)
    osc.start(whenCtx)
    osc.stop(whenCtx + CLICK_S + 0.002)
  }

  const tick = () => {
    raf = requestAnimationFrame(tick)
    if (!params || !params.isPlaying()) return

    const pos = params.getSongPositionSeconds()
    if (lastPos >= 0 && Math.abs(pos - lastPos) > 0.35) {
      firedBeatMs.clear()
    }
    lastPos = pos

    const grid = params.beatGrid
    if (grid.length === 0) return

    const rate = Math.max(0.05, params.getPlaybackRate())
    const tempo = params.tempoBpm > 0 ? params.tempoBpm : 120
    const nowCtx = audioContext.currentTime
    const horizonSong = 1.8 * rate

    const beats = iterBeatsFrom(grid, pos, tempo, horizonSong)
    for (const beatSong of beats) {
      const deltaSong = beatSong - pos
      if (deltaSong < -0.02) continue
      const whenCtxClick = nowCtx + deltaSong / rate
      if (whenCtxClick < nowCtx + 0.008 || whenCtxClick > nowCtx + 2.5) continue

      const key = Math.round(beatSong * 1000)
      if (firedBeatMs.has(key)) continue
      firedBeatMs.add(key)
      playClick(whenCtxClick)
    }

    if (firedBeatMs.size > 200) {
      firedBeatMs.clear()
    }
  }

  return {
    start(p: BeatMetronomeParams) {
      params = p
      firedBeatMs.clear()
      lastPos = -1
      if (raf) cancelAnimationFrame(raf)
      raf = requestAnimationFrame(tick)
    },
    stop() {
      params = null
      firedBeatMs.clear()
      lastPos = -1
      if (raf) cancelAnimationFrame(raf)
      raf = 0
    },
  }
}
