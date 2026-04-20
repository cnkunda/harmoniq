import {
  mapUserRateToWebSpeech,
  prepareSpeechText,
  shouldSkipTts,
} from '@/src/audio/voiceCoachShared'
import { useVoiceCoachPrefsStore } from '@/src/stores/voiceCoachPrefsStore'

let speaking = false
let currentUtterance: SpeechSynthesisUtterance | null = null

function pickVoice(gender: 'default' | 'female' | 'male'): SpeechSynthesisVoice | null {
  if (typeof window === 'undefined' || !window.speechSynthesis) return null
  const voices = window.speechSynthesis.getVoices()
  if (!voices.length) return null
  const en = voices.filter((v) => /en(-|$)/i.test(v.lang))
  const pool = en.length ? en : voices
  if (gender === 'default') {
    const preferred = pool.find((v) => /samantha|karen|victoria|zira|aria|susan/i.test(v.name))
    return preferred ?? pool[0] ?? null
  }
  const female = pool.find((v) => /female|woman|zira|samantha|karen|victoria|emma|joanna/i.test(`${v.name} ${v.voiceURI}`))
  const male = pool.find((v) => /male|man|david|daniel|fred|mark|thomas|arthur/i.test(`${v.name} ${v.voiceURI}`))
  return gender === 'female' ? female ?? pool[0] ?? null : male ?? pool[0] ?? null
}

export function speak(text: string, rate?: number): void {
  if (shouldSkipTts()) return
  if (typeof window === 'undefined' || !window.speechSynthesis) return
  if (!useVoiceCoachPrefsStore.getState().enabled) return
  const cleaned = prepareSpeechText(text)
  if (!cleaned) return

  window.speechSynthesis.cancel()
  currentUtterance = new SpeechSynthesisUtterance(cleaned)
  currentUtterance.lang = 'en-US'
  const u = rate ?? useVoiceCoachPrefsStore.getState().rate
  currentUtterance.rate = mapUserRateToWebSpeech(u)
  currentUtterance.pitch = 1
  const voice = pickVoice(useVoiceCoachPrefsStore.getState().gender)
  if (voice) currentUtterance.voice = voice
  speaking = true
  currentUtterance.onend = () => {
    speaking = false
    currentUtterance = null
  }
  currentUtterance.onerror = () => {
    speaking = false
    currentUtterance = null
  }
  window.speechSynthesis.speak(currentUtterance)
}

export function stop(): void {
  speaking = false
  currentUtterance = null
  if (typeof window !== 'undefined' && window.speechSynthesis) {
    window.speechSynthesis.cancel()
  }
}

export function isSpeaking(): boolean {
  return speaking
}
