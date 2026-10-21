import { AppState } from 'react-native'

/** Flush analytics when the app leaves the foreground. */
export function subscribeAnalyticsBackground(onBackground: () => void): () => void {
  const subscription = AppState.addEventListener('change', (state) => {
    if (state !== 'active') onBackground()
  })
  return () => subscription.remove()
}
