import { useFocusEffect } from '@react-navigation/native'
import { useRouter, type Href } from 'expo-router'
import { Bookmark, Filter, Music, Search } from 'lucide-react-native'
import { useCallback, useMemo, useState } from 'react'
import { Alert, Platform, ScrollView, Text, TextInput, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { PrimaryButton } from '@/components/Button'
import { EmptyState } from '@/components/EmptyState'
import { WoodGradient } from '@/components/WoodGradient'
import { ApiError, submitExportJob } from '@/src/api/analyze'
import colors from '@/src/constants/colors'
import { sessionEntryHrefWithMoodCheck } from '@/src/constants/sessionFlow'
import {
    clearAllPracticeData,
    deleteLessonByJobId,
    deleteLickById,
    getLessonByJobId,
    getLicks,
    listLessonsJournal,
} from '@/src/db/client'
import type { LessonListRow, LickRow } from '@/src/db/types'
import { DEMO_LESSON_JOB_ID } from '@/src/demo/constants'
import { getDemoLesson } from '@/src/demo/demoLesson'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSessionAnnotationsStore } from '@/src/stores/sessionAnnotationsStore'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
import { shareExportedBlob } from '@/src/utils/exportShare'
import { lessonFromSavedLick } from '@/src/utils/lessonFromSavedLick'
import { firstGp5Base64FromLessonSections } from '@/src/utils/lessonTabs'

type LibraryTab = 'lessons' | 'licks'

