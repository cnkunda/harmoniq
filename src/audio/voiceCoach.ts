/**
 * Cross-platform TTS for coach copy (commit 72).
 * Native uses dynamic import so `expo-speech` is not bundled for web.
 */
import { Platform } from 'react-native'

import * as WebImpl from '@/src/audio/voiceCoach.web'
import type { SessionPhase } from '@/src/constants/sessionPhases'
import { PHASE_TRANSITION_COPY } from '@/src/constants/sessionPhases'

type NativeMod = typeof import('./voiceCoach.native')

let nativeCache: NativeMod | null = null

function loadNativeSync(): NativeMod | null {
  if (nativeCache) return nativeCache
  if (Platform.OS === 'web') return null
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  nativeCache = require('./voiceCoach.native') as NativeMod
  return nativeCache
}

export function speak(text: string, rate?: number): void {
  if (Platform.OS === 'web') {
    WebImpl.speak(text, rate)
    return
  }
  const n = loadNativeSync()
  if (n) n.speak(text, rate)
}

export function stop(): void {
  if (Platform.OS === 'web') {
    WebImpl.stop()
    return
  }
  const n = loadNativeSync()
  if (n) n.stop()
}

export function isSpeaking(): boolean {
  if (Platform.OS === 'web') return WebImpl.isSpeaking()
  const n = loadNativeSync()
  return n ? n.isSpeaking() : false
}

/**
 * Commit 83: Narrate phase transitions using the voice coach.
 * Speaks the enter copy for the given phase.
 */
export function speakPhaseTransition(phase: SessionPhase): void {
  const copy = PHASE_TRANSITION_COPY[phase]
  if (copy) {
    speak(copy.enter)
  }
}
