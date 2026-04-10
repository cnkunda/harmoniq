import { Redirect } from 'expo-router'
import { useEffect, useState } from 'react'
import { ActivityIndicator, View } from 'react-native'

import { getOnboardingComplete } from '@/src/db/client'

export default function EntryRedirect() {
  const [done, setDone] = useState<boolean | null>(null)

  useEffect(() => {
    void getOnboardingComplete()
      .then(setDone)
      .catch(() => setDone(false))
  }, [])

  if (done === null) {
    return (
      <View className="flex-1 items-center justify-center bg-wood-900">
        <ActivityIndicator color="#E8A54B" />
      </View>
    )
  }

  if (done) {
    return <Redirect href="/(tabs)" />
  }
  return <Redirect href="/onboarding" />
}
