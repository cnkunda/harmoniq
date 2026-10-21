/**
 * Background-hook contract. Metro resolves `.web.ts` / `.native.ts` at bundle time;
 * this stub keeps Vitest and type-only consumers free of React Native imports.
 */
export function subscribeAnalyticsBackground(_onBackground: () => void): () => void {
  return () => {}
}
