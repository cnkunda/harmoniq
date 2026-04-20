import * as Speech from 'expo-speech'

import {
  mapUserRateToExpoSpeech,
  prepareSpeechText,
  shouldSkipTts,
} from '@/src/audio/voiceCoachShared'
import { useVoiceCoachPrefsStore } from '@/src/stores/voiceCoachPrefsStore'

let speaking = false

export function speak(text: string, rate?: number): void {
  if (shouldSkipTts()) return
  if (!useVoiceCoachPrefsStore.getState().enabled) return
  const cleaned = prepareSpeechText(text)
  if (!cleaned) return

  void Speech.stop()
    .catch(() => {})
    .then(() => {
      const u = rate ?? useVoiceCoachPrefsStore.getState().rate
      const nativeRate = mapUserRateToExpoSpeech(u)
      speaking = true
      Speech.speak(cleaned, {
        language: 'en-US',
        rate: nativeRate,
        pitch: 1.0,
        onDone: () => {
          speaking = false
        },
        onStopped: () => {
          speaking = false
        },
        onError: () => {
          speaking = false
        },
      })
    })
}

export function stop(): void {
  speaking = false
  void Speech.stop().catch(() => {})
}

export function isSpeaking(): boolean {
  return speaking
}
