import { useFocusEffect } from '@react-navigation/native'
import { LinearGradient } from 'expo-linear-gradient'
import { useRouter } from 'expo-router'
import {
  ChevronRight,
  ClipboardList,
  Clock,
  Library as LibraryIcon,
  Link2,
  Music,
  Play,
  Plus,
} from 'lucide-react-native'
import * as Linking from 'expo-linking'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Pressable, ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import {
  buildPlayerProfileFromSkillNodes,
  generatePracticePlan,
  loadLearningContextFromPrefs,
  parseTasteProfileJson,
} from '@/src/api/analyze'
import { AnimatedPressable } from '@/components/AnimatedPressable'
import { RecentProgress } from '@/components/RecentProgress'
import { TodaysPlanCard, TodaysPlanCardLoading } from '@/components/TodaysPlanCard'
import { WeakAreaPulse } from '@/components/WeakAreaPulse'
import { sessionEntryHref } from '@/src/constants/sessionFlow'
import { pickWeakAreaPulseNode } from '@/src/home/weakAreaPulseLogic'
import { usePlanStore } from '@/src/stores/planStore'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
import { useSkillStore } from '@/src/stores/skillStore'
import {
  getAllSkillNodes,
  getAppPref,
  getHomeSuggestion,
  getLessonByJobId,
  getLickById,
  listLessonsJournal,
  listPracticePlanCompletions,
  listSessionsJournal,
} from '@/src/db/client'
import { PREF_SPOTIFY_TASTE_PROFILE_JSON, PREF_TASTE_PROFILE_JSON } from '@/src/db/schema'
import type { HomeSuggestion, PracticePlanCompletionRow, SessionJournalRow } from '@/src/db/types'
import { startPracticePlanFromHome } from '@/src/session/practicePlanNavigation'
import { useLessonStore } from '@/src/stores/lessonStore'
import type { PracticePlanPayload } from '@/src/types'
import colors from '@/src/constants/colors'
import { startDemoSession } from '@/src/demo/startDemoSession'
import { runSpotifyConnect } from '@/src/spotify/connectSpotify'
import { spotifyTasteLooksPresent } from '@/src/taste/tasteQuizGate'
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
  const [sessionsLog, setSessionsLog] = useState<SessionJournalRow[]>([])
  const [latestPlanCompletion, setLatestPlanCompletion] = useState<PracticePlanCompletionRow | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [drillLatestError, setDrillLatestError] = useState<string | null>(null)
  const [practicePlan, setPracticePlan] = useState<PracticePlanPayload | null>(null)
  const [practicePlanLoading, setPracticePlanLoading] = useState(false)
  const [practicePlanStartError, setPracticePlanStartError] = useState<string | null>(null)
  const [planStartBusy, setPlanStartBusy] = useState(false)
  const [demoBusy, setDemoBusy] = useState(false)
  const [spotifyBusy, setSpotifyBusy] = useState(false)
  const [tasteSongHints, setTasteSongHints] = useState<string[]>([])
  const [spotifyLinked, setSpotifyLinked] = useState(false)

  const skillNodes = useSkillStore((s) => s.nodes)
  const loadSkills = useSkillStore((s) => s.loadFromDb)
  const weakPulseNode = useMemo(() => pickWeakAreaPulseNode(skillNodes), [skillNodes])

  const currentPlan = usePlanStore((s) => s.currentPlan)
  const planSlotIndex = usePlanStore((s) => s.currentSlotIndex)

  const planProgressFraction = useMemo(() => {
    if (!practicePlan?.slots?.length || !currentPlan?.slots?.length) return 0
    if (currentPlan.slots.length !== practicePlan.slots.length) return 0
    const a = currentPlan.slots[0]?.lesson_ref ?? currentPlan.slots[0]?.title ?? ''
    const b = practicePlan.slots[0]?.lesson_ref ?? practicePlan.slots[0]?.title ?? ''
    if (a !== b) return 0
    return Math.min(1, planSlotIndex / Math.max(1, currentPlan.slots.length))
  }, [practicePlan, currentPlan, planSlotIndex])

  const refresh = useCallback(() => {
    setLoadError(false)
    setDrillLatestError(null)
    setPracticePlanStartError(null)
    setPracticePlanLoading(true)
    void Promise.all([
      getHomeSuggestion(),
      listSessionsJournal(),
      listLessonsJournal(),
      getAllSkillNodes(),
      getAppPref(PREF_TASTE_PROFILE_JSON),
      getAppPref(PREF_SPOTIFY_TASTE_PROFILE_JSON),
      listPracticePlanCompletions(),
    ])
      .then(async ([homeSuggestion, sessions, lessons, skillRows, tasteRaw, spotifyRaw, planCompletions]) => {
        setSuggestion(homeSuggestion)
        setSessionsLog(sessions)
        setLatestPlanCompletion(planCompletions[0] ?? null)
        setLoadError(false)
        setSpotifyLinked(spotifyTasteLooksPresent(spotifyRaw))

        await useSkillStore.getState().loadFromDb()

        if (homeSuggestion?.kind === 'cold_start') {
          setPracticePlan(null)
          setPracticePlanLoading(false)
          return
        }

        const planState = usePlanStore.getState()
        const cachedPreview = planState.homePreviewPlan
        const hasMultiLessonLibrary = lessons.length >= 2
        const cachedIsFullSequencerPlan = (cachedPreview?.slots?.length ?? 0) === 4
        if (
          cachedPreview?.slots?.length &&
          !planState.isHomePreviewStale() &&
          (!hasMultiLessonLibrary || cachedIsFullSequencerPlan)
        ) {
          setPracticePlan(cachedPreview)
          setPracticePlanLoading(false)
          return
        }

        try {
          const taste = parseTasteProfileJson(tasteRaw)
          const learningCtx = await loadLearningContextFromPrefs()
          const profile = buildPlayerProfileFromSkillNodes(skillRows, taste, learningCtx)
          const libraryLessons = (
            await Promise.all(lessons.map((l) => getLessonByJobId(l.job_id)))
          ).filter((row): row is NonNullable<typeof row> => row != null)
          const plan = await generatePracticePlan({
            player_profile: profile,
            job_ids: lessons.map((l) => l.job_id),
            duration_minutes: 25,
            library_lessons: libraryLessons,
          })
          const next = plan.slots?.length ? plan : null
          setPracticePlan(next)
          if (next) {
            usePlanStore.getState().setHomePreviewPlan(next)
          }
        } catch (e) {
          console.warn('[home] practice plan unavailable', e)
          setPracticePlan(null)
        } finally {
          setPracticePlanLoading(false)
        }
      })
      .catch((e) => {
        console.error('[home] refresh failed', e)
        setLoadError(true)
        setSessionsLog([])
        setLatestPlanCompletion(null)
        setPracticePlanLoading(false)
        setSpotifyLinked(false)
      })
  }, [])

  useFocusEffect(
    useCallback(() => {
      refresh()
    }, [refresh]),
  )

  const goAnalyze = () => router.push('/add-song')
  const goSession = () => router.push(sessionEntryHref(useSessionPrefsStore.getState().skipTuneStep))
  const goLibrary = () => router.push('/library')

  const onStartDemoLesson = useCallback(() => {
    if (demoBusy) return
    setDemoBusy(true)
    void startDemoSession(router, saveLesson, setLessonSectionIndex)
      .then(() => refresh())
      .catch((e) => console.warn('[home] demo session', e))
      .finally(() => setDemoBusy(false))
  }, [demoBusy, refresh, router, saveLesson, setLessonSectionIndex])

  const onConnectSpotify = useCallback(() => {
    if (spotifyBusy) return
    setSpotifyBusy(true)
    void runSpotifyConnect({
      onProfile: () =>
        void loadSkills().then(() => {
          void refresh()
        }),
    }).finally(() => setSpotifyBusy(false))
  }, [spotifyBusy, refresh, loadSkills])

  useEffect(() => {
    if (suggestion?.kind !== 'cold_start') {
      setTasteSongHints([])
      return
    }
    void getAppPref(PREF_TASTE_PROFILE_JSON).then((raw) => {
      const t = parseTasteProfileJson(raw)
      const list = t?.song_candidates?.filter((s) => typeof s === 'string' && s.trim()) ?? []
      setTasteSongHints(list.slice(0, 8))
    })
  }, [suggestion])

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
      const duplicate = sessionsLog
        .slice(0, 2)
        .some((s) => s.song_title?.trim().toLowerCase() === analyzedTitle.toLowerCase())
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
    for (const session of sessionsLog.slice(0, 2)) {
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
  }, [goSession, lesson?.job_id, lesson?.song_title, lesson?.style_label, sessionsLog, router])

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

  const recommendedMinutes = useMemo(() => {
    if (practicePlan?.total_duration_seconds) {
      return Math.max(1, Math.round(practicePlan.total_duration_seconds / 60))
    }
    return 15
  }, [practicePlan])

  const durationBadge = (
    <View className="flex-row items-center gap-1 rounded-lg border border-wood-700 bg-wood-800/50 px-3 py-1.5">
      <Clock color="#8B7D6B" size={16} strokeWidth={2} />
      <Text className="font-sans text-sm text-muted-brown">~{recommendedMinutes} min</Text>
    </View>
  )

  const onStartPracticePlan = useCallback(() => {
    if (!practicePlan?.slots?.length) return
    setPracticePlanStartError(null)
    setPlanStartBusy(true)
    void startPracticePlanFromHome(router, { saveLesson, setLessonSectionIndex }, practicePlan)
      .catch((e) => {
        const msg = e instanceof Error ? e.message : 'Could not start this plan.'
        setPracticePlanStartError(msg)
      })
      .finally(() => setPlanStartBusy(false))
  }, [practicePlan, router, saveLesson, setLessonSectionIndex])

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

          <Text className="mb-4 font-sans-medium text-sm uppercase tracking-wider text-muted-brown">Your practice path</Text>

          <LinearGradient
            colors={['rgba(74, 55, 40, 0.98)', 'rgba(44, 24, 16, 0.99)']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            className="relative mb-6 overflow-hidden rounded-2xl border border-wood-600/50 shadow-soft-wood"
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
              ) : suggestion.kind === 'cold_start' ? (
                <View className="w-full max-w-md self-center">
                  {/* Matches onboarding welcome: icon, headline scale, readable measure */}
                  <View className="items-center">
                    <View className="h-16 w-16 items-center justify-center rounded-full border border-amber-accent/50">
                      <Music color={colors.amber.accent} size={28} strokeWidth={1.5} />
                    </View>
                    <Text className="mt-6 text-center font-serif text-2xl text-cream">Kick off your practice</Text>
                    <Text className="mt-4 max-w-sm text-center font-sans text-base leading-7 text-muted-brown">
                      Let's get your playing faster. Take a quick style quiz, try a demo session, add a song, or connect Spotify—whatever gets you playing first.
                    </Text>
                  </View>

                  {/* {tasteSongHints.length > 0 ? (
                    <View className="mt-6 w-full">
                      <Text className="mb-2 font-sans-medium text-[11px] uppercase tracking-wider text-muted-brown">
                        Ideas for your style (add as lessons)
                      </Text>
                      <View className="gap-2">
                        {tasteSongHints.map((hint) => (
                          <Pressable
                            key={hint}
                            onPress={() =>
                              void Linking.openURL(
                                `https://www.youtube.com/results?search_query=${encodeURIComponent(hint)}`,
                              )
                            }
                            className="rounded-lg border border-wood-600/40 bg-wood-800/25 px-3 py-2.5 active:opacity-90"
                            accessibilityRole="button"
                            accessibilityLabel={`Search YouTube for ${hint}`}
                          >
                            <Text className="font-sans text-sm text-cream">{hint}</Text>
                          </Pressable>
                        ))}
                      </View>
                      <Text className="mt-2 font-sans text-xs leading-5 text-muted-brown">
                        Pick a result, copy the link, then use Add song to turn it into tabs in Harmoniq.
                      </Text>
                    </View>
                  ) : null} */}

                  <View className="mt-8 w-full">
                    <Text className="mb-3 font-sans-medium text-[11px] uppercase tracking-wider text-muted-brown">
                      Get started
                    </Text>
                    <View className="gap-3">
                      <AnimatedPressable
                        onPress={() => router.push('/onboarding/taste-quiz')}
                        haptic="medium"
                        className="w-full flex-row items-center justify-center gap-2 rounded-lg bg-amber-accent px-4 py-3.5"
                        accessibilityRole="button"
                        accessibilityLabel="Open style quiz"
                      >
                        <ClipboardList color="#2C1810" size={20} strokeWidth={2} />
                        <Text className="font-sans-medium text-base text-wood-900">Style quiz</Text>
                      </AnimatedPressable>
                      <AnimatedPressable
                        onPress={() => void onStartDemoLesson()}
                        disabled={demoBusy}
                        haptic="light"
                        className="w-full flex-row items-center justify-center gap-2 rounded-lg border border-wood-600 bg-wood-800/60 px-4 py-3 disabled:opacity-50"
                        accessibilityRole="button"
                        accessibilityLabel="Play demo session"
                      >
                        <Play color={colors.amber.light} size={20} fill={colors.amber.light} strokeWidth={0} />
                        <Text className="font-sans-medium text-sm text-cream">
                          {demoBusy ? 'Opening…' : 'Play demo session'}
                        </Text>
                      </AnimatedPressable>
                    </View>
                  </View>

                  <View className="mt-7 w-full border-t border-wood-600/45 pt-5">
                    <Text className="mb-3 font-sans-medium text-[11px] uppercase tracking-wider text-muted-brown">
                      More ways to begin
                    </Text>
                    <View className="gap-2">
                      <Pressable
                        onPress={goAnalyze}
                        className="flex-row items-center gap-3 rounded-lg border border-wood-600/50 bg-wood-800/35 px-4 py-3.5 active:opacity-90"
                        accessibilityRole="button"
                        accessibilityLabel="Add a song"
                      >
                        <Plus color={colors.amber.light} size={20} strokeWidth={2} />
                        <Text className="flex-1 font-sans-medium text-sm text-cream">Add a song</Text>
                      </Pressable>
                      {spotifyLinked ? (
                        <Pressable
                          onPress={() => router.push('/(tabs)/settings')}
                          className="flex-row items-center gap-3 rounded-lg border border-wood-600/50 bg-wood-800/35 px-4 py-3.5 active:opacity-90"
                          accessibilityRole="button"
                          accessibilityLabel="Spotify connected, open Settings"
                        >
                          <Link2 color={colors.amber.light} size={20} strokeWidth={2} />
                          <Text className="flex-1 font-sans-medium text-sm text-cream">Spotify · Connected</Text>
                          <ChevronRight color={colors.amber.light} size={20} strokeWidth={2} />
                        </Pressable>
                      ) : (
                        <Pressable
                          onPress={onConnectSpotify}
                          disabled={spotifyBusy}
                          className="flex-row items-center gap-3 rounded-lg border border-wood-600/50 bg-wood-800/35 px-4 py-3.5 active:opacity-90 disabled:opacity-50"
                          accessibilityRole="button"
                          accessibilityLabel="Connect to Spotify"
                        >
                          <Link2 color={colors.amber.light} size={20} strokeWidth={2} />
                          <Text className="flex-1 font-sans-medium text-sm text-cream">
                            {spotifyBusy ? 'Connecting…' : 'Connect to Spotify'}
                          </Text>
                        </Pressable>
                      )}
                    </View>
                  </View>
                </View>
              ) : practicePlanLoading ? (
                <TodaysPlanCardLoading />
              ) : practicePlan?.slots?.length ? (
                <TodaysPlanCard
                  plan={practicePlan}
                  sessionMinutes={recommendedMinutes}
                  progressFraction={planProgressFraction}
                  onStart={() => void onStartPracticePlan()}
                  busy={planStartBusy}
                  errorText={practicePlanStartError}
                />
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
                  <AnimatedPressable
                    onPress={goSession}
                    haptic="medium"
                    className="flex-row items-center justify-center gap-2 self-stretch rounded-xl bg-amber-accent px-8 py-3.5 shadow-md sm:self-start"
                    accessibilityRole="button"
                    accessibilityLabel="Start session at Listen"
                  >
                    <Play color="#2C1810" size={20} fill="#2C1810" strokeWidth={0} />
                    <Text className="font-sans-medium text-base text-wood-900">Start session</Text>
                  </AnimatedPressable>
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
                  <AnimatedPressable
                    onPress={() => void drillLatestSavedLick()}
                    haptic="medium"
                    className="mb-3 flex-row items-center justify-center gap-2 self-stretch rounded-xl bg-amber-accent px-8 py-3.5 shadow-md sm:self-start"
                    accessibilityRole="button"
                    accessibilityLabel="Drill latest saved lick"
                  >
                    <Play color="#2C1810" size={20} fill="#2C1810" strokeWidth={0} />
                    <Text className="font-sans-medium text-base text-wood-900">Start Session</Text>
                  </AnimatedPressable>
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
                  <AnimatedPressable
                    onPress={goSession}
                    haptic="medium"
                    className="flex-row items-center justify-center gap-2 self-stretch rounded-xl bg-amber-accent px-8 py-3.5 shadow-md sm:self-start"
                    accessibilityRole="button"
                    accessibilityLabel="Start session at Listen"
                  >
                    <Play color="#2C1810" size={20} fill="#2C1810" strokeWidth={0} />
                    <Text className="font-sans-medium text-base text-wood-900">Start session</Text>
                  </AnimatedPressable>
                </>
              )}
            </View>
          </LinearGradient>

          {suggestion && suggestion.kind !== 'cold_start' && weakPulseNode ? <WeakAreaPulse node={weakPulseNode} /> : null}
          {suggestion && suggestion.kind !== 'cold_start' ? (
            <View className="mb-8">
              <RecentProgress sessions={sessionsLog.slice(0, 3)} lastPlanCompletion={latestPlanCompletion} />
            </View>
          ) : null}

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
