import { Redirect } from 'expo-router'

/**
 * `/listening` was a near-duplicate of `/(tabs)/discover` and has been retired.
 * Deep links still resolve here — they are routed to the canonical Discover tab.
 */
export default function ListeningRedirect() {
  return <Redirect href="/(tabs)/discover" />
}
