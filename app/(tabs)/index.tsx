import { useFocusEffect } from '@react-navigation/native'
import { useRouter } from 'expo-router'
import { useCallback, useState } from 'react'
import { Pressable, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { sessionHref } from '@/src/constants/sessionFlow'
import { getHomeSuggestion, getLickById } from '@/src/db/client'
import type { HomeSuggestion } from '@/src/db/types'
import { useLessonStore } from '@/src/stores/lessonStore'
import { lessonFromSavedLick } from '@/src/utils/lessonFromSavedLick'

export default function HomeScreen() {
  const router = useRouter()
  const saveLesson = useLessonStore((s) => s.saveLesson)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)
  const [suggestion, setSuggestion] = useState<HomeSuggestion | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [drillLatestError, setDrillLatestError] = useState<string | null>(null)

  const refresh = useCallback(() => {
    setLoadError(false)
    setDrillLatestError(null)
    void getHomeSuggestion()
      .then((s) => {
        setSuggestion(s)
        setLoadError(false)
      })
      .catch((e) => {
        console.error('[home] getHomeSuggestion failed', e)
        setLoadError(true)
      })
  }, [])

  useFocusEffect(
    useCallback(() => {
      refresh()
    }, [refresh]),
  )

  const goAnalyze = () => router.push('/add-song')
  const goSession = () => router.push(sessionHref('listen'))
  const goLibrary = () => router.push('/library')
  const goProgress = () => router.push('/progress')
  const goJam = () => router.push('/jam')
  const goSettings = () => router.push('/settings')

  const drillLatestSavedLick = useCallback(async () => {
    if (suggestion?.kind !== 'library_saved') return
    setDrillLatestError(null)
    try {
      const row = await getLickById(suggestion.latest.id)
      if (!row) {
        setDrillLatestError('That save is no longer in your library. Try Open Library.')
        return
      }
      saveLesson(lessonFromSavedLick(row, 0))
      setLessonSectionIndex(0)
      router.push('/session/study')
    } catch {
      setDrillLatestError('Could not open your latest save.')
    }
  }, [router, saveLesson, setLessonSectionIndex, suggestion])

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <View className="flex-1 px-6 py-8">
        <Text className="font-serif text-3xl text-cream">Home</Text>
        <Text className="mt-2 font-sans text-sm text-muted-brown">
          Suggestions use your last scored session and skill schedule when available; otherwise saved library licks or adding a
          song.
        </Text>

        <View className="mt-8 rounded-xl border-2 border-amber-accent/50 bg-wood-800/90 p-5 shadow-sm">
          {suggestion == null ? (
            loadError ? (
              <View>
                <Text className="font-sans text-sm text-cream">Could not load your suggestion.</Text>
                <Pressable
                  onPress={refresh}
                  className="mt-4 rounded-lg border border-amber-accent/60 bg-wood-900/50 px-4 py-3"
                  accessibilityRole="button"
                  accessibilityLabel="Retry loading suggestion"
                >
                  <Text className="text-center font-sans-medium text-amber-light">Retry</Text>
                </Pressable>
              </View>
            ) : (
              <Text className="font-sans text-sm text-cream">Loading suggestion…</Text>
            )
          ) : suggestion.kind === 'cold_start' ? (
            <>
              <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Suggested session</Text>
              <Text className="mt-3 font-sans text-base leading-6 text-cream">
                {
                  "You haven't practiced a specific song yet. Tap Add Song to bring in a lesson — we'll shape your first session around it."
                }
              </Text>
              <Pressable
                onPress={goAnalyze}
                className="mt-5 rounded-lg bg-amber-accent px-4 py-3"
                accessibilityRole="button"
                accessibilityLabel="Add a song"
              >
                <Text className="text-center font-sans-medium text-wood-900">Add Song</Text>
              </Pressable>
            </>
          ) : suggestion.kind === 'library_saved' ? (
            <>
              <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Suggested session</Text>
              <Text className="mt-3 font-sans text-base leading-6 text-cream">
                You have {suggestion.lickCount} saved {suggestion.lickCount === 1 ? 'lick' : 'licks'} from Review (tab only, no
                stems). The primary action opens your newest save in Study — same as Drill this in Library. Add a song for
                Listen with stems and the full session, or open the library to pick a different save.
              </Text>
              {drillLatestError ? (
                <Text className="mt-3 font-sans text-sm text-danger">{drillLatestError}</Text>
              ) : null}
              <Pressable
                onPress={() => void drillLatestSavedLick()}
                className="mt-5 rounded-lg bg-amber-accent px-4 py-3"
                accessibilityRole="button"
                accessibilityLabel="Drill latest saved lick in Study"
              >
                <Text className="text-center font-sans-medium text-wood-900">Drill latest save</Text>
              </Pressable>
              <Pressable
                onPress={goLibrary}
                className="mt-3 rounded-lg border border-amber-accent/55 bg-wood-900/30 px-4 py-3"
                accessibilityRole="button"
                accessibilityLabel="Open Library"
              >
                <Text className="text-center font-sans-medium text-amber-light">Open Library</Text>
              </Pressable>
              <Pressable
                onPress={goAnalyze}
                className="mt-3 rounded-lg border border-wood-600/50 bg-cream-dark/20 px-4 py-3"
                accessibilityRole="button"
                accessibilityLabel="Add a full song"
              >
                <Text className="text-center font-sans-medium text-wood-900">Add Song</Text>
              </Pressable>
            </>
          ) : (
            <>
              <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Suggested session</Text>
              <Text className="mt-3 font-serif text-xl text-cream">{suggestion.song.song_title}</Text>
              {suggestion.song.artist ? (
                <Text className="mt-1 font-sans text-sm text-muted-brown">{suggestion.song.artist}</Text>
              ) : null}
              {suggestion.song.section_label ? (
                <Text className="mt-2 font-sans text-xs text-muted-brown">Last section: {suggestion.song.section_label}</Text>
              ) : null}
              <View className="mt-4 rounded-lg border border-wood-600/60 bg-wood-900/40 px-3 py-2">
                <Text className="font-sans-medium text-sm text-amber-light">Focus</Text>
                <Text className="mt-1 font-sans text-sm text-cream">{suggestion.node.label ?? suggestion.node.id}</Text>
                <Text className="mt-1 font-mono text-xs text-muted-brown">
                  Next review: {suggestion.node.next_review_date ?? '—'} · interval {suggestion.node.interval_days}d
                </Text>
              </View>
              <Text className="mt-3 font-sans text-sm leading-5 text-muted-brown">
                Starts at Listen with stems and tab, then Study, Slow, Play, and Review — not the same as drilling a saved lick
                (Study only).
              </Text>
              <Pressable
                onPress={goSession}
                className="mt-4 rounded-lg bg-amber-accent px-4 py-3"
                accessibilityRole="button"
                accessibilityLabel="Start full practice session at Listen"
              >
                <Text className="text-center font-sans-medium text-wood-900">Start session</Text>
              </Pressable>
            </>
          )}
        </View>
        <Pressable
          onPress={goJam}
          className="mt-4 rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-3"
          accessibilityRole="button"
          accessibilityLabel="Open jam mode"
        >
          <Text className="text-center font-sans-medium text-wood-900">Jam</Text>
        </Pressable>
        <Pressable
          onPress={goProgress}
          className="mt-4 rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-3"
          accessibilityRole="button"
          accessibilityLabel="Open progress"
        >
          <Text className="text-center font-sans-medium text-wood-900">Progress</Text>
        </Pressable>
        <Pressable
          onPress={goSettings}
          className="mt-4 rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-3"
          accessibilityRole="button"
          accessibilityLabel="Open settings"
        >
          <Text className="text-center font-sans-medium text-wood-900">Settings</Text>
        </Pressable>
        <Pressable
          onPress={goLibrary}
          className="mt-4 rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-3"
          accessibilityRole="button"
          accessibilityLabel="Open Library"
        >
          <Text className="text-center font-sans-medium text-wood-900">Open Library</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  )
}
