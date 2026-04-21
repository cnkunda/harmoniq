import { Audio } from 'expo-av'
import { Platform } from 'react-native'
import { useEffect, useRef } from 'react'

import { GHOST_MIX_LINEAR } from '@/src/audio/ghostConstants'

/**
 * Native: parallel ghost clip synced to stem mixer transport.
 * Web: no-op — ghost is mixed as a padded stem inside `StemMixer.web`.
 */
export function useGhostStemSidecar(opts: {
  ghostFileUri: string | null
  anchorSec: number
  ghostAudible: boolean
  mixerPlaying: boolean
  getMixerPositionSec: () => number
  masterDurationSec: number
  playbackRate: number
  mixerReady: boolean
}): void {
  const soundRef = useRef<Audio.Sound | null>(null)

  useEffect(() => {
    if (Platform.OS === 'web') return

    let cancelled = false

    const uri = opts.ghostFileUri
    if (!uri || !opts.mixerReady) {
      void soundRef.current?.unloadAsync().catch(() => {})
      soundRef.current = null
      return
    }

    const boot = async () => {
      try {
        await Audio.setAudioModeAsync({ playsInSilentModeIOS: true, allowsRecordingIOS: false })
        const { sound } = await Audio.Sound.createAsync(
          { uri },
          { shouldPlay: false, isLooping: false, volume: GHOST_MIX_LINEAR },
        )
        if (cancelled) {
          await sound.unloadAsync().catch(() => {})
          return
        }
        soundRef.current = sound
      } catch (e) {
        console.warn('[ghost] native sidecar load failed', e)
      }
    }

    void boot()

    return () => {
      cancelled = true
      void soundRef.current?.unloadAsync().catch(() => {})
      soundRef.current = null
    }
  }, [opts.ghostFileUri, opts.mixerReady])

  useEffect(() => {
    if (Platform.OS === 'web') return

    const uri = opts.ghostFileUri
    if (!uri || !opts.mixerReady) return

    const tick = async () => {
      const s = soundRef.current
      if (!s) return
      try {
        const st = await s.getStatusAsync()
        if (!st.isLoaded) return
        const durMs = st.durationMillis ?? 0
        const d = opts.masterDurationSec > 0 ? opts.masterDurationSec : durMs / 1000
        const songPos = ((opts.getMixerPositionSec() % d) + d) % d
        const rel = songPos - opts.anchorSec
        if (!opts.ghostAudible || !opts.mixerPlaying || rel < 0 || rel * 1000 >= durMs) {
          await s.setVolumeAsync(0)
          await s.pauseAsync().catch(() => {})
          return
        }
        await s.setVolumeAsync(GHOST_MIX_LINEAR)
        await s.setRateAsync(opts.playbackRate, true, Audio.PitchCorrectionQuality.Medium)
        const posMs = Math.min(rel * 1000, Math.max(0, durMs - 1))
        await s.setPositionAsync(posMs)
        await s.playAsync()
      } catch (e) {
        console.warn('[ghost] native sidecar tick failed', e)
      }
    }

    const id = setInterval(() => {
      void tick()
    }, 90)
    return () => clearInterval(id)
  }, [
    opts.anchorSec,
    opts.ghostAudible,
    opts.getMixerPositionSec,
    opts.masterDurationSec,
    opts.mixerPlaying,
    opts.playbackRate,
    opts.ghostFileUri,
    opts.mixerReady,
  ])
}
