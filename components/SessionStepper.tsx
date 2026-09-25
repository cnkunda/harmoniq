import { Text, View } from 'react-native'
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated'
import { useEffect } from 'react'

import { SESSION_STEPS, type SessionStep } from '@/src/constants/sessionFlow'
import { spring } from '@/src/constants/animations'

export interface SessionStepperProps {
  currentStep: number
  steps?: readonly SessionStep[]
  compact?: boolean
}

function stepLabel(s: SessionStep): string {
  switch (s) {
    case 'tune': return 'Tune'
    case 'musical-tolerance': return 'Tolerance'
    default: return s.charAt(0).toUpperCase() + s.slice(1)
  }
}

export function SessionStepper({
  currentStep,
  steps = SESSION_STEPS,
  compact = false,
}: SessionStepperProps) {
  const totalSteps = steps.length
  const trackPercent = totalSteps > 1 ? ((currentStep - 1) / (totalSteps - 1)) * 100 : 0
  const trackWidth = useSharedValue(0)

  useEffect(() => {
    trackWidth.value = withSpring(trackPercent, spring.gentle)
  }, [trackPercent, trackWidth])

  const animatedTrackStyle = useAnimatedStyle(() => ({
    width: `${Math.max(0, Math.min(100, trackWidth.value))}%`,
  }))

  return (
    <View className="w-full px-2">
      <View className="relative flex-row items-center justify-between">
        <View className="absolute left-0 right-0 top-[11px] z-0 h-[2px] bg-wood-800" />

        <Animated.View
          style={animatedTrackStyle}
          className="absolute top-[11px] z-0 h-[2px] bg-amber-accent"
        />

        {steps.map((step, index) => {
          const stepNum = index + 1
          const isActive = stepNum === currentStep
          const isPast = stepNum < currentStep

          return (
            <View key={step} className="z-10 items-center">
              <View
                className={`h-6 w-6 items-center justify-center rounded-full ${
                  isActive
                    ? 'bg-amber-accent'
                    : isPast
                      ? 'border border-amber-accent/30 bg-wood-700'
                      : 'border border-wood-600 bg-wood-800'
                }`}
              >
                <Text
                  className={`text-[10px] ${
                    isActive
                      ? 'font-sans-medium text-wood-900'
                      : isPast
                        ? 'font-sans text-amber-light/50'
                        : 'font-sans text-muted-brown'
                  }`}
                >
                  {stepNum}
                </Text>
              </View>
              {compact ? null : (
                <Text
                  className={`mt-1 text-[9px] font-sans-medium uppercase tracking-wider ${
                    isActive
                      ? 'text-amber-accent'
                      : isPast
                        ? 'text-cream/60'
                        : 'text-muted-brown/50'
                  }`}
                >
                  {stepLabel(step)}
                </Text>
              )}
            </View>
          )
        })}
      </View>
    </View>
  )
}
