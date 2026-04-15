import { View } from 'react-native'

export type OnboardingProgressProps = {
  totalSteps: number
  /** 1-based index of the active step */
  currentStep: number
}

export function OnboardingProgress({ totalSteps, currentStep }: OnboardingProgressProps) {
  const safeTotal = Math.max(1, totalSteps)
  const active = Math.min(Math.max(1, currentStep), safeTotal)

  return (
    <View
      accessibilityRole="progressbar"
      accessibilityLabel={`Onboarding step ${active} of ${safeTotal}`}
      className="w-full flex-row gap-1"
    >
      {Array.from({ length: safeTotal }, (_, i) => (
        <View
          key={i}
          className={`h-1 flex-1 rounded-full ${i === active - 1 ? 'bg-amber-accent' : 'bg-wood-600/70'}`}
        />
      ))}
    </View>
  )
}
