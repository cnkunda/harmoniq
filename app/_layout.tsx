import 'react-native-gesture-handler'
import 'react-native-reanimated'
import '../global.css'

import { LinearGradient } from 'expo-linear-gradient'
import { DMSans_400Regular, DMSans_500Medium } from '@expo-google-fonts/dm-sans'
import { JetBrainsMono_400Regular } from '@expo-google-fonts/jetbrains-mono'
import {
  PlayfairDisplay_400Regular,
  PlayfairDisplay_400Regular_Italic,
  PlayfairDisplay_700Bold,
} from '@expo-google-fonts/playfair-display'
import { useFonts } from 'expo-font'
import { Stack } from 'expo-router'
import * as SplashScreen from 'expo-splash-screen'
import { useEffect } from 'react'
import { View } from 'react-native'
import { GestureHandlerRootView } from 'react-native-gesture-handler'
import { SafeAreaProvider } from 'react-native-safe-area-context'
import { cssInterop } from 'nativewind'

import { NoiseOverlay } from '@/components/NoiseOverlay'
import Toast from 'react-native-toast-message'

import { toastConfig } from '@/components/ToastConfig'

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

  if (!loaded) {
    return null
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <View className="flex-1 bg-wood-900">
          <NoiseOverlay />
          <Stack screenOptions={{ headerShown: false }}>
            <Stack.Screen name="(tabs)" />
            <Stack.Screen name="session" />
          </Stack>
          <Toast config={toastConfig} />
        </View>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  )
}
