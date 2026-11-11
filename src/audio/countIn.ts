/** Count-in clicks before transport start (P1). */

import { Audio } from 'expo-av'
import { Platform } from 'react-native'

import { globalAudioManager } from '@/src/audio/GlobalAudioManager'
import { countInBeatPeriodMs, isCountInDownbeat } from '@/src/audio/countInShared'

export type CountInResult = 'completed' | 'cancelled'

export type CountInOptions = {
  bpm: number
  /** Total clicks (e.g. one bar = time-signature numerator). */
  beats: number
  /** Click every N beats uses the high sample (default 4). */
  beatsPerBar?: number
  /** Called as each click fires (1-based beat index). */
  onBeat?: (beatIndex: number, downbeat: boolean) => void
  signal?: AbortSignal
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function wasCancelled(signal?: AbortSignal): boolean {
  return signal?.aborted === true
}

async function playWebCountIn(opts: CountInOptions, periodMs: number): Promise<CountInResult> {
  const AudioContextCtor: typeof AudioContext | undefined =
    typeof globalThis !== 'undefined'
      ? ((globalThis as unknown as { AudioContext?: typeof AudioContext }).AudioContext ??
        (globalThis as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext)
      : undefined
  if (!AudioContextCtor) {
    // No audio context: keep timing so the transport still starts on the right beat.
    for (let i = 1; i <= opts.beats; i += 1) {
      if (wasCancelled(opts.signal)) return 'cancelled'
      opts.onBeat?.(i, isCountInDownbeat(i, opts.beatsPerBar ?? 4))
      await sleep(periodMs)
    }
    return 'completed'
  }

  const ctx = new AudioContextCtor()
  try {
    await ctx.resume()
    for (let i = 1; i <= opts.beats; i += 1) {
      if (wasCancelled(opts.signal)) return 'cancelled'
      const downbeat = isCountInDownbeat(i, opts.beatsPerBar ?? 4)
      const when = ctx.currentTime + 0.01
      const gain = ctx.createGain()
      gain.gain.setValueAtTime(0.0001, when)
      gain.gain.exponentialRampToValueAtTime(0.22, when + 0.003)
      gain.gain.exponentialRampToValueAtTime(0.0001, when + 0.03)
      gain.connect(ctx.destination)
      const osc = ctx.createOscillator()
      osc.type = 'square'
      osc.frequency.setValueAtTime(downbeat ? 1880 : 1040, when)
      osc.connect(gain)
      osc.start(when)
      osc.stop(when + 0.035)
      opts.onBeat?.(i, downbeat)
      await sleep(periodMs)
    }
    return 'completed'
  } finally {
    void ctx.close().catch(() => {})
  }
}

async function playNativeCountIn(opts: CountInOptions, periodMs: number): Promise<CountInResult> {
  await globalAudioManager.resetToPlaybackMode()
  const [hi, lo] = await Promise.all([
    Audio.Sound.createAsync(require('../../assets/audio/click-hi.wav'), {
      shouldPlay: false,
      volume: 0.92,
    }),
    Audio.Sound.createAsync(require('../../assets/audio/click-lo.wav'), {
      shouldPlay: false,
      volume: 0.72,
    }),
  ])
  try {
    for (let i = 1; i <= opts.beats; i += 1) {
      if (wasCancelled(opts.signal)) return 'cancelled'
      const downbeat = isCountInDownbeat(i, opts.beatsPerBar ?? 4)
      const sound = downbeat ? hi.sound : lo.sound
      try {
        await sound.setPositionAsync(0)
        await sound.playAsync()
      } catch {
        /* click audio is best-effort; timing still advances */
      }
      opts.onBeat?.(i, downbeat)
      await sleep(periodMs)
    }
    return 'completed'
  } finally {
    void hi.sound.unloadAsync().catch(() => {})
    void lo.sound.unloadAsync().catch(() => {})
  }
}

/** Play a count-in and resolve when the transport may start (or when cancelled). */
export async function playCountIn(opts: CountInOptions): Promise<CountInResult> {
  const beats = Math.max(0, Math.round(opts.beats))
  if (beats === 0) return 'completed'
  const periodMs = countInBeatPeriodMs(opts.bpm)
  return Platform.OS === 'web'
    ? playWebCountIn({ ...opts, beats }, periodMs)
    : playNativeCountIn({ ...opts, beats }, periodMs)
}
