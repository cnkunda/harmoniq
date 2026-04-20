import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import type { RecordedTake } from '@/src/audio/recordSession.types'

type PlayCaptureControlsProps = {
  /** Tighter layout when nested in the lesson playback card. */
  embedded?: boolean
  recording: boolean
  status: string
  take: RecordedTake | null
  autostopTriggered: boolean
  onToggleCapture: () => void
}

/**
 * Primary capture CTA, status line, optional take summary (Play session).
 */
export function PlayCaptureControls({
  embedded = false,
  recording,
  status,
  take,
  autostopTriggered,
  onToggleCapture,
}: PlayCaptureControlsProps) {
  return (
    <View className={embedded ? 'gap-2' : 'gap-3'}>
      {/* {Platform.OS === 'web' ? (
        <View className="rounded-xl border border-wood-600/40 bg-cream-dark/50 px-3 py-2.5">
          <Text className="font-sans text-xs text-wood-900">
            Web: allow the microphone and use headphones to cut bleed. Mic capture needs HTTPS or localhost.
          </Text>
        </View>
      ) : null} */}

      <View className="flex-row flex-wrap items-center gap-2">
        <AnimatedPressable
          onPress={onToggleCapture}
          className={`rounded-xl bg-amber-accent ${embedded ? 'px-3 py-2' : 'px-4 py-2.5'}`}
          accessibilityRole="button"
        >
          <Text className={`font-sans-medium text-wood-900 ${embedded ? 'text-sm' : ''}`}>
            {recording ? 'Finish capture' : embedded ? 'Start capture' : 'Start play capture'}
          </Text>
        </AnimatedPressable>
        <Text className={`flex-1 text-muted-brown ${embedded ? 'font-mono text-[10px]' : 'font-mono text-[11px]'}`}>
          {status}
        </Text>
      </View>

      {autostopTriggered ? (
        <Text className="font-sans text-xs text-muted-brown">Auto-end triggered after 5 seconds of silence.</Text>
      ) : null}
      {take ? (
        <Text className="font-sans text-xs text-wood-900">
          Recorded take: {(take.durationMs / 1000).toFixed(1)}s, {take.audioBytes.length} bytes ({take.mimeType})
        </Text>
      ) : null}
    </View>
  )
}
