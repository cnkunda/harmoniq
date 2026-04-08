import { Platform } from 'react-native'

import { createNativeBeatMetronome } from './beatMetronome.native'
import { createWebBeatMetronome } from './beatMetronome.web'
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
