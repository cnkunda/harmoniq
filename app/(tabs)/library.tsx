import { useFocusEffect } from '@react-navigation/native'
import { useRouter } from 'expo-router'
import { useCallback, useMemo, useState } from 'react'
import { Filter, Search } from 'lucide-react-native'
import { Alert, Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { WoodGradient } from '@/components/WoodGradient'
import colors from '@/src/constants/colors'
import { clearAllPracticeData, deleteLickById, getLicks } from '@/src/db/client'
import type { LickRow } from '@/src/db/types'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSessionAnnotationsStore } from '@/src/stores/sessionAnnotationsStore'
import { lessonFromSavedLick } from '@/src/utils/lessonFromSavedLick'

export default function LibraryScreen() {
  const router = useRouter()
  const saveLesson = useLessonStore((s) => s.saveLesson)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)
  const [licks, setLicks] = useState<LickRow[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [search, setSearch] = useState<string>('')
  const [showFilters, setShowFilters] = useState(false)
  const [songFilter, setSongFilter] = useState<string>('all')
  const [techniqueFilter, setTechniqueFilter] = useState<string>('all')
  const [transposeById, setTransposeById] = useState<Record<string, number>>({})

  const refresh = useCallback(() => {
    setLoadError(null)
    void getLicks()
      .then(setLicks)
      .catch((e) => setLoadError(e instanceof Error ? e.message : 'Could not load licks.'))
  }, [])

  useFocusEffect(
    useCallback(() => {
      refresh()
    }, [refresh]),
  )

  const drill = useCallback(
    (lick: LickRow) => {
      const semitones = transposeById[lick.id] ?? 0
      saveLesson(lessonFromSavedLick(lick, semitones))
      setLessonSectionIndex(0)
      router.push('/session/study')
    },
    [router, saveLesson, setLessonSectionIndex, transposeById],
  )

  const performRemoveLick = useCallback(async (lick: LickRow) => {
    try {
      setLoadError(null)
      await deleteLickById(lick.id)
      const { lesson, resetLesson } = useLessonStore.getState()
      if (lesson?.job_id === `lick-${lick.id}`) resetLesson()
      setTransposeById((prev) => {
        const next = { ...prev }
        delete next[lick.id]
        return next
      })
      const rows = await getLicks()
      if (rows.length === 0) {
        await clearAllPracticeData()
        useLessonStore.getState().resetLesson()
        useSessionAnnotationsStore.getState().clearAll()
      }
      setLicks(rows)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Could not remove lick.')
    }
  }, [])

  const confirmRemoveLick = useCallback(
    (lick: LickRow) => {
      const title = lick.song_title?.trim() || 'this lick'
      const message = `Remove "${title}" from saved licks on this device? This cannot be undone.`

      if (Platform.OS === 'web') {
        if (typeof window !== 'undefined' && window.confirm(`Remove from library?\n\n${message}`)) {
          void performRemoveLick(lick)
        }
        return
      }

      Alert.alert('Remove from library?', message, [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Remove',
          style: 'destructive',
          onPress: () => void performRemoveLick(lick),
        },
      ])
    },
    [performRemoveLick],
  )

  const songOptions = useMemo(() => {
    const set = new Set<string>()
    for (const l of licks) {
      const s = l.song_title?.trim()
      if (s) set.add(s)
    }
    return ['all', ...Array.from(set).sort((a, b) => a.localeCompare(b))]
  }, [licks])

  const techniqueOptions = useMemo(() => {
    const set = new Set<string>()
    for (const l of licks) {
      for (const t of l.technique_tags ?? []) {
        const s = t.trim()
        if (s) set.add(s)
      }
    }
    return ['all', ...Array.from(set).sort((a, b) => a.localeCompare(b))]
  }, [licks])

  const filteredLicks = useMemo(
    () =>
      licks.filter((l) => {
        const q = search.trim().toLowerCase()
        const song = l.song_title?.toLowerCase() ?? ''
        const artist = l.artist?.toLowerCase() ?? ''
        const position = l.position?.toLowerCase() ?? ''
        const coach = l.coach_oneliner?.toLowerCase() ?? ''
        const tags = (l.technique_tags ?? []).map((t) => t.toLowerCase())
        const bySearch =
          q.length === 0 ||
          song.includes(q) ||
          artist.includes(q) ||
          position.includes(q) ||
          coach.includes(q) ||
          tags.some((t) => t.includes(q))
        const bySong = songFilter === 'all' || (l.song_title?.trim() ?? '') === songFilter
        const byTechnique = techniqueFilter === 'all' || (l.technique_tags ?? []).includes(techniqueFilter)
        return bySearch && bySong && byTechnique
      }),
    [licks, search, songFilter, techniqueFilter],
  )

  const empty = useMemo(() => filteredLicks.length === 0 && !loadError, [filteredLicks.length, loadError])

  return (
    <WoodGradient className="flex-1">
      <SafeAreaView className="flex-1" edges={['top', 'left', 'right']}>
        <ScrollView
          className="flex-1"
          contentContainerStyle={{ paddingBottom: 28 }}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View className="w-full max-w-6xl self-center px-6 pb-6 pt-4">
            <View className="mb-8 mt-4">
              <Text className="mb-2 font-serif text-3xl text-cream">Lick Library</Text>
              <Text className="font-sans text-muted-brown">Your personal vocabulary of expressive phrases.</Text>
            </View>

            <View className="mb-10 flex-row items-center gap-3">
              <View className="relative min-h-14 flex-1 overflow-hidden rounded-xl border border-wood-700 bg-wood-800/60 shadow-inner-wood">
                <View className="pointer-events-none absolute bottom-0 left-3 top-0 z-10 justify-center">
                  <Search color={colors.muted.brown} size={18} />
                </View>
                <TextInput
                  value={search}
                  onChangeText={setSearch}
                  placeholder="Search by song, artist, or technique..."
                  placeholderTextColor={colors.muted.brown}
                  className="min-h-14 flex-1 py-3 pl-10 pr-4 font-sans text-sm text-cream"
                />
              </View>
              <Pressable
                onPress={() => setShowFilters((v) => !v)}
                className="min-h-14 flex-row items-center gap-2 rounded-xl border border-wood-700 bg-wood-800/60 px-4"
                accessibilityRole="button"
                accessibilityLabel="Toggle filters"
              >
                <Filter color={showFilters ? colors.cream : colors.muted.brown} size={18} />
                <Text className={`font-sans text-sm ${showFilters ? 'text-cream' : 'text-muted-brown'}`}>
                  {showFilters ? 'Hide' : 'Filter'}
                </Text>
              </Pressable>
            </View>

            {showFilters ? (
              <View className="mb-6 rounded-xl border border-wood-700/50 bg-wood-800/40 p-4">
                <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-amber-light">Song filter</Text>
                <View className="mb-4 flex-row flex-wrap gap-2">
                  {songOptions.map((s) => (
                    <Pressable
                      key={`song-${s}`}
                      onPress={() => setSongFilter(s)}
                      className={`rounded-full border px-3 py-1.5 ${
                        songFilter === s ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/45 bg-cream-dark/35'
                      }`}
                    >
                      <Text className={`font-sans text-xs ${songFilter === s ? 'text-wood-900' : 'text-muted-brown'}`}>
                        {s === 'all' ? 'All songs' : s}
                      </Text>
                    </Pressable>
                  ))}
                </View>

                <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-amber-light">
                  Technique filter
                </Text>
                <View className="flex-row flex-wrap gap-2">
                  {techniqueOptions.map((t) => (
                    <Pressable
                      key={`tech-${t}`}
                      onPress={() => setTechniqueFilter(t)}
                      className={`rounded-full border px-3 py-1.5 ${
                        techniqueFilter === t
                          ? 'border-amber-accent bg-amber-accent/20'
                          : 'border-wood-600/45 bg-cream-dark/35'
                      }`}
                    >
                      <Text className={`font-sans text-xs ${techniqueFilter === t ? 'text-wood-900' : 'text-muted-brown'}`}>
                        {t === 'all' ? 'All techniques' : t}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              </View>
            ) : null}

            {loadError ? (
              <View className="mb-6 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2">
                <Text className="font-sans text-sm text-danger">{loadError}</Text>
              </View>
            ) : null}

            {empty ? (
              <View className="items-center py-20">
                <Text className="font-sans text-muted-brown">
                  {licks.length === 0 ? 'No saved licks yet.' : 'No licks found matching your search.'}
                </Text>
              </View>
            ) : (
              <View className="flex-row flex-wrap gap-4">
                {filteredLicks.map((lick) => (
                  <View key={lick.id} className="w-full rounded-xl border border-wood-700/50 bg-wood-800/40 p-4 md:w-[48%] lg:w-[31%]">
                    <Text className="font-serif text-lg text-cream">{lick.song_title?.trim() || 'Untitled lick'}</Text>
                    <Text className="mt-0.5 font-sans text-xs text-muted-brown">{lick.artist?.trim() || 'Unknown artist'}</Text>

                    <View className="mt-3 flex-row flex-wrap items-center gap-2">
                      {(lick.technique_tags ?? []).slice(0, 2).map((tag) => (
                        <View key={`${lick.id}-${tag}`} className="rounded bg-wood-700 px-2 py-1">
                          <Text className="font-sans text-[10px] uppercase tracking-wider text-amber-light">{tag}</Text>
                        </View>
                      ))}
                      {lick.position ? (
                        <View className="rounded bg-wood-700 px-2 py-1">
                          <Text className="font-sans text-[10px] uppercase tracking-wider text-muted-brown">{lick.position}</Text>
                        </View>
                      ) : null}
                    </View>

                    <Text className="mt-3 border-t border-wood-700/50 pt-3 font-sans text-xs italic leading-relaxed text-cream/80" numberOfLines={3}>
                      &ldquo;{lick.coach_oneliner?.trim() || 'A phrase worth revisiting with control and feel.'}&rdquo;
                    </Text>

                    <View className="mt-3 flex-row items-center gap-2">
                      {[-2, -1, 0, 1, 2].map((n) => {
                        const selected = (transposeById[lick.id] ?? 0) === n
                        return (
                          <Pressable
                            key={`${lick.id}-tp-${n}`}
                            onPress={() =>
                              setTransposeById((prev) => ({
                                ...prev,
                                [lick.id]: n,
                              }))
                            }
                            className={`rounded-full border px-2.5 py-1 ${
                              selected ? 'border-amber-accent bg-amber-accent/25' : 'border-wood-600/45 bg-cream-dark/35'
                            }`}
                          >
                            <Text className={`font-mono text-[11px] ${selected ? 'text-wood-900' : 'text-muted-brown'}`}>
                              {n > 0 ? `+${n}` : n}
                            </Text>
                          </Pressable>
                        )
                      })}
                    </View>

                    <View className="mt-3 flex-row items-center gap-2">
                      <Pressable
                        onPress={() => drill(lick)}
                        className="flex-1 rounded-lg bg-wood-700 px-3 py-2"
                        accessibilityRole="button"
                        accessibilityLabel="Drill this lick"
                      >
                        <Text className="text-center font-sans-medium text-sm text-amber-light">Drill this</Text>
                      </Pressable>
                      <Pressable
                        onPress={() => confirmRemoveLick(lick)}
                        className="rounded-lg border border-danger/45 bg-wood-900/50 px-3 py-2"
                        accessibilityRole="button"
                        accessibilityLabel="Remove from library"
                      >
                        <Text className="font-sans-medium text-xs text-danger">Remove</Text>
                      </Pressable>
                    </View>
                  </View>
                ))}
              </View>
            )}
          </View>
        </ScrollView>
      </SafeAreaView>
    </WoodGradient>
  )
}
