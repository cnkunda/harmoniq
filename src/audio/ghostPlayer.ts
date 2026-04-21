/**
 * Commit 75 — ghost take loading and mix constants.
 * Runtime wiring lives in `ListenStemPanel` (stems) and `useGhostStemSidecar` (native).
 */
export * from '@/src/audio/ghostConstants'
export { ghostReferenceToPlaybackUri, prepareGhostTakePayload } from '@/src/session/persistGhostTake'
