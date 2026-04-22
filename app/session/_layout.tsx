import { Stack, usePathname } from 'expo-router'
import { useEffect } from 'react'
import { View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { PhaseIndicator } from '@/components/PhaseIndicator'
import { SessionChromeBar } from '@/components/SessionChromeBar'
import { sessionStepIndexFromPathname, type SessionStep } from '@/src/constants/sessionFlow'
import { usePlanStore } from '@/src/stores/planStore'
import { useSessionPhaseStore } from '@/src/stores/sessionPhaseStore'

export default function SessionLayout() {
  const pathname = usePathname()
  const syncPhaseFromStep = useSessionPhaseStore((s) => s.syncPhaseFromStep)
  const currentPlan = usePlanStore((s) => s.currentPlan)

  // Sync phase store with current route
  useEffect(() => {
    const stepIndex = sessionStepIndexFromPathname(pathname)
    const steps: SessionStep[] = ['tune', 'listen', 'study', 'slow', 'play', 'review']
    const currentStep = steps[stepIndex] as SessionStep
    
    if (currentStep) {
      syncPhaseFromStep(currentStep)
    }
  }, [pathname, syncPhaseFromStep])

  return (
    <SafeAreaView className="flex-1 bg-ivory" edges={['top', 'left', 'right']}>
      <SessionChromeBar />
      <View className="flex-1">
        {!currentPlan && (
          <View className="px-4 py-2">
            <PhaseIndicator />
          </View>
        )}
        <Stack screenOptions={{ headerShown: false, animation: 'slide_from_right' }} />
      </View>
    </SafeAreaView>
  )
}
