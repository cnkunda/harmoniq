import 'react-native-gesture-handler'
import 'react-native-reanimated'
import '../global.css'

import { DMSans_400Regular, DMSans_500Medium } from '@expo-google-fonts/dm-sans'
import { JetBrainsMono_400Regular } from '@expo-google-fonts/jetbrains-mono'
import {
    PlayfairDisplay_400Regular,
    PlayfairDisplay_400Regular_Italic,
    PlayfairDisplay_700Bold,
} from '@expo-google-fonts/playfair-display'
import { useFonts } from 'expo-font'
import { LinearGradient } from 'expo-linear-gradient'
import { Stack } from 'expo-router'
import * as SplashScreen from 'expo-splash-screen'
import { cssInterop } from 'nativewind'
import { useEffect } from 'react'
import { AppState, Platform, View } from 'react-native'
import { GestureHandlerRootView } from 'react-native-gesture-handler'
import { SafeAreaProvider } from 'react-native-safe-area-context'

import { NoiseOverlay } from '@/components/NoiseOverlay'
import Toast from 'react-native-toast-message'

import { toastConfig } from '@/components/ToastConfig'
import { isActiveTrackedJob } from '@/src/analysis/trackedAnalysisJobs'
import { startAnalytics } from '@/src/analytics/eventBus'
import { hydrateVoiceCoachPrefs } from '@/src/audio/hydrateVoiceCoachPrefs'
import { hydrateWebLessonStore, initDb } from '@/src/db/client'
import { resumeActivePracticePlan } from '@/src/session/activePlanPersistence'
import { useAnalysisJobsStore } from '@/src/stores/analysisJobsStore'
import { useOutputTierStore } from '@/src/stores/outputTierStore'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'

cssInterop(LinearGradient, { className: 'style' })

SplashScreen.preventAutoHideAsync()

export default function RootLayout() {
  const [loaded, error] = useFonts({
    'PlayfairDisplay-Regular': PlayfairDisplay_400Regular,
    'PlayfairDisplay-Bold': PlayfairDisplay_700Bold,
    'PlayfairDisplay-Italic': PlayfairDisplay_400Regular_Italic,
    'DMSans-Regular': DMSans_400Regular,
    'DMSans-Medium': DMSans_500Medium,
    'JetBrainsMono-Regular': JetBrainsMono_400Regular,
  })

  useEffect(() => {
    if (error) throw error
  }, [error])

  useEffect(() => {
    if (loaded) SplashScreen.hideAsync()
  }, [loaded])

  useEffect(() => {
    void (async () => {
      try {
        await initDb()
        const resumedPlan = await resumeActivePracticePlan()
        if (resumedPlan) {
          console.log('[planPersistence] restored active plan', resumedPlan.plan_id)
        }
        await startAnalytics()
        await useSessionPrefsStore.getState().hydrate()
        await useOutputTierStore.getState().hydrate()
        await hydrateVoiceCoachPrefs()
        if (Platform.OS === 'web') {
          await hydrateWebLessonStore()
        }
      } catch (e) {
        console.error('[db] init failed', e)
      }
    })()
  }, [])

  useEffect(() => {
    if (!loaded) return
    void (async () => {
      try {
        await useAnalysisJobsStore.getState().hydrate()
        await useAnalysisJobsStore.getState().refresh()
      } catch (refreshError) {
        console.log('[analysisJobs] startup refresh failed', refreshError)
      }
    })()
  }, [loaded])

  useEffect(() => {
    const refreshTrackedJobs = () => {
      void useAnalysisJobsStore
        .getState()
        .refresh()
        .catch((refreshError) => console.log('[analysisJobs] watcher refresh failed', refreshError))
    }
    const sync = () => {
      if (AppState.currentState !== 'active') return
      if (!useAnalysisJobsStore.getState().jobs.some(isActiveTrackedJob)) return
      refreshTrackedJobs()
    }
    const id = setInterval(sync, 20_000)
    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active') refreshTrackedJobs()
    })
    return () => {
      clearInterval(id)
      subscription.remove()
    }
  }, [])

  if (!loaded) {
    return null
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <View className="flex-1 bg-wood-900">
          <NoiseOverlay />
          <Stack screenOptions={{ headerShown: false }}>
            <Stack.Screen name="index" />
            <Stack.Screen name="onboarding" />
            <Stack.Screen name="(tabs)" />
            <Stack.Screen name="add-song" options={{ presentation: 'modal' }} />
            <Stack.Screen name="listening" />
            <Stack.Screen name="review-archive/[sessionId]" />
            <Stack.Screen name="settings/feedback" />
            <Stack.Screen name="settings/analytics" />
            <Stack.Screen name="session" />
            <Stack.Screen name="jam-practice" />
          </Stack>
          <Toast config={toastConfig} />
        </View>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  )
}
