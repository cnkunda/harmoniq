import { Redirect } from 'expo-router'
import { useEffect, useState } from 'react'
import { ActivityIndicator, Platform, Text, View } from 'react-native'

import { toast } from '@/components/ToastConfig'
import { getLicks, getOnboardingComplete, initDb, listLessonsJournal } from '@/src/db/client'
import { fetchPersistAndDeriveSpotifyTaste } from '@/src/spotify/fetchPersistAndDeriveSpotify'
import { formatSpotifySetupError } from '@/src/spotify/spotifyConnectErrors'
import { hasCommittedTasteOrSpotifyRaw } from '@/src/taste/tasteQuizGate'
import colors from '@/src/constants/colors'

/** Enter main app if placement finished, library content exists, or taste/Spotify prefs are present. */
async function shouldEnterMainApp(): Promise<boolean> {
  await initDb()
  const [onboardingDone, lessons, licks, tasteGate] = await Promise.all([
    getOnboardingComplete(),
    listLessonsJournal(),
    getLicks(),
    hasCommittedTasteOrSpotifyRaw(),
  ])
  return onboardingDone || lessons.length > 0 || licks.length > 0 || tasteGate
}

export default function EntryRedirect() {
  const [done, setDone] = useState<boolean | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        await initDb()
        if (Platform.OS === 'web' && typeof window !== 'undefined') {
          const sp = new URLSearchParams(window.location.search)
          const oauth = sp.get('spotify_oauth')
          const cs = (sp.get('client_session') ?? '').trim()
          if (oauth === '1' && cs) {
            try {
              await fetchPersistAndDeriveSpotifyTaste(cs)
              toast.success('Spotify connected.')
            } catch (e) {
              toast.error(formatSpotifySetupError(e))
            }
            window.history.replaceState({}, '', `${window.location.pathname}${window.location.hash}`)
          } else if (oauth === '0' || sp.get('spotify_error') === '1') {
            window.history.replaceState({}, '', `${window.location.pathname}${window.location.hash}`)
            toast.error('Spotify authorization was cancelled or failed.')
          }
        }
        const ok = await shouldEnterMainApp()
        setDone(ok)
      } catch {
        setDone(false)
      }
    })()
  }, [])

  if (done === null) {
    return (
      <View className="flex-1 items-center justify-center gap-4 bg-wood-900 px-8">
        <ActivityIndicator accessibilityLabel="Loading" color={colors.amber.light} />
        <Text className="text-center font-sans text-sm text-muted-brown">Loading…</Text>
      </View>
    )
  }

  if (done) {
    return <Redirect href="/(tabs)" />
  }
  return <Redirect href="/onboarding" />
}
