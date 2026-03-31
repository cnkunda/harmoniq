import { useCallback, useRef } from 'react'

import type { PitchReading, PitchStream } from '@/src/pitch/pitchTypes'
import { createPitchStream } from '@/src/pitch/pitchStream.web'

export function usePitchStream() {
  const streamRef = useRef<PitchStream | null>(null)

  const start = useCallback(async (onPitch: (reading: PitchReading) => void) => {
    if (!streamRef.current) {
      streamRef.current = createPitchStream()
    }
    await streamRef.current.start(onPitch)
  }, [])

  const stop = useCallback(async () => {
    const s = streamRef.current
    if (!s) return
    await s.stop()
    streamRef.current = null
  }, [])

  const isRunning = useCallback(() => streamRef.current?.isRunning() ?? false, [])

  return { start, stop, isRunning }
}
