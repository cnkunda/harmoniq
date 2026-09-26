import { useEffect } from 'react'
import { Text, View } from 'react-native'
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from 'react-native-reanimated'

import { colors } from '@/src/constants/colors'

export interface ConfidenceMeterProps {
  /** Confidence value 0–1. */
  confidence: number
}

const SPRING_CONFIG = { damping: 20, stiffness: 200 }

/**
 * Animated horizontal bar showing model confidence.
 * Fill color transitions: low → amber.accent, high → amber.light.
 */
export function ConfidenceMeter({ confidence }: ConfidenceMeterProps) {
  const clamped = Math.max(0, Math.min(1, confidence))
  const widthPct = useSharedValue(0)

  useEffect(() => {
    widthPct.value = withSpring(clamped, SPRING_CONFIG)
  }, [clamped, widthPct])

  const barStyle = useAnimatedStyle(() => ({
    width: `${widthPct.value * 100}%`,
  }))

  const barColor = clamped >= 0.7 ? colors.amber.light : colors.amber.accent

  return (
    <View className="mt-2">
      <View className="h-1.5 w-full overflow-hidden rounded-full bg-wood-600/40">
        <Animated.View
          style={[{ height: '100%', borderRadius: 999, backgroundColor: barColor }, barStyle]}
        />
      </View>
      <Text className="mt-1 text-center font-mono text-[10px] text-muted-brown">
        {Math.round(clamped * 100)}%
      </Text>
    </View>
  )
}
