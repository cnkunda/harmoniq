import { Audio } from 'expo-av'

import type { BeatMetronome, BeatMetronomeParams } from './beatMetronome.types'

function beatPeriodSeconds(grid: number[], tempoBpm: number): number {
  const sorted = [...grid].filter((t) => Number.isFinite(t)).sort((a, b) => a - b)
  if (sorted.length >= 2) {
    return Math.max(0.04, sorted[1]! - sorted[0]!)
  }
  if (tempoBpm > 0) return 60 / tempoBpm
  return 0.5
}

function iterBeatsNear(
  grid: number[],
  posSong: number,
  tempoBpm: number,
  windowHalf: number,
): number[] {
  const sorted = [...grid].filter((t) => Number.isFinite(t)).sort((a, b) => a - b)
  const out: number[] = []
  const period = beatPeriodSeconds(grid, tempoBpm)

  for (const b of sorted) {
    if (b >= posSong - windowHalf && b <= posSong + windowHalf) out.push(b)
  }

  let t = sorted.length > 0 ? sorted[sorted.length - 1]! : 0
  while (t < posSong - windowHalf) t += period
  while (t <= posSong + windowHalf) {
    if (!out.some((x) => Math.abs(x - t) < 1e-3)) out.push(t)
    t += period
  }
  return out.sort((a, b) => a - b)
}

let clickSound: Audio.Sound | null = null

async function ensureClickSound(): Promise<Audio.Sound> {
  if (clickSound) return clickSound
  await Audio.setAudioModeAsync({
    playsInSilentModeIOS: true,
    allowsRecordingIOS: false,
  })
  const { sound } = await Audio.Sound.createAsync(
    require('../../assets/metronome-click.wav'),
    { shouldPlay: false, volume: 0.85, isLooping: false },
  )
  clickSound = sound
  return sound
}

/**
 * Native metronome: polls timeline and plays a short WAV near each grid hit.
 */
export function createNativeBeatMetronome(): BeatMetronome {
  let interval: ReturnType<typeof setInterval> | null = null
  let params: BeatMetronomeParams | null = null
  const firedBeatMs = new Set<number>()
  let lastPos = -1

  const tick = () => {
    void (async () => {
      if (!params || !params.isPlaying()) return
      const pos = params.getSongPositionSeconds()
      if (lastPos >= 0 && Math.abs(pos - lastPos) > 0.35) {
        firedBeatMs.clear()
      }
      lastPos = pos

      const grid = params.beatGrid
      if (grid.length === 0) return

      const tempo = params.tempoBpm > 0 ? params.tempoBpm : 120
      const rate = Math.max(0.05, params.getPlaybackRate())
      const win = 0.06 * rate
      const beats = iterBeatsNear(grid, pos, tempo, win)

      for (const b of beats) {
        const delta = b - pos
        if (delta < -0.035 || delta > 0.055) continue
        const key = Math.round(b * 1000)
        if (firedBeatMs.has(key)) continue
        firedBeatMs.add(key)
        try {
          const s = await ensureClickSound()
          await s.setPositionAsync(0)
          await s.playAsync()
        } catch {
          /* ignore click failures */
        }
      }

      if (firedBeatMs.size > 200) firedBeatMs.clear()
    })()
  }

  return {
    start(p: BeatMetronomeParams) {
      params = p
      firedBeatMs.clear()
      lastPos = -1
      if (interval) clearInterval(interval)
      interval = setInterval(tick, 40)
    },
    stop() {
      params = null
      if (interval) clearInterval(interval)
      interval = null
      firedBeatMs.clear()
      lastPos = -1
    },
  }
}
