import { useEffect } from 'react'
import { Text, View } from 'react-native'
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withTiming,
} from 'react-native-reanimated'

import colors from '@/src/constants/colors'
import type { AccuracyLabel } from '@/src/session/noteAccuracyBeats'

export interface PitchIndicatorProps {
  note?: string
  cents?: number
  isActive?: boolean
  targetMidi?: number
  /** Latest closed beat result — drives transient ladder flash. */
  windowResult?: AccuracyLabel | null
  /** Increment to retrigger flash even when result repeats. */
  windowFlashToken?: number
}

function midiToHz(midi: number): number {
  return 440 * Math.pow(2, (midi - 69) / 12)
}

const FLASH_BG: Record<AccuracyLabel, string> = {
  hit: colors.success,
  close: colors.amber.accent,
  miss: colors.danger,
}

export function PitchIndicator({
  note,
  cents,
  isActive,
  targetMidi,
  windowResult,
  windowFlashToken = 0,
}: PitchIndicatorProps) {
  const hz = typeof targetMidi === 'number' && Number.isFinite(targetMidi) ? midiToHz(targetMidi) : null
  const flashOpacity = useSharedValue(0)

  useEffect(() => {
    if (!windowResult || windowFlashToken <= 0) return
    flashOpacity.value = 0
    flashOpacity.value = withSequence(
      withTiming(0.55, { duration: 70 }),
      withTiming(0, { duration: 420 }),
    )
  }, [windowFlashToken, windowResult, flashOpacity])

  const flashStyle = useAnimatedStyle(() => ({
    opacity: flashOpacity.value,
  }))

  const flashColor = windowResult ? FLASH_BG[windowResult] : colors.wood[600]

  return (
    <View className="relative overflow-hidden rounded-lg border border-dashed border-wood-600 p-4">
      {windowResult ? (
        <Animated.View
          pointerEvents="none"
          style={[
            {
              position: 'absolute',
              left: 0,
              right: 0,
              top: 0,
              bottom: 0,
              borderRadius: 8,
              backgroundColor: flashColor,
            },
            flashStyle,
          ]}
        />
      ) : null}
      <Text className="font-mono text-amber-accent">Pitch ladder</Text>
      <Text className="mt-1 font-sans text-xs text-muted-brown">
        target: {hz != null ? `${hz.toFixed(1)} Hz` : '—'} {note ? `| note: ${note}` : ''}{' '}
        {typeof cents === 'number' ? `| cents: ${Math.round(cents)}` : ''} {isActive ? '| active' : ''}
      </Text>
      <View className="relative mt-2 h-1.5 w-full rounded-full bg-wood-600/40">
        <View className="h-1.5 w-1/2 rounded-full bg-amber-accent/80" />
      </View>
    </View>
  )
}
