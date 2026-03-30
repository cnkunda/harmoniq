/**
 * Metro resolves `@/components/NoiseOverlay` to:
 * - `NoiseOverlay.web.tsx` on web
 * - `NoiseOverlay.native.tsx` on iOS / Android
 *
 * This file exists so TypeScript resolves the module when running `tsc`
 * (no platform suffixes in tsconfig). It is not bundled when `.web` / `.native` exist.
 */
export { NoiseOverlay } from './NoiseOverlay.native'
