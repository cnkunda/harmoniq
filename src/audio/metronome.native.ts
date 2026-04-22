import { Audio } from 'expo-av'

import type { BeatMetronome, BeatMetronomeParams } from './beatMetronome.types'
import { globalAudioManager } from './GlobalAudioManager'
import { beatPeriodSeconds, collectClickTimesInRange, type MetronomeSubdivision } from './metronomeShared'

/**
 * Native metronome: 25ms poll + short hi/lo WAV samples.
 *
 * Jitter: Expo `playAsync` + JS timer variance typically lands within ~20–80ms of the
 * ideal grid (device-dependent). Acceptable for v1 per PRIORITIES §50; web uses
 * sample-accurate scheduling instead.
 */
const POLL_MS = 25
const NATIVE_WINDOW_BEFORE = 0.055
const NATIVE_WINDOW_AFTER = 0.08

let hiSound: Audio.Sound | null = null
let loSound: Audio.Sound | null = null
let metronomeInstanceId = `metronome-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`

async function ensureSounds(): Promise<{ hi: Audio.Sound; lo: Audio.Sound }> {
  if (hiSound && loSound) return { hi: hiSound, lo: loSound }
  await globalAudioManager.resetToPlaybackMode()
  const [hi, lo] = await Promise.all([
    Audio.Sound.createAsync(require('../../assets/audio/click-hi.wav'), {
      shouldPlay: false,
      volume: 0.92,
      isLooping: false,
    }),
    Audio.Sound.createAsync(require('../../assets/audio/click-lo.wav'), {
      shouldPlay: false,
      volume: 0.72,
      isLooping: false,
    }),
  ])
  hiSound = hi.sound
  loSound = lo.sound

  // Register metronome sounds with GlobalAudioManager
  globalAudioManager.registerInstance(
    metronomeInstanceId,
    'expo-sound',
    { hi: hiSound, lo: loSound },
    async () => {
      if (hiSound) await hiSound.unloadAsync().catch(() => {})
      if (loSound) await loSound.unloadAsync().catch(() => {})
      hiSound = null
      loSound = null
    },
  )

  return { hi: hiSound, lo: loSound }
}

export function createNativeBeatMetronome(): BeatMetronome {
  let interval: ReturnType<typeof setInterval> | null = null
  let params: BeatMetronomeParams | null = null
  const firedSongMs = new Set<number>()
  let lastPos = -1

  const tick = () => {
    void (async () => {
      if (!params || !params.isPlaying()) return
      const posRaw = params.getSongPositionSecondsNow?.() ?? params.getSongPositionSeconds()
      const alignOff = params.beatAlignOffsetSec ?? 0
      const pos = posRaw - alignOff
      if (lastPos >= 0 && Math.abs(pos - lastPos) > 0.35) {
        firedSongMs.clear()
      }
      lastPos = pos

      const grid = params.beatGrid ?? []
      const rate = Math.max(0.05, params.getPlaybackRate())
      const tempo = params.tempoBpm > 0 ? params.tempoBpm : 120
      const subdiv = (params.subdivision ?? 1) as MetronomeSubdivision
      const stretch = Math.max(1, Math.sqrt(1 / Math.min(rate, 1)))
      const quarterPeriod = beatPeriodSeconds(grid, tempo)
      const minAfter = quarterPeriod / Math.max(1, subdiv)
      const from = pos - NATIVE_WINDOW_BEFORE * stretch
      const to = pos + Math.max(NATIVE_WINDOW_AFTER * stretch, minAfter)
      const clicks = collectClickTimesInRange(grid, tempo, from, to, subdiv, {
        barTimestamps: params.barTimestamps,
      })

      let sounds: { hi: Audio.Sound; lo: Audio.Sound } | null = null
      for (const { songTime, isDownbeat } of clicks) {
        const delta = songTime - pos
        const late = 0.045 * stretch
        const early = 0.07 * stretch
        if (delta < -late || delta > early) continue
        const key = Math.round(songTime * 1000)
        if (firedSongMs.has(key)) continue
        firedSongMs.add(key)
        try {
          if (!sounds) sounds = await ensureSounds()
          const s = isDownbeat ? sounds.hi : sounds.lo
          await s.setPositionAsync(0)
          await s.playAsync()
          params.onBeatFlash?.({ isDownbeat })
        } catch {
          /* ignore click failures */
        }
      }

      if (firedSongMs.size > 400) firedSongMs.clear()
    })()
  }

  return {
    start(p: BeatMetronomeParams) {
      params = p
      firedSongMs.clear()
      lastPos = -1
      if (interval) clearInterval(interval)
      interval = setInterval(tick, POLL_MS)
    },
    stop() {
      params = null
      if (interval) clearInterval(interval)
      interval = null
      firedSongMs.clear()
      lastPos = -1
    },
  }
}
