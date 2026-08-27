import { Stack, usePathname } from 'expo-router'
import { useEffect } from 'react'
import { View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { SessionChromeBar } from '@/components/SessionChromeBar'
import { SessionDesktopRail } from '@/components/SessionDesktopRail'
import { sessionStepIndexFromPathname, type SessionStep } from '@/src/constants/sessionFlow'
import { useSessionPhaseStore } from '@/src/stores/sessionPhaseStore'

export default function SessionLayout() {
  const pathname = usePathname()
  const syncPhaseFromStep = useSessionPhaseStore((s) => s.syncPhaseFromStep)

  // Sync phase store with current route
  useEffect(() => {
    const stepIndex = sessionStepIndexFromPathname(pathname)
    if (stepIndex < 0) return
    const steps: SessionStep[] = ['tune', 'musical-tolerance', 'listen', 'study', 'slow', 'play', 'review']
    const currentStep = steps[stepIndex] as SessionStep
    syncPhaseFromStep(currentStep)
  }, [pathname, syncPhaseFromStep])

  const stepIndex = sessionStepIndexFromPathname(pathname)
  const steps: SessionStep[] = ['tune', 'musical-tolerance', 'listen', 'study', 'slow', 'play', 'review']
  const currentStep = stepIndex >= 0 ? steps[stepIndex] : 'listen'

  return (
    <SafeAreaView className="flex-1 bg-ivory" edges={['top', 'left', 'right']}>
      <SessionChromeBar />
      <View className="flex flex-1 flex-row">
        <SessionDesktopRail activeStep={currentStep as SessionStep} />
        <View className="flex-1">
          <Stack screenOptions={{ headerShown: false, animation: 'slide_from_right' }} />
        </View>
      </View>
    </SafeAreaView>
  )
}
