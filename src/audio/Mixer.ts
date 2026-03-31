/**
 * Metro bundles `Mixer.native.ts` (iOS/Android) or `Mixer.web.ts` (web) instead of this file.
 * This entry exists so `tsc` resolves `import … from '@/src/audio/Mixer'`.
 */
export type { StemAssetModule, StemDefinition, StemMixer } from './mixerTypes'
export { createStemMixer } from './Mixer.native'
