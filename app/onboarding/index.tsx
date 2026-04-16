import { useRouter } from 'expo-router'
import { Music } from 'lucide-react-native'
import { Pressable, Text, View } from 'react-native'

import { OnboardingScreenShell } from '@/components/onboarding/OnboardingScreenShell'
import colors from '@/src/constants/colors'
import { useOnboardingPlacementStore } from '@/src/stores/onboardingPlacementStore'

export default function OnboardingWelcomeScreen() {
  const router = useRouter()
  const resetPlacement = useOnboardingPlacementStore((s) => s.reset)

  return (
    <OnboardingScreenShell currentStep={1}>
      <View className="items-center">
        <View className="h-16 w-16 items-center justify-center rounded-full border border-amber-accent/50">
          <Music color={colors.amber.accent} size={28} strokeWidth={1.5} />
        </View>
        <Text className="mt-6 text-center font-serif text-3xl text-cream">First time here</Text>
        <Text className="mt-4 text-center font-sans text-base leading-7 text-muted-brown">
          {
            "Let's find out what you sound like. Three short phrases, your mic, and a quick baseline for your skill map — about five minutes, like tuning up before a gig."
          }
        </Text>
        <Pressable
          onPress={() => {
            resetPlacement()
            router.push('/onboarding/mic')
          }}
          className="mt-10 w-full rounded-lg bg-amber-accent px-4 py-3"
          accessibilityRole="button"
          accessibilityLabel="Continue to microphone permission"
        >
          <Text className="text-center font-sans-medium text-wood-900">Continue</Text>
        </Pressable>
      </View>
    </OnboardingScreenShell>
  )
}
