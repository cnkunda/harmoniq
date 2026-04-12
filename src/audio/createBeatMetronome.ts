import { Platform } from 'react-native'

import { createNativeBeatMetronome } from './metronome.native'
import { createWebBeatMetronome } from './metronome.web'
import type { BeatMetronome } from './beatMetronome.types'

const noopMetronome: BeatMetronome = {
  start: () => {},
  stop: () => {},
}

export function createBeatMetronome(audioContext: AudioContext | null): BeatMetronome {
  if (Platform.OS === 'web') {
    if (!audioContext) {
      return noopMetronome
    }
    return createWebBeatMetronome(audioContext)
  }
  return createNativeBeatMetronome()
}
