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
