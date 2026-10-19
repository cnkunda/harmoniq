import { DarkTheme, ThemeProvider } from '@react-navigation/native'
import { Stack, usePathname } from 'expo-router'
import { useEffect } from 'react'
import { View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { SessionChromeBar } from '@/components/SessionChromeBar'
import { WoodGradient } from '@/components/WoodGradient'
import { colors } from '@/src/constants/colors'
import { sessionStepIndexFromPathname, type SessionStep } from '@/src/constants/sessionFlow'
import { useSessionPhaseStore } from '@/src/stores/sessionPhaseStore'

// Scenes otherwise inherit React Navigation's default light background
// (rgb(242,242,242)), which covers the shared WoodGradient.
const SESSION_NAV_THEME = {
  ...DarkTheme,
  colors: { ...DarkTheme.colors, background: colors.wood[900] },
}

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

  return (
    <View className="flex-1 bg-wood-900">
      <WoodGradient variant="background" className="flex-1">
        <SafeAreaView className="flex-1" edges={['top', 'left', 'right']}>
          <SessionChromeBar />
          <ThemeProvider value={SESSION_NAV_THEME}>
            <Stack screenOptions={{ headerShown: false, animation: 'slide_from_right' }} />
          </ThemeProvider>
        </SafeAreaView>
      </WoodGradient>
    </View>
  )
}
