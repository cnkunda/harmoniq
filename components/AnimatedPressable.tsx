import * as Haptics from 'expo-haptics'
import { Pressable, type PressableProps, type StyleProp, type ViewStyle } from 'react-native'
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated'

import { spring } from '@/src/constants/animations'

type HapticStrength = 'light' | 'medium' | 'heavy' | 'none'

export interface AnimatedPressableProps extends Omit<PressableProps, 'style'> {
  haptic?: HapticStrength
  className?: string
  style?: StyleProp<ViewStyle>
}

const HAPTIC_STYLE: Record<Exclude<HapticStrength, 'none'>, Haptics.ImpactFeedbackStyle> = {
  light: Haptics.ImpactFeedbackStyle.Light,
  medium: Haptics.ImpactFeedbackStyle.Medium,
  heavy: Haptics.ImpactFeedbackStyle.Heavy,
}

export function AnimatedPressable({
  onPress,
  onPressIn,
  onPressOut,
  haptic = 'light',
  style,
  className,
  children,
  disabled,
  ...props
}: AnimatedPressableProps) {
  const scale = useSharedValue(1)

  const animStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }))

  const handlePressIn: NonNullable<PressableProps['onPressIn']> = (e) => {
    onPressIn?.(e)
    if (disabled) return
    scale.value = withSpring(0.97, spring.snappy)
  }

  const handlePressOut: NonNullable<PressableProps['onPressOut']> = (e) => {
    onPressOut?.(e)
    scale.value = withSpring(1, { damping: 15, stiffness: 300 })
  }

  const handlePress: PressableProps['onPress'] = (e) => {
    if (!disabled && haptic !== 'none') {
      void Haptics.impactAsync(HAPTIC_STYLE[haptic])
    }
    onPress?.(e)
  }

  return (
    <Animated.View style={[animStyle, style]}>
      <Pressable
        {...props}
        className={className}
        disabled={disabled}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        onPress={handlePress}
      >
        {children}
      </Pressable>
    </Animated.View>
  )
}