function relativeDateLabel(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return 'Recently'

  const today = new Date()
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const startOfDate = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const dayMs = 24 * 60 * 60 * 1000
  const days = Math.floor((startOfToday.getTime() - startOfDate.getTime()) / dayMs)

  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days} days ago`
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export default function LibraryScreen() {
  const router = useRouter()
  const saveLesson = useLessonStore((s) => s.saveLesson)
  const resetLesson = useLessonStore((s) => s.resetLesson)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)
  const [libraryTab, setLibraryTab] = useState<LibraryTab>('lessons')
  const [lessons, setLessons] = useState<LessonListRow[]>([])
  const [licks, setLicks] = useState<LickRow[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [search, setSearch] = useState<string>('')
  const [showFilters, setShowFilters] = useState(false)
  const [songFilter, setSongFilter] = useState<string>('all')
  const [techniqueFilter, setTechniqueFilter] = useState<string>('all')
  const [transposeById, setTransposeById] = useState<Record<string, number>>({})
  const [exportBusyJobId, setExportBusyJobId] = useState<string | null>(null)

  const refresh = useCallback(() => {
    setLoadError(null)
    void Promise.all([getLicks(), listLessonsJournal()])
      .then(([lickRows, lessonRows]) => {
        setLicks(lickRows)
        setLessons(lessonRows)
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : 'Could not load library.'))
  }, [])

  useFocusEffect(
    useCallback(() => {
      refresh()
    }, [refresh]),
  )

  const exportLessonMidi = useCallback(async (row: LessonListRow) => {
    setLoadError(null)
    setExportBusyJobId(row.job_id)
    try {
      const full = await getLessonByJobId(row.job_id)
      const gp = full ? firstGp5Base64FromLessonSections(full.sections) : null
      if (!gp) {
        setLoadError('This song has no GP5 tab data to export yet.')
        return
      }
      const title = typeof full?.song_title === 'string' ? full.song_title.trim() : null
      const fallbackBase =
        typeof full?.song_title === 'string' && full.song_title.trim()
          ? full.song_title.trim()
          : row.song_title?.trim() || 'song'
      const { blob, mimeType, contentDisposition } = await submitExportJob({
        gp5_base64: gp,
        format: 'midi',
        title,
      })
      await shareExportedBlob({
        blob,
        mimeType,
        contentDisposition,
        fallbackBase,
        dialogTitle: 'Export MIDI',
      })
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : 'Could not export MIDI.')
    } finally {
      setExportBusyJobId(null)
    }
  }, [])

  const openFullLesson = useCallback(
    async (row: LessonListRow) => {
      setLoadError(null)
      try {
        if (row.job_id === DEMO_LESSON_JOB_ID) {
          // Demo lesson is in-memory only - load directly from getDemoLesson()
          const demoLesson = getDemoLesson()
          saveLesson(demoLesson)
          setLessonSectionIndex(0)
          void sessionEntryHrefWithMoodCheck(useSessionPrefsStore.getState().skipTuneStep).then((href) =>
            router.push(href as Href),
          )
          return
        }
        const full = await getLessonByJobId(row.job_id)
        if (!full) {
          setLoadError('That song could not be loaded.')
          return
        }
        saveLesson(full)
        setLessonSectionIndex(0)
        void sessionEntryHrefWithMoodCheck(useSessionPrefsStore.getState().skipTuneStep).then((href) =>
          router.push(href as Href),
        )
      } catch {
        setLoadError('Could not open song.')
      }
    },
    [router, saveLesson, setLessonSectionIndex],
  )

  const performRemoveLesson = useCallback(
    async (row: LessonListRow) => {
      try {
        setLoadError(null)
        await deleteLessonByJobId(row.job_id)
        const { lesson } = useLessonStore.getState()
        if (lesson?.job_id === row.job_id) resetLesson()
        setLessons(await listLessonsJournal())
      } catch (e) {
        setLoadError(e instanceof Error ? e.message : 'Could not remove song.')
      }
    },
    [resetLesson],
  )

  const confirmRemoveLesson = useCallback(
    (row: LessonListRow) => {
      const title = row.song_title?.trim() || 'this song'
      const message = `Remove "${title}" and its saved analysis from this device? This cannot be undone.`

      if (Platform.OS === 'web') {
        if (typeof window !== 'undefined' && window.confirm(`Remove song?\n\n${message}`)) {
          void performRemoveLesson(row)
        }
        return
      }

      Alert.alert('Remove song?', message, [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Remove',
          style: 'destructive',
          onPress: () => void performRemoveLesson(row),
        },
      ])
    },
    [performRemoveLesson],
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

  const listenToLick = useCallback(
    (lick: LickRow) => {
      const semitones = transposeById[lick.id] ?? 0
      saveLesson(lessonFromSavedLick(lick, semitones))
      setLessonSectionIndex(0)
      void sessionEntryHrefWithMoodCheck(useSessionPrefsStore.getState().skipTuneStep).then((href) =>
        router.push(href as Href),
      )
    },
    [router, saveLesson, setLessonSectionIndex, transposeById],
  )

  const performRemoveLick = useCallback(async (lick: LickRow) => {
    try {
      setLoadError(null)
      await deleteLickById(lick.id)
      const { lesson, resetLesson: reset } = useLessonStore.getState()
      if (lesson?.job_id === `lick-${lick.id}`) reset()
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
        setLessons([])
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

  const lessonsPool = useMemo(() => {
    return lessons
  }, [lessons])

  const filteredLessons = useMemo(() => {
    const q = search.trim().toLowerCase()
    return lessonsPool.filter((l) => {
      if (q.length === 0) return true
      const song = l.song_title?.toLowerCase() ?? ''
      const artist = l.artist?.toLowerCase() ?? ''
      return song.includes(q) || artist.includes(q)
    })
  }, [lessonsPool, search])

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

  const emptyLessons = filteredLessons.length === 0 && !loadError
  const emptyLicks = filteredLicks.length === 0 && !loadError

  const searchPlaceholder =
    libraryTab === 'lessons' ? 'Search songs by title or artist…' : 'Search by song, artist, or technique…'

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
            <View className="mb-6 mt-4">
              <Text className="mb-2 font-serif text-3xl text-cream">Library</Text>
              <Text className="font-sans text-sm leading-6 text-cream/85">
                Full songs you&apos;ve analyzed, and licks saved from Review.
              </Text>
            </View>

            <View className="mb-6 flex-row rounded-xl border border-wood-700 bg-wood-800/50 p-1">
              <AnimatedPressable haptic="light"
                onPress={() => setLibraryTab('lessons')}
                className={`flex-1 rounded-lg py-2.5 ${libraryTab === 'lessons' ? 'bg-wood-700' : ''}`}
                accessibilityRole="tab"
                accessibilityState={{ selected: libraryTab === 'lessons' }}
              >
                <Text
                  className={`text-center font-sans-medium text-sm ${libraryTab === 'lessons' ? 'text-amber-light' : 'text-muted-light'}`}
                >
                  Songs
                </Text>
              </AnimatedPressable>
              <AnimatedPressable haptic="light"
                onPress={() => setLibraryTab('licks')}
                className={`flex-1 rounded-lg py-2.5 ${libraryTab === 'licks' ? 'bg-wood-700' : ''}`}
                accessibilityRole="tab"
                accessibilityState={{ selected: libraryTab === 'licks' }}
              >
                <Text
                  className={`text-center font-sans-medium text-sm ${libraryTab === 'licks' ? 'text-amber-light' : 'text-muted-light'}`}
                >
                  Licks
                </Text>
              </AnimatedPressable>
            </View>

            <View className="mb-10 flex-row items-center gap-3">
              <View className="relative min-h-14 flex-1 overflow-hidden rounded-xl border border-wood-700 bg-wood-800/60 shadow-inner-wood">
                <View className="pointer-events-none absolute bottom-0 left-3 top-0 z-10 justify-center">
                  <Search color={colors.muted.light} size={18} />
                </View>
                <TextInput
                  value={search}
                  onChangeText={setSearch}
                  placeholder={searchPlaceholder}
                  placeholderTextColor={colors.muted.light}
                  className="min-h-14 flex-1 py-3 pl-10 pr-4 font-sans text-sm text-cream"
                />
              </View>
              {libraryTab === 'licks' ? (
                <AnimatedPressable haptic="light"
                  onPress={() => setShowFilters((v) => !v)}
                  className="min-h-14 flex-row items-center gap-2 rounded-xl border border-wood-700 bg-wood-800/60 px-4"
                  accessibilityRole="button"
                  accessibilityLabel="Toggle filters"
                >
                  <Filter color={showFilters ? colors.cream : colors.muted.light} size={18} />
                  <Text className={`font-sans text-sm ${showFilters ? 'text-cream' : 'text-muted-light'}`}>
                    {showFilters ? 'Hide' : 'Filter'}
                  </Text>
                </AnimatedPressable>
              ) : null}
            </View>

            {libraryTab === 'licks' && showFilters ? (
              <View className="mb-6 rounded-xl border border-wood-700/50 bg-wood-800/40 p-4">
                <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-amber-light">Song filter</Text>
                <View className="mb-4 flex-row flex-wrap gap-2">
                  {songOptions.map((s) => (
                    <AnimatedPressable haptic="light"
                      key={`song-${s}`}
                      onPress={() => setSongFilter(s)}
                      className={`rounded-full border px-3 py-1.5 ${
                        songFilter === s ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/45 bg-cream-dark/35'
                      }`}
                    >
                      <Text className={`font-sans text-xs ${songFilter === s ? 'text-wood-900' : 'text-muted-light'}`}>
                        {s === 'all' ? 'All songs' : s}
                      </Text>
                    </AnimatedPressable>
                  ))}
                </View>

                <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-amber-light">
                  Technique filter
                </Text>
                <View className="flex-row flex-wrap gap-2">
                  {techniqueOptions.map((t) => (
                    <AnimatedPressable haptic="light"
                      key={`tech-${t}`}
                      onPress={() => setTechniqueFilter(t)}
                      className={`rounded-full border px-3 py-1.5 ${
                        techniqueFilter === t
                          ? 'border-amber-accent bg-amber-accent/20'
                          : 'border-wood-600/45 bg-cream-dark/35'
                      }`}
                    >
                      <Text className={`font-sans text-xs ${techniqueFilter === t ? 'text-wood-900' : 'text-muted-light'}`}>
                        {t === 'all' ? 'All techniques' : t}
                      </Text>
                    </AnimatedPressable>
                  ))}
                </View>
              </View>
            ) : null}

            {loadError ? (
              <View className="mb-6 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2">
                <Text className="font-sans text-sm text-danger">{loadError}</Text>
              </View>
            ) : null}

            {libraryTab === 'lessons' ? (
              emptyLessons ? (
                lessons.length === 0 ? (
                  <EmptyState
                    Icon={Music}
                    heading="No analyzed songs yet"
                    subtext="Add a song from YouTube or upload an audio file to get your first lesson."
                    ctaLabel="Add song →"
                    onCta={() => router.push('/add-song')}
                  />
                ) : (
                  <View className="items-center gap-3 py-20">
                    <Text className="font-sans text-sm text-cream/80">No songs match your search.</Text>
                    <Text className="font-sans text-xs text-muted-light">Try a different title or artist.</Text>
                  </View>
                )
              ) : (
                <View className="flex-row flex-wrap gap-4">
                  {filteredLessons.map((row) => (
                    <View
                      key={row.job_id}
                      className="w-full rounded-xl border border-wood-700/50 bg-wood-800/40 p-4 md:w-[48%] lg:w-[31%]"
                    >
                      <Text className="font-serif text-lg text-cream">{row.song_title?.trim() || 'Untitled song'}</Text>
                      <Text className="mt-0.5 font-sans text-xs text-muted-light">{row.artist?.trim() || 'Unknown artist'}</Text>
                      <Text className="mt-2 font-sans text-xs text-muted-light">
                        {row.section_count} {row.section_count === 1 ? 'section' : 'sections'} · {relativeDateLabel(row.analyzed_at)}
                      </Text>
                      <View className="mt-3 flex-row flex-wrap items-center gap-2">
                        <AnimatedPressable haptic="light"
                          onPress={() => void openFullLesson(row)}
                          className="min-w-[120px] flex-1 rounded-lg bg-wood-700 px-3 py-2"
                          accessibilityRole="button"
                          accessibilityLabel="Listen to full song"
                        >
                          <Text className="text-center font-sans-medium text-sm text-amber-light">Listen</Text>
                        </AnimatedPressable>
                        <AnimatedPressable
                          onPress={() => void exportLessonMidi(row)}
                          disabled={exportBusyJobId === row.job_id}
                          className={`min-w-[120px] flex-1 rounded-lg border border-wood-600/45 bg-cream-dark/35 px-3 py-2 ${
                            exportBusyJobId === row.job_id ? 'opacity-40' : ''
                          }`}
                          accessibilityRole="button"
                          accessibilityLabel="Export song MIDI"
                        >
                          <Text className="text-center font-sans-medium text-sm text-wood-900">
                            {exportBusyJobId === row.job_id ? 'Exporting…' : 'Export MIDI'}
                          </Text>
                        </AnimatedPressable>
                        <AnimatedPressable haptic="light"
                          onPress={() => confirmRemoveLesson(row)}
                          className="rounded-lg border border-danger/45 bg-wood-900/50 px-3 py-2"
                          accessibilityRole="button"
                          accessibilityLabel="Remove song"
                        >
                          <Text className="font-sans-medium text-xs text-danger">Remove</Text>
                        </AnimatedPressable>
                      </View>
                    </View>
                  ))}
                </View>
              )
            ) : emptyLicks ? (
              licks.length === 0 ? (
                <EmptyState
                  Icon={Bookmark}
                  heading="No saved licks yet"
                  subtext="Licks you save from Review will appear here for quick drill practice."
                  ctaLabel="Go to Progress"
                  onCta={() => router.push('/(tabs)/progress')}
                />
              ) : (
                <View className="items-center gap-3 py-20">
                  <Text className="font-sans text-sm text-cream/80">No licks match your search.</Text>
                  <Text className="font-sans text-xs text-muted-light">Adjust filters or try another keyword.</Text>
                </View>
              )
            ) : (
              <View className="flex-row flex-wrap gap-4">
                {filteredLicks.map((lick) => (
                  <View key={lick.id} className="w-full rounded-xl border border-wood-700/50 bg-wood-800/40 p-4 md:w-[48%] lg:w-[31%]">
                    <Text className="font-serif text-lg text-cream">{lick.song_title?.trim() || 'Untitled lick'}</Text>
                    <Text className="mt-0.5 font-sans text-xs text-muted-light">{lick.artist?.trim() || 'Unknown artist'}</Text>

                    <View className="mt-3 flex-row flex-wrap items-center gap-2">
                      {(lick.technique_tags ?? []).slice(0, 2).map((tag) => (
                        <View key={`${lick.id}-${tag}`} className="rounded bg-wood-700 px-2 py-1">
                          <Text className="font-sans text-[10px] uppercase tracking-wider text-amber-light">{tag}</Text>
                        </View>
                      ))}
                      {lick.position ? (
                        <View className="rounded bg-wood-700 px-2 py-1">
                          <Text className="font-sans text-[10px] uppercase tracking-wider text-muted-light">{lick.position}</Text>
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
                          <AnimatedPressable haptic="light"
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
                            <Text className={`font-mono text-[11px] ${selected ? 'text-wood-900' : 'text-muted-light'}`}>
                              {n > 0 ? `+${n}` : n}
                            </Text>
                          </AnimatedPressable>
                        )
                      })}
                    </View>

                    <View className="mt-3 flex-row flex-wrap items-center gap-2">
                      <AnimatedPressable haptic="light"
                        onPress={() => drill(lick)}
                        className="min-w-[100px] flex-1 rounded-lg bg-wood-700 px-3 py-2"
                        accessibilityRole="button"
                        accessibilityLabel="Practice this lick"
                      >
                        <Text className="text-center font-sans-medium text-sm text-amber-light">Practice</Text>
                      </AnimatedPressable>
                      <AnimatedPressable haptic="light"
                        onPress={() => listenToLick(lick)}
                        className="min-w-[100px] flex-1 rounded-lg border border-wood-600/45 bg-cream-dark/35 px-3 py-2"
                        accessibilityRole="button"
                        accessibilityLabel="Listen to this lick"
                      >
                        <Text className="text-center font-sans-medium text-sm text-wood-900">Listen</Text>
                      </AnimatedPressable>
                      <AnimatedPressable haptic="light"
                        onPress={() => confirmRemoveLick(lick)}
                        className="rounded-lg border border-danger/45 bg-wood-900/50 px-3 py-2"
                        accessibilityRole="button"
                        accessibilityLabel="Remove from library"
                      >
                        <Text className="font-sans-medium text-xs text-danger">Remove</Text>
                      </AnimatedPressable>
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
