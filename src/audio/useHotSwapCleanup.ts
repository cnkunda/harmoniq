import { useEffect } from 'react'

import { globalAudioManager } from './GlobalAudioManager'

/**
 * Hook to handle hot-swap audio cleanup when navigating between different audio contexts.
 * Call this in session screens to ensure audio buffers are cleared when deep-linking
 * (e.g., Single File → Full Practice).
 *
 * This hook cleans up audio instances on component unmount, which happens when navigating away.
 *
 * @param options.skipTypes - Audio instance types to skip during cleanup (e.g., keep metronome running)
 */
export function useHotSwapCleanup(options?: { skipTypes?: Array<'expo-sound' | 'expo-recording' | 'audio-api-recorder' | 'audio-api-manager'> }): void {
  useEffect(() => {
    return () => {
      console.info('[useHotSwapCleanup] component unmounting, cleaning up audio instances')
      void globalAudioManager.cleanupAll(options)
    }
  }, [options])
}
