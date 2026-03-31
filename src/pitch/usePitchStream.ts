/**
 * Metro prefers `usePitchStream.native` / `usePitchStream.web` at bundle time.
 * This file exists so `tsc` can resolve `@/src/pitch/usePitchStream`.
 */
export { usePitchStream } from '@/src/pitch/usePitchStream.web'
