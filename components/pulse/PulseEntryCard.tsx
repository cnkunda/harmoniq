import { ChevronRight, Activity } from 'lucide-react-native'
import { useEffect } from 'react'
import { Text, View } from 'react-native'
import Animated, {
  Easing,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { colors } from '@/src/constants/colors'

export interface PulseEntryCardProps {
  onPress: () => void
  variant?: 'home' | 'progress'
}

export function PulseEntryCard({ onPress, variant = 'home' }: PulseEntryCardProps) {
  const reducedMotion = useReducedMotion()
  const pulse = useSharedValue(0)

  useEffect(() => {
    if (reducedMotion) {
      pulse.value = 0
      return
    }
    pulse.value = withRepeat(
      withTiming(1, { duration: 2200, easing: Easing.out(Easing.quad) }),
      -1,
      false,
    )
  }, [pulse, reducedMotion])

  const rippleStyle = useAnimatedStyle(() => ({
    opacity: 0.35 * (1 - pulse.value),
    transform: [{ scale: 1 + pulse.value * 0.9 }],
  }))

  return (
    <AnimatedPressable
      onPress={onPress}
      haptic="light"
      accessibilityRole="button"
      accessibilityLabel="Open Chord Pulse"
      className="mb-6 overflow-hidden rounded-2xl border border-amber-accent/35 bg-wood-800/55 px-5 py-4 active:bg-wood-700/60"
    >
      <View
        pointerEvents="none"
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: 0,
          width: 3,
          backgroundColor: colors.amber.accent,
        }}
      />

      <View className="flex-row items-center gap-4">
        <View className="h-12 w-12 items-center justify-center rounded-full border border-amber-accent/30 bg-amber-accent/10">
          <Animated.View
            pointerEvents="none"
            style={[
              {
                position: 'absolute',
                width: 42,
                height: 42,
                borderRadius: 21,
                borderWidth: 1,
                borderColor: colors.amber.light,
              },
              rippleStyle,
            ]}
          />
          <Activity color={colors.amber.light} size={22} strokeWidth={2} />
        </View>

        <View className="flex-1 pr-1">
          <Text className="font-sans-medium text-[10px] uppercase tracking-[1.4px] text-amber-light">
            Chord Pulse
          </Text>
          <Text className="mt-0.5 font-serif text-lg text-cream">
            {variant === 'progress' ? 'Watch your chords breathe' : 'See your harmony in motion'}
          </Text>
          <Text className="mt-0.5 font-sans text-xs leading-5 text-muted-light">
            Beat-synced timeline, confidence ring, accuracy trend, and a mastery heatmap.
          </Text>
        </View>

        <ChevronRight color={colors.amber.accent} size={20} strokeWidth={2} />
      </View>
    </AnimatedPressable>
  )
}
