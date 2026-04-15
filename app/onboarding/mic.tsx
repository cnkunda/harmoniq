import { Audio } from 'expo-av'
import * as Linking from 'expo-linking'
import { useRouter } from 'expo-router'
import { useCallback, useEffect, useState } from 'react'
import { Platform, Pressable, Text, View } from 'react-native'

import { OnboardingScreenShell } from '@/components/onboarding/OnboardingScreenShell'

export default function OnboardingMicScreen() {
  const router = useRouter()
  const [status, setStatus] = useState<'unknown' | 'granted' | 'denied'>('unknown')
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    if (Platform.OS === 'web') {
      setStatus('granted')
      return
    }
    const existing = await Audio.getPermissionsAsync()
    if (existing.granted) {
      setStatus('granted')
      return
    }
    if (existing.status === 'denied') {
      setStatus('denied')
      return
    }
    setStatus('unknown')
  }, [])

  const request = useCallback(async () => {
    setBusy(true)
    try {
      if (Platform.OS === 'web') {
        setStatus('granted')
        return
      }
      const res = await Audio.requestPermissionsAsync()
      setStatus(res.granted ? 'granted' : 'denied')
    } finally {
      setBusy(false)
    }
  }, [])

  const openSettings = useCallback(() => {
    void Linking.openSettings()
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return (
    <OnboardingScreenShell
      currentStep={2}
      showBack
      onBack={() => router.back()}
      footer={
        <Text className="text-center font-sans text-xs leading-5 text-muted-brown">
          If you deny permission, you won&apos;t be able to use the core practice features until the microphone is
          enabled in settings.
        </Text>
      }
    >
      <View className="items-center">
        <Text className="text-center font-serif text-2xl text-cream">Microphone</Text>
        <Text className="mt-3 text-center font-sans text-sm leading-6 text-muted-brown">
          Harmoniq listens only to score your placement phrases. Nothing is uploaded until you run analysis on a song
          later.
        </Text>

        {status === 'denied' ? (
          <View className="mt-6 w-full rounded-lg border border-danger/35 bg-danger/10 px-3 py-3">
            <Text className="text-center font-sans text-sm text-cream">Microphone access is off for this app.</Text>
            <Text className="mt-2 text-center font-sans text-xs text-muted-brown">
              Enable the mic in system settings, then tap Refresh below.
            </Text>
            <Pressable
              onPress={openSettings}
              className="mt-3 self-center rounded-md border border-amber-accent/50 px-3 py-2"
              accessibilityRole="button"
              accessibilityLabel="Open system settings"
            >
              <Text className="font-sans-medium text-sm text-amber-light">Open Settings</Text>
            </Pressable>
          </View>
        ) : null}

        <View className="mt-8 w-full gap-3">
          <Pressable
            onPress={() => void request()}
            disabled={busy || status === 'granted'}
            className="rounded-lg bg-amber-accent px-4 py-3 disabled:opacity-40"
            accessibilityRole="button"
          >
            <Text className="text-center font-sans-medium text-wood-900">
              {status === 'granted' ? 'Microphone ready' : busy ? 'Requesting…' : 'Allow microphone'}
            </Text>
          </Pressable>
          {Platform.OS !== 'web' ? (
            <Pressable
              onPress={() => void refresh()}
              className="rounded-lg border border-wood-600/50 px-4 py-3"
              accessibilityRole="button"
            >
              <Text className="text-center font-sans-medium text-cream">Refresh status</Text>
            </Pressable>
          ) : null}
        </View>

        <Pressable
          onPress={() => router.push({ pathname: '/onboarding/phrase/[index]', params: { index: '0' } })}
          disabled={status !== 'granted'}
          className="mt-10 w-full rounded-lg border border-amber-accent/60 bg-wood-800/80 px-4 py-3 disabled:opacity-35"
          accessibilityRole="button"
        >
          <Text className="text-center font-sans-medium text-amber-light">Next: placement phrases</Text>
        </Pressable>
      </View>
    </OnboardingScreenShell>
  )
}
