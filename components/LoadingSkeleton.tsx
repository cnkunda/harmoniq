import { useEffect } from 'react'
import type { ViewStyle } from 'react-native'
import Animated, { useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated'

import colors from '@/src/constants/colors'
import { timing } from '@/src/constants/animations'

export interface LoadingSkeletonProps {
  width?: number | `${number}%`
  height?: number
  borderRadius?: number
  style?: ViewStyle
}

export function LoadingSkeleton({
  width = '100%',
  height = 16,
  borderRadius = 8,
  style,
}: LoadingSkeletonProps) {
  const opacity = useSharedValue(0.3)

  useEffect(() => {
    opacity.value = withRepeat(withTiming(0.75, { duration: timing.slow * 2 }), -1, true)
  }, [opacity])

  const animStyle = useAnimatedStyle(() => ({ opacity: opacity.value }))

  return (
    <Animated.View
      style={[{ width, height, borderRadius, backgroundColor: colors.wood[600] }, animStyle, style]}
    />
  )
}
