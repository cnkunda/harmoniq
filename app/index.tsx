import { Redirect } from 'expo-router'
import { useEffect, useState } from 'react'
import { ActivityIndicator, View } from 'react-native'

import { getLicks, getOnboardingComplete, initDb, listLessonsJournal } from '@/src/db/client'

/** Enter main app if placement onboarding finished or user already has library content. */
async function shouldEnterMainApp(): Promise<boolean> {
  await initDb()
  const [onboardingDone, lessons, licks] = await Promise.all([
    getOnboardingComplete(),
    listLessonsJournal(),
    getLicks(),
  ])
  return onboardingDone || lessons.length > 0 || licks.length > 0
}

export default function EntryRedirect() {
  const [done, setDone] = useState<boolean | null>(null)

  useEffect(() => {
    void shouldEnterMainApp()
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
