import { useEffect } from 'react'
import { View } from 'react-native'
import Animated, { useAnimatedStyle, useSharedValue, withSequence, withTiming } from 'react-native-reanimated'

import colors from '@/src/constants/colors'

export type BeatFlashPulseProps = {
  /** Increment on each metronome pulse (downbeat uses stronger ring). */
  flashTick: number
  lastDownbeat?: boolean
}

/**
 * Reanimated beat flash next to transport (PRIORITIES §50).
 */
export function BeatFlashPulse({ flashTick, lastDownbeat }: BeatFlashPulseProps) {
  const ring = useSharedValue(0)

  useEffect(() => {
    if (flashTick <= 0) return
    ring.value = 0
    const peak = lastDownbeat ? 1 : 0.55
    ring.value = withSequence(withTiming(peak, { duration: 45 }), withTiming(0, { duration: 220 }))
  }, [flashTick, lastDownbeat, ring])

  const style = useAnimatedStyle(() => ({
    opacity: 0.35 + ring.value * 0.5,
    transform: [{ scale: 1 + ring.value * 0.35 }],
  }))

  return (
    <View className="items-center justify-center" style={{ width: 28, height: 28 }}>
      <Animated.View
        style={[
          style,
          {
            width: 22,
            height: 22,
            borderRadius: 11,
            borderWidth: 2,
            borderColor: colors.amber.accent,
            backgroundColor: `${colors.amber.accent}18`,
          },
        ]}
      />
    </View>
  )
}
