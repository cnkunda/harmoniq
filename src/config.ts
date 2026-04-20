import Constants from 'expo-constants'

type HarmoniqExtra = {
  apiBaseUrl?: string
}

function readExtra(): HarmoniqExtra {
  return (Constants.expoConfig?.extra ?? {}) as HarmoniqExtra
}

/** Backend origin for FastAPI (commit 0.2+). Set `EXPO_PUBLIC_API_URL` in `.env` or app.config `extra`. */
export const API_BASE_URL: string = (() => {
  const fromExtra = readExtra().apiBaseUrl
  if (typeof fromExtra === 'string' && fromExtra.length > 0) {
    return fromExtra.replace(/\/$/, '')
  }
  return 'http://localhost:8000'
})()

/** Commit 63: skip technique EMA persistence (tests / CI fast path). */
export function isHarmoniqSkillMutationSkipped(): boolean {
  if (typeof process === 'undefined' || !process.env) return false
  return (
    process.env.EXPO_PUBLIC_HARMONIQ_SKIP_SKILL_MUTATION === '1' || process.env.HARMONIQ_SKIP_SKILL_MUTATION === '1'
  )
}
