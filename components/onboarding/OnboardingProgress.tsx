import { View } from 'react-native'

export type OnboardingProgressProps = {
  totalSteps: number
  /** 1-based index of the active step */
  currentStep: number
}

import { Text } from 'react-native'

export function OnboardingProgress({ totalSteps, currentStep }: OnboardingProgressProps) {
  const safeTotal = Math.max(1, totalSteps)
  const active = Math.min(Math.max(1, currentStep), safeTotal)

  return (
    <View
      accessibilityRole="progressbar"
      accessibilityLabel={`Onboarding step ${active} of ${safeTotal}`}
      className="w-full gap-1.5"
    >
      <View className="flex-row gap-2">
        {Array.from({ length: safeTotal }, (_, i) => {
          const isActive = i === active - 1
          const isPast = i < active - 1
          return (
            <View
              key={i}
              className={`h-2 flex-1 rounded-full ${
                isActive ? 'bg-amber-accent shadow-sm' : isPast ? 'bg-amber-accent/55' : 'bg-wood-600'
              }`}
              style={isActive ? { shadowColor: '#D4A574', shadowOpacity: 0.4 } : undefined}
            />
          )
        })}
      </View>
      <Text className="text-right font-sans text-[11px] tracking-wide text-cream/70">
        {active} / {safeTotal}
      </Text>
    </View>
  )
}
