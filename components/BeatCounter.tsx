import { useEffect } from 'react'
import { Text, View } from 'react-native'
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated'

import colors from '@/src/constants/colors'

interface BeatCounterProps {
  bpm: number
  isPlaying?: boolean
  resetKey?: number
}

export function BeatCounter({ bpm, isPlaying = false, resetKey = 0 }: BeatCounterProps) {
  const pulse = useSharedValue(1)

  useEffect(() => {
    pulse.value = 1
    if (isPlaying) {
      const intervalMs = (60000 / bpm) / 2
      const durationMs = Math.max(100, intervalMs)
      pulse.value = withRepeat(
        withTiming(0.3, { duration: durationMs }),
        -1,
        true,
      )
    } else {
      pulse.value = withTiming(0, { duration: 200 })
    }
  }, [isPlaying, bpm, resetKey, pulse])

  const dotStyle = useAnimatedStyle(() => ({
    opacity: pulse.value,
  }))

  return (
    <View className="flex-row items-center gap-1.5" accessibilityLabel={`Beat counter: ${bpm} BPM`} accessible>
      <Animated.View
        style={[
          dotStyle,
          {
            width: 6,
            height: 6,
            borderRadius: 3,
            backgroundColor: colors.amber.accent,
          },
        ]}
      />
      <Text className="font-mono text-[11px] text-muted-brown tabular-nums">
        ♩ {bpm}
      </Text>
    </View>
  )
}
