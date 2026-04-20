/** Shared TTS helpers (commit 72). */

const MAX_CHARS = 150

export function shouldSkipTts(): boolean {
  try {
    if (typeof process !== 'undefined' && process.env?.EXPO_PUBLIC_HARMONIQ_SKIP_TTS === '1') return true
    if (typeof process !== 'undefined' && process.env?.HARMONIQ_SKIP_TTS === '1') return true
  } catch {
    /* ignore */
  }
  return false
}

/** Truncate at sentence end when possible; keeps cadence natural under ~150 chars. */
export function prepareSpeechText(raw: string): string {
  const t = raw.replace(/\s+/g, ' ').trim()
  if (!t) return ''
  if (t.length <= MAX_CHARS) return t
  const slice = t.slice(0, MAX_CHARS)
  const lastSentence = Math.max(slice.lastIndexOf('.'), slice.lastIndexOf('!'), slice.lastIndexOf('?'))
  if (lastSentence > 40) return slice.slice(0, lastSentence + 1).trim()
  return `${slice.replace(/\s+\S*$/, '').trim()}…`
}

/** Map Settings slider 0.7–1.2 → expo-speech `rate` (1 = normal per SDK). */
export function mapUserRateToExpoSpeech(userRate: number): number {
  const u = Math.max(0.7, Math.min(1.2, userRate))
  return Math.max(0.45, Math.min(1.15, 0.72 + ((u - 0.7) / 0.5) * 0.38))
}

/** Map 0.7–1.2 → Web Speech API utterance.rate (typical comfortable band). */
export function mapUserRateToWebSpeech(userRate: number): number {
  const u = Math.max(0.7, Math.min(1.2, userRate))
  return Math.max(0.75, Math.min(1.35, 0.88 + ((u - 0.7) / 0.5) * 0.32))
}
