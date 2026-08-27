import { useRouter } from 'expo-router'
import { Music } from 'lucide-react-native'
import { useState } from 'react'
import { Text, View } from 'react-native'

import { PrimaryButton } from '@/components/Button'
import { OnboardingScreenShell } from '@/components/onboarding/OnboardingScreenShell'
import colors from '@/src/constants/colors'
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
        <Text className="mt-4 text-center font-sans text-base leading-7 text-cream/85">
          Let&apos;s find out what you sound like. Three short phrases, your mic, and a quick baseline for your skill map
          — about five minutes, like tuning up before a gig.
        </Text>
        <Text className="mt-3 max-w-sm self-center text-center font-sans text-sm leading-6 text-cream/70">
          After this, Home lines up the same choices: try the demo, add a song, take the optional style quiz, or connect
          Spotify.
        </Text>
        <PrimaryButton
          label={routing ? 'Continue…' : 'Continue → Mic setup'}
          onPress={onContinue}
          loading={routing}
          disabled={routing}
          size="lg"
          fullWidth
          className="mt-10"
          accessibilityLabel="Continue to microphone permission"
        />
      </View>
    </OnboardingScreenShell>
  )
}
