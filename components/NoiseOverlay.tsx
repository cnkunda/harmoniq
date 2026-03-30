import { Platform } from 'react-native'

import { NoiseOverlay as NativeNoiseOverlay } from './NoiseOverlay.native'
import { NoiseOverlay as WebNoiseOverlay } from './NoiseOverlay.web'

/**
 * Wrapper to ensure web uses `NoiseOverlay.web.tsx`.
 *
 * Without this, some bundler/TS setups end up re-exporting the native version,
 * which triggers react-native-web deprecation warnings (e.g. `pointerEvents` prop).
 */
export const NoiseOverlay = Platform.OS === 'web' ? WebNoiseOverlay : NativeNoiseOverlay
