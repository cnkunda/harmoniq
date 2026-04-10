import { useRouter } from 'expo-router'
import { Pressable, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { useOnboardingPlacementStore } from '@/src/stores/onboardingPlacementStore'

export default function OnboardingWelcomeScreen() {
  const router = useRouter()
  const resetPlacement = useOnboardingPlacementStore((s) => s.reset)

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <View className="flex-1 justify-center px-6 py-8">
        <Text className="font-serif text-3xl text-cream">First time here</Text>
        <Text className="mt-4 font-sans text-base leading-7 text-muted-brown">
          {
            "Let's find out what you sound like. Three short phrases, your mic, and a quick baseline for your skill map — about five minutes, like tuning up before a gig."
          }
        </Text>
        <Text className="mt-4 font-sans text-sm leading-6 text-muted-brown">
          We need microphone access to score your takes. You can turn it off later in system settings.
        </Text>
        <Pressable
          onPress={() => {
            resetPlacement()
            router.push('/onboarding/mic')
          }}
          className="mt-10 rounded-lg bg-amber-accent px-4 py-3"
          accessibilityRole="button"
          accessibilityLabel="Continue to microphone permission"
        >
          <Text className="text-center font-sans-medium text-wood-900">Continue</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  )
}
