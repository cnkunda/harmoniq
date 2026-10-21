import { useRouter } from 'expo-router'
import { ChevronRight, Music } from 'lucide-react-native'
import { useState } from 'react'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { OnboardingScreenShell } from '@/components/onboarding/OnboardingScreenShell'
import { colors } from '@/src/constants/colors'
import { shouldOfferTasteQuizOnboarding } from '@/src/taste/tasteQuizGate'
import { useOnboardingPlacementStore } from '@/src/stores/onboardingPlacementStore'

export default function OnboardingWelcomeScreen() {
  const router = useRouter()
  const resetPlacement = useOnboardingPlacementStore((s) => s.reset)
  const [routing, setRouting] = useState(false)

  const onContinue = () => {
    if (routing) return
    setRouting(true)
    void (async () => {
      try {
        resetPlacement()
        const offer = await shouldOfferTasteQuizOnboarding()
        if (offer) {
          router.push('/onboarding/taste-quiz')
        } else {
          router.push('/onboarding/mic')
        }
      } catch {
        router.push('/onboarding/mic')
      } finally {
        setRouting(false)
      }
    })()
  }

  return (
    <OnboardingScreenShell currentStep={1}>
      <View className="items-center">
        <View className="h-16 w-16 items-center justify-center rounded-full border border-amber-accent/50">
          <Music color={colors.amber.accent} size={28} strokeWidth={1.5} />
        </View>
        <Text className="mt-6 text-center font-serif text-3xl text-cream">First time here</Text>
        <Text className="mt-4 text-center font-sans text-base leading-7 text-muted-brown">
          Let&apos;s find out what you sound like. Three short phrases, your mic, and a quick baseline for your skill map
          — about five minutes, like tuning up before a gig.
        </Text>
        <Text className="mt-3 max-w-sm self-center text-center font-sans text-sm leading-6 text-muted-brown">
          After this, Home lines up the same choices: try the demo, add a song, take the optional style quiz, or connect
          Spotify.
        </Text>
        <Text className="mt-4 max-w-sm self-center text-center font-sans text-xs leading-5 text-muted-light">
          We track practice patterns to improve your experience. Opt out anytime.
        </Text>
        <AnimatedPressable haptic="light"
          onPress={onContinue}
          disabled={routing}
          className="mt-10 w-full flex-row items-center justify-center gap-2 rounded-lg bg-amber-accent px-4 py-3.5 disabled:opacity-60"
          accessibilityRole="button"
          accessibilityLabel="Continue to microphone permission"
        >
          <Text className="text-center font-sans-medium text-wood-900">
            {routing ? 'Continue…' : 'Continue'}
          </Text>
          {routing ? null : <ChevronRight color={colors.wood[900]} size={20} strokeWidth={2} />}
        </AnimatedPressable>
      </View>
    </OnboardingScreenShell>
  )
}
