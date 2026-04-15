import { useFocusEffect } from '@react-navigation/native'
import { LinearGradient } from 'expo-linear-gradient'
import { useRouter } from 'expo-router'
import { Clock, Library as LibraryIcon, Play, Plus } from 'lucide-react-native'
import { useCallback, useMemo, useState } from 'react'
import { Pressable, ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { sessionHref } from '@/src/constants/sessionFlow'
import { getHomeSuggestion, getLickById, listSessionsJournal } from '@/src/db/client'
import type { HomeSuggestion, SessionJournalRow } from '@/src/db/types'
import { useLessonStore } from '@/src/stores/lessonStore'
import { lessonFromSavedLick } from '@/src/utils/lessonFromSavedLick'

function getGreeting(name?: string | null): string {
  const h = new Date().getHours()
  const base = h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
  const trimmed = name?.trim()
  return trimmed ? `${base}, ${trimmed}` : base
}

function focusLabelFromNodes(nodes: readonly string[]): string {
  if (!nodes.length) return 'Practice'
  return (nodes[0] ?? 'practice').replace(/_/g, ' ')
}

function toTitleCase(value: string): string {
  return value
    .toLowerCase()
    .replace(/\b([a-z])/g, (m) => m.toUpperCase())
}

function relativeDateLabel(input: unknown): string {
  const d =
    input instanceof Date
      ? input
      : typeof input === 'string' || typeof input === 'number'
        ? new Date(input)
        : new Date()
  if (Number.isNaN(d.getTime())) return 'Today'

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

export default function HomeScreen() {
  const router = useRouter()
  const displayName = 'Nkunda' // TODO(auth): Replace with signed-in profile name.
  const saveLesson = useLessonStore((s) => s.saveLesson)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)
  const lesson = useLessonStore((s) => s.lesson)
  const [suggestion, setSuggestion] = useState<HomeSuggestion | null>(null)
  const [recentSessions, setRecentSessions] = useState<SessionJournalRow[]>([])
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
    void listSessionsJournal()
      .then((rows) => setRecentSessions(rows.slice(0, 2)))
      .catch(() => setRecentSessions([]))
  }, [])

  useFocusEffect(
    useCallback(() => {
      refresh()
    }, [refresh]),
  )

  const goAnalyze = () => router.push('/add-song')
  const goSession = () => router.push(sessionHref('listen'))
  const goLibrary = () => router.push('/library')

  const recentItems = useMemo(() => {
    const out: Array<{
      id: string
      title: string
      focus: string
      dateLabel: string
      open: () => void
    }> = []
    const analyzedTitle = lesson?.song_title?.trim()
    if (analyzedTitle) {
      const duplicate = recentSessions.some((s) => s.song_title?.trim().toLowerCase() === analyzedTitle.toLowerCase())
      if (!duplicate) {
        out.push({
          id: `analysis-${lesson?.job_id ?? analyzedTitle}`,
          title: analyzedTitle,
          focus: toTitleCase(lesson?.style_label?.trim() || 'Ready to start session'),
          dateLabel: relativeDateLabel(
            (lesson as Record<string, unknown> | null)?.updated_at ??
              (lesson as Record<string, unknown> | null)?.created_at ??
              (lesson as Record<string, unknown> | null)?.analyzed_at ??
              (lesson as Record<string, unknown> | null)?.generated_at,
          ),
          open: goSession,
        })
      }
    }
    for (const session of recentSessions) {
      if (out.length >= 2) break
      out.push({
        id: session.id,
        title: session.song_title?.trim() ? session.song_title : 'Practice session',
        focus: toTitleCase(focusLabelFromNodes(session.nodes_targeted)),
        dateLabel: relativeDateLabel(session.date),
        open: () => router.push({ pathname: '/review-archive/[sessionId]', params: { sessionId: session.id } }),
      })
    }
    return out
  }, [goSession, lesson?.job_id, lesson?.song_title, lesson?.style_label, recentSessions, router])

  const drillLatestSavedLick = useCallback(async () => {
    if (suggestion?.kind !== 'library_saved') return
    setDrillLatestError(null)
    try {
      const row = await getLickById(suggestion.latest.id)
      if (!row) {
        setDrillLatestError('That save is no longer in your library. Open Library from the tab bar.')
        return
      }
      saveLesson(lessonFromSavedLick(row, 0))
      setLessonSectionIndex(0)
      router.push('/session/study')
    } catch {
      setDrillLatestError('Could not open your latest save.')
    }
  }, [router, saveLesson, setLessonSectionIndex, suggestion])

  const durationBadge = (
    <View className="flex-row items-center gap-1 rounded-lg border border-wood-700 bg-wood-800/50 px-3 py-1.5">
      <Clock color="#8B7D6B" size={16} strokeWidth={2} />
      <Text className="font-sans text-sm text-muted-brown">~15 min</Text>
    </View>
  )

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <ScrollView
        className="flex-1"
        contentContainerStyle={{ paddingBottom: 32 }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View className="w-full max-w-4xl self-center px-6 pb-8 pt-4">
          <View className="mb-10 mt-2">
            <Text className="mb-1 font-serif text-3xl text-cream">{getGreeting(displayName)}</Text>
            <Text className="font-sans text-base text-muted-brown">Ready to play?</Text>
          </View>

          <Text className="mb-4 font-sans-medium text-sm uppercase tracking-wider text-muted-brown">Recommended session</Text>

          <LinearGradient
            colors={['rgba(74, 55, 40, 0.98)', 'rgba(44, 24, 16, 0.99)']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            className="relative mb-12 overflow-hidden rounded-2xl border border-wood-600/50 shadow-soft-wood"
            style={{ elevation: 8 }}
          >
            <View className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-amber-accent/10" />
            <View className="relative z-10 p-6">
              {suggestion == null ? (
                loadError ? (
                  <View>
                    <Text className="font-sans text-sm text-cream">Could not load your suggestion.</Text>
                    <Pressable
                      onPress={refresh}
                      className="mt-4 rounded-xl border border-amber-accent/60 bg-wood-900/50 px-4 py-3"
                      accessibilityRole="button"
                      accessibilityLabel="Retry loading suggestion"
                    >
                      <Text className="text-center font-sans-medium text-amber-light">Retry</Text>
                    </Pressable>
                  </View>
                ) : (
                  <Text className="font-sans text-sm text-cream">Loading suggestion…</Text>
                )
              ) : suggestion.kind === 'active_lesson' ? (
                <>
                  <View className="mb-6 flex-row items-start justify-between">
                    <View className="flex-1 pr-3">
                      <Text className="mb-1 font-serif text-2xl text-cream">{suggestion.song.song_title}</Text>
                      {suggestion.song.artist ? (
                        <Text className="font-sans text-sm text-amber-light/80">{suggestion.song.artist}</Text>
                      ) : null}
                      {suggestion.song.section_label ? (
                        <Text className="mt-1 font-sans text-xs text-muted-brown">
                          Section: {suggestion.song.section_label}
                        </Text>
                      ) : null}
                    </View>
                    {durationBadge}
                  </View>
                  <View className="mb-6 rounded-xl border border-wood-700 bg-wood-800/60 p-4 shadow-inner-wood">
                    <Text className="font-sans text-sm italic leading-relaxed text-cream/90">
                      &ldquo;This song is ready in your workspace — start with Listen, then Study and Play when you&apos;re
                      warmed up.&rdquo;
                    </Text>
                  </View>
                  <Text className="mb-4 font-sans text-xs leading-5 text-muted-brown">
                    Full loop: Listen → Study → Slow → Play → Review (with stems). Use Library tab for saved licks only.
                  </Text>
                  <Pressable
                    onPress={goSession}
                    className="flex-row items-center justify-center gap-2 self-stretch rounded-xl bg-amber-accent px-8 py-3.5 shadow-md sm:self-start"
                    accessibilityRole="button"
                    accessibilityLabel="Start session at Listen"
                  >
                    <Play color="#2C1810" size={20} fill="#2C1810" strokeWidth={0} />
                    <Text className="font-sans-medium text-base text-wood-900">Start session</Text>
                  </Pressable>
                </>
              ) : suggestion.kind === 'cold_start' ? (
                <>
                  <View className="mb-6">
                    <Text className="font-serif text-2xl text-cream">Add your first song</Text>
                  </View>
                  <Pressable
                    onPress={goAnalyze}
                    className="flex-row items-center justify-center gap-2 self-stretch rounded-xl bg-amber-accent px-8 py-3.5 shadow-md sm:self-start"
                    accessibilityRole="button"
                    accessibilityLabel="Add a song"
                  >
                    <Plus color="#2C1810" size={20} strokeWidth={2} />
                    <Text className="font-sans-medium text-base text-wood-900">Add Song</Text>
                  </Pressable>
                </>
              ) : suggestion.kind === 'library_saved' ? (
                <>
                  <View className="mb-6 flex-row items-start justify-between">
                    <View className="flex-1 pr-3">
                      <Text className="mb-1 font-serif text-2xl text-cream">
                        {suggestion.latest.song_title?.trim() || 'Saved lick'}
                      </Text>
                      <Text className="font-sans text-sm text-amber-light/80">
                        {suggestion.latest.artist?.trim() || 'Your library'}
                      </Text>
                    </View>
                    {durationBadge}
                  </View>
                  <View className="mb-6 rounded-xl border border-wood-700 bg-wood-800/60 p-4 shadow-inner-wood">
                    <Text className="font-sans text-sm italic leading-relaxed text-cream/90">
                      &ldquo;
                      {suggestion.latest.coach_oneliner?.trim() ||
                        `You have ${suggestion.lickCount} saved ${suggestion.lickCount === 1 ? 'lick' : 'licks'} — drill the newest or add a full song for stems.`}
                      &rdquo;
                    </Text>
                  </View>
                  {drillLatestError ? (
                    <Text className="mb-3 font-sans text-sm text-danger">{drillLatestError}</Text>
                  ) : null}
                  <Pressable
                    onPress={() => void drillLatestSavedLick()}
                    className="mb-3 flex-row items-center justify-center gap-2 self-stretch rounded-xl bg-amber-accent px-8 py-3.5 shadow-md sm:self-start"
                    accessibilityRole="button"
                    accessibilityLabel="Drill latest saved lick"
                  >
                    <Play color="#2C1810" size={20} fill="#2C1810" strokeWidth={0} />
                    <Text className="font-sans-medium text-base text-wood-900">Start Session</Text>
                  </Pressable>
                  {/* <Pressable
                    onPress={goAnalyze}
                    className="self-stretch rounded-xl border border-wood-600/50 bg-cream-dark/15 px-4 py-3 sm:self-start"
                    accessibilityRole="button"
                    accessibilityLabel="Add a full song"
                  >
                    <Text className="text-center font-sans-medium text-cream">Add full song</Text>
                  </Pressable> */}
                </>
              ) : (
                <>
                  <View className="mb-6 flex-row items-start justify-between">
                    <View className="flex-1 pr-3">
                      <Text className="mb-1 font-serif text-2xl text-cream">{suggestion.song.song_title}</Text>
                      {suggestion.song.artist ? (
                        <Text className="font-sans text-sm text-amber-light/80">{suggestion.song.artist}</Text>
                      ) : null}
                      {suggestion.song.section_label ? (
                        <Text className="mt-1 font-sans text-xs text-muted-brown">
                          Last section: {suggestion.song.section_label}
                        </Text>
                      ) : null}
                    </View>
                    {durationBadge}
                  </View>
                  <View className="mb-6 rounded-xl border border-wood-700 bg-wood-800/60 p-4 shadow-inner-wood">
                    <Text className="font-sans text-sm italic leading-relaxed text-cream/90">
                      &ldquo;Focus on {suggestion.node.label ?? suggestion.node.id.replace(/_/g, ' ')} — next review{' '}
                      {suggestion.node.next_review_date ?? 'soon'}
                      {suggestion.node.interval_days != null ? ` · every ${suggestion.node.interval_days}d` : ''}.&rdquo;
                    </Text>
                  </View>
                  <Text className="mb-4 font-sans text-xs leading-5 text-muted-brown">
                    Full loop: Listen → Study → Slow → Play → Review (with stems). Use Library tab for saved licks only.
                  </Text>
                  <Pressable
                    onPress={goSession}
                    className="flex-row items-center justify-center gap-2 self-stretch rounded-xl bg-amber-accent px-8 py-3.5 shadow-md sm:self-start"
                    accessibilityRole="button"
                    accessibilityLabel="Start session at Listen"
                  >
                    <Play color="#2C1810" size={20} fill="#2C1810" strokeWidth={0} />
                    <Text className="font-sans-medium text-base text-wood-900">Start session</Text>
                  </Pressable>
                </>
              )}
            </View>
          </LinearGradient>

          <View className="flex-col gap-8">
            <View>
              <Text className="mb-3 font-sans-medium text-sm uppercase tracking-wider text-muted-brown">Recently added</Text>
              <View className="gap-2">
                {recentItems.length === 0 ? (
                  <Text className="font-sans text-sm text-muted-brown">No songs added yet.</Text>
                ) : (
                  recentItems.map((item) => (
                    <Pressable
                      key={item.id}
                      onPress={item.open}
                      className="flex-row items-center justify-between rounded-xl border border-wood-700/50 bg-wood-800/40 px-3 py-2.5 active:bg-wood-800/60"
                      accessibilityRole="button"
                      accessibilityLabel={`Open session ${item.title}`}
                    >
                      <View className="flex-1 pr-2">
                        <Text className="font-sans-medium text-[15px] text-cream">{item.title}</Text>
                        <Text className="mt-0.5 font-sans text-[11px] text-muted-brown">{item.focus}</Text>
                      </View>
                      <Text className="font-sans text-[11px] text-muted-brown">{item.dateLabel}</Text>
                    </Pressable>
                  ))
                )}
              </View>
            </View>

            <View>
              <Text className="mb-4 font-sans-medium text-sm uppercase tracking-wider text-muted-brown">Quick actions</Text>
              <View className="flex-row gap-3">
                <Pressable
                  onPress={goAnalyze}
                  className="min-h-[128px] flex-1 items-center justify-center gap-3 rounded-xl border border-wood-700/50 bg-wood-800/40 py-4 active:bg-wood-700/50"
                  accessibilityRole="button"
                  accessibilityLabel="Add a song"
                >
                  <View className="h-10 w-10 items-center justify-center rounded-full bg-wood-700">
                    <Plus color="#E8B86D" size={20} strokeWidth={2} />
                  </View>
                  <Text className="text-center font-sans-medium text-sm text-cream">Add Song</Text>
                </Pressable>
                <Pressable
                  onPress={goLibrary}
                  className="min-h-[128px] flex-1 items-center justify-center gap-3 rounded-xl border border-wood-700/50 bg-wood-800/40 py-4 active:bg-wood-700/50"
                  accessibilityRole="button"
                  accessibilityLabel="Open library"
                >
                  <View className="h-10 w-10 items-center justify-center rounded-full bg-wood-700">
                    <LibraryIcon color="#E8B86D" size={20} strokeWidth={2} />
                  </View>
                  <Text className="text-center font-sans-medium text-sm text-cream">Open Library</Text>
                </Pressable>
              </View>
            </View>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  )
}
