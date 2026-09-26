import { useFocusEffect } from '@react-navigation/native'
import { LinearGradient } from 'expo-linear-gradient'
import { useRouter, type Href } from 'expo-router'
import {
  ChevronRight,
  Clock,
  Headphones,
  Library as LibraryIcon,
  Link2,
  ListMusic,
  Music,
  Play,
  Plus,
  X
} from 'lucide-react-native'
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import Svg, { Circle as SvgCircle, Line as SvgLine, Polygon as SvgPolygon } from 'react-native-svg'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { RecentProgress } from '@/components/RecentProgress'
import { toast } from '@/components/ToastConfig'
import { TodaysPlanCard, TodaysPlanCardLoading } from '@/components/TodaysPlanCard'
import { WeakAreaPulse } from '@/components/WeakAreaPulse'
import {
  buildPlayerProfileFromSkillNodes,
  generatePracticePlan,
  loadLearningContextFromPrefs,
  parseTasteProfileJson,
} from '@/src/api/analyze'
import colors from '@/src/constants/colors'
import { sessionEntryHrefWithMoodCheck } from '@/src/constants/sessionFlow'
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
import { PREF_MOOD_CHECK_LAST_MOOD, PREF_SPOTIFY_TASTE_PROFILE_JSON, PREF_TASTE_PROFILE_JSON } from '@/src/db/schema'
import type { HomeSuggestion, LessonListRow, PracticePlanCompletionRow, SessionJournalRow } from '@/src/db/types'
import { startDemoSession } from '@/src/demo/startDemoSession'
import {
  dismissDailyLick,
  getDailyLick,
  isDailyLickDismissed,
  persistDailyLick,
  type DailyLick,
} from '@/src/home/dailyLick'
import { pickWeakAreaPulseNode } from '@/src/home/weakAreaPulseLogic'
import { startPracticePlanFromHome } from '@/src/session/practicePlanNavigation'
import { runSpotifyConnect } from '@/src/spotify/connectSpotify'
import { useLessonStore } from '@/src/stores/lessonStore'
import { usePlanStore } from '@/src/stores/planStore'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
import { useSkillStore } from '@/src/stores/skillStore'
import { spotifyTasteLooksPresent } from '@/src/taste/tasteQuizGate'
import type { PracticePlanPayload } from '@/src/types'
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

const STRING_YS = [15, 37, 59, 81, 103, 125]

interface FretCell {
  string: number
  fret: number
  variant: 'primary' | 'secondary'
}

function DailyLickFretboard({ cells, caption: captionProp }: { cells: readonly FretCell[]; caption?: string | null }) {
  const sorted = useMemo(() => [...cells].sort((a, b) => a.fret - b.fret || a.string - b.string), [cells])

  const minFret = useMemo(() => Math.min(...cells.map((c) => c.fret), 0), [cells])
  const maxFret = useMemo(() => Math.max(...cells.map((c) => c.fret), 4), [cells])
  const fretSpan = useMemo(() => Math.max(maxFret - minFret, 3), [maxFret, minFret])

  function fretToX(fret: number): number {
    return 40 + ((fret - minFret) / fretSpan) * 480
  }

  function dotX(fret: number): number {
    if (fret <= 0) return fretToX(-0.5)
    return (fretToX(fret - 1) + fretToX(fret)) / 2
  }

  function stringToY(string: number): number {
    return STRING_YS[6 - string]
  }

  const groups = useMemo(() => {
    if (!sorted.length) return [] as FretCell[][]
    const result: FretCell[][] = [[sorted[0]]]
    for (let i = 1; i < sorted.length; i++) {
      if (sorted[i].fret - sorted[i - 1].fret > 3) {
        result.push([sorted[i]])
      } else {
        result[result.length - 1].push(sorted[i])
      }
    }
    return result
  }, [sorted])

  const GROUP_COLORS = [colors.amber.accent, colors.ember, '#e8bd7e', '#5a3f2d']

  const connectors = useMemo(() => {
    const result: { fromX: number; toX: number; y: number }[] = []
    for (let i = 0; i < groups.length - 1; i++) {
      const g1maxX = Math.max(...groups[i].map((c) => dotX(c.fret)))
      const g2minX = Math.min(...groups[i + 1].map((c) => dotX(c.fret)))
      const midY1 = groups[i].reduce((sum, c) => sum + stringToY(c.string), 0) / groups[i].length
      const midY2 = groups[i + 1].reduce((sum, c) => sum + stringToY(c.string), 0) / groups[i + 1].length
      result.push({ fromX: g1maxX + 10, toX: g2minX - 10, y: (midY1 + midY2) / 2 })
    }
    return result
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups, minFret, maxFret, fretSpan])

  if (!cells.length) return null

  const displayCaption = captionProp ?? 'Position shifts left to right'

  return (
    <View className="mb-3 w-full">
      <Svg width="100%" height={130} viewBox="0 0 560 130" preserveAspectRatio="xMidYMid meet">
        {/* Nut line at left edge */}
        <SvgLine x1={20} y1={15} x2={20} y2={125} stroke={colors.cream} opacity={0.3} strokeWidth={2} />

        {/* Fret lines at each integer fret boundary */}
        {Array.from({ length: fretSpan + 1 }).map((_, fi) => {
          const x = fretToX(minFret + fi)
          return (
            <SvgLine key={`f${fi}`} x1={x} y1={15} x2={x} y2={125} stroke={colors.hairline} opacity={0.35} strokeWidth={0.6} />
          )
        })}

        {/* Six string lines */}
        {STRING_YS.map((y, si) => (
          <SvgLine key={`s${si}`} x1={20} y1={y} x2={540} y2={y} stroke={colors.hairline} strokeWidth={si === 0 || si === 5 ? 0.6 : 0.4} />
        ))}

        {/* Dots per group, each group gets a distinct color */}
        {groups.map((group, gi) => (
          <React.Fragment key={`g${gi}`}>
            {group.map((cell, di) => (
              <SvgCircle
                key={`d${gi}-${di}`}
                cx={dotX(cell.fret)}
                cy={stringToY(cell.string)}
                r={5}
                fill={GROUP_COLORS[gi % GROUP_COLORS.length]}
                opacity={cell.variant === 'primary' ? 0.95 : 0.55}
              />
            ))}
          </React.Fragment>
        ))}

        {/* Arrows between groups */}
        {connectors.map((c, i) => (
          <React.Fragment key={`a${i}`}>
            <SvgLine x1={c.fromX} y1={c.y} x2={c.toX} y2={c.y} stroke={colors.ember} strokeWidth={2} />
            <SvgPolygon points={`${c.toX},${c.y - 5} ${c.toX + 8},${c.y} ${c.toX},${c.y + 5}`} fill={colors.ember} />
          </React.Fragment>
        ))}
      </Svg>
      <Text className="mt-1 text-center font-mono text-[10px] text-muted2">{displayCaption}</Text>
    </View>
  )
}

function DifficultyDots({ level }: { level: number }) {
  return (
    <View className="flex-row items-center gap-1">
      {Array.from({ length: 5 }).map((_, i) => (
        <View
          key={i}
          className={`h-1.5 w-1.5 rounded-full ${i < level ? 'bg-amber-accent' : 'bg-hairline'}`}
        />
      ))}
    </View>
  )
}

export default function HomeScreen() {
  const router = useRouter()
  const displayName = 'Nkunda' // TODO(auth): Replace with signed-in profile name.
  const saveLesson = useLessonStore((s) => s.saveLesson)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)
  const lesson = useLessonStore((s) => s.lesson)
  const [suggestion, setSuggestion] = useState<HomeSuggestion | null>(null)
  const [sessionsLog, setSessionsLog] = useState<SessionJournalRow[]>([])
  const [lessons, setLessons] = useState<LessonListRow[]>([])
  const [latestPlanCompletion, setLatestPlanCompletion] = useState<PracticePlanCompletionRow | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [drillLatestError, setDrillLatestError] = useState<string | null>(null)
  const [dailyLick, setDailyLick] = useState<DailyLick | null>(null)
  const [dailyLickDismissed, setDailyLickDismissed] = useState(false)
  const [lickDateOffset, setLickDateOffset] = useState(0)
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

  const validPlanSlotIndex = useMemo(() => {
    if (!practicePlan?.slots?.length || !currentPlan?.slots?.length) return 0
    if (currentPlan.slots.length !== practicePlan.slots.length) return 0
    const a = currentPlan.slots[0]?.lesson_ref ?? currentPlan.slots[0]?.title ?? ''
    const b = practicePlan.slots[0]?.lesson_ref ?? practicePlan.slots[0]?.title ?? ''
    if (a !== b) return 0
    return Math.min(planSlotIndex, currentPlan.slots.length - 1)
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
        setLessons(lessons)
        setLatestPlanCompletion(planCompletions[0] ?? null)
        setLoadError(false)
        setSpotifyLinked(spotifyTasteLooksPresent(spotifyRaw))

        await useSkillStore.getState().loadFromDb()

        // B7: daily lick — deterministic Slonimsky pattern
        try {
          const lickDate = new Date()
          lickDate.setDate(lickDate.getDate() + lickDateOffset)
          const lick = getDailyLick(lickDate)
          const dismissed = await isDailyLickDismissed(lickDate)
          setDailyLick(lick)
          setDailyLickDismissed(dismissed)
          if (!dismissed) {
            void persistDailyLick(lickDate)
          }
        } catch {
          setDailyLick(null)
          setDailyLickDismissed(true)
        }

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
          const moodRaw = ((await getAppPref(PREF_MOOD_CHECK_LAST_MOOD)) ?? '').trim()
          const mood =
            moodRaw === 'focused' || moodRaw === 'loose' || moodRaw === 'tired' || moodRaw === 'on_fire'
              ? moodRaw
              : undefined
          const libraryLessons = (
            await Promise.all(lessons.map((l) => getLessonByJobId(l.job_id)))
          ).filter((row): row is NonNullable<typeof row> => row != null)
          const plan = await generatePracticePlan({
            player_profile: profile,
            job_ids: lessons.map((l) => l.job_id),
            duration_minutes: 25,
            mood,
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
  }, [lickDateOffset])

  useFocusEffect(
    useCallback(() => {
      refresh()
    }, [refresh]),
  )

  const goAnalyze = () => router.push('/add-song')
  const goSession = () => {
    void sessionEntryHrefWithMoodCheck(useSessionPrefsStore.getState().skipTuneStep).then((href) =>
      router.push(href as Href),
    )
  }
  const goLibrary = () => router.push('/library')
  const goListening = () => router.push('/(tabs)/discover')

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
    const sortedLessons = [...lessons].sort((a, b) => {
      const dateA = new Date(a.analyzed_at).getTime()
      const dateB = new Date(b.analyzed_at).getTime()
      return dateB - dateA
    })
    for (const lessonRow of sortedLessons.slice(0, 3)) {
      if (!lessonRow.song_title?.trim()) continue
      out.push({
        id: lessonRow.job_id,
        title: lessonRow.song_title,
        focus: lessonRow.artist?.trim() ? `${lessonRow.artist} · ${lessonRow.section_count} section${lessonRow.section_count !== 1 ? 's' : ''}` : `${lessonRow.section_count} section${lessonRow.section_count !== 1 ? 's' : ''}`,
        dateLabel: relativeDateLabel(lessonRow.analyzed_at),
        open: async () => {
          try {
            const fullLesson = await getLessonByJobId(lessonRow.job_id)
            if (!fullLesson) {
              toast.error('Song not found. Try opening from Library.')
              return
            }
            saveLesson(fullLesson)
            setLessonSectionIndex(0)
            const skipTune = useSessionPrefsStore.getState().skipTuneStep
            router.replace(skipTune ? '/session/listen' : '/session/tune')
          } catch {
            toast.error('Could not open song.')
          }
        },
      })
    }
    return out
  }, [lessons, router, saveLesson, setLessonSectionIndex])

  const startDailyLick = useCallback(async () => {
    if (!dailyLick) return
    try {
      const plan: PracticePlanPayload = {
        slots: [
          {
            slot_type: 'warmup',
            duration_seconds: dailyLick.pattern.defaultDurationSeconds,
            title: dailyLick.name,
            coach_intro: dailyLick.description,
            warmup_plan: {
              exercises: [
                {
                  name: dailyLick.name,
                  description: dailyLick.description,
                  duration_seconds: dailyLick.pattern.defaultDurationSeconds,
                  technique_tag: dailyLick.pattern.techniqueTags[0] ?? 'finger_independence',
                  bpm: 80,
                  fretboard_guide: {
                    cells: dailyLick.pattern.fretboardCells,
                    caption: dailyLick.pattern.caption ?? null,
                  },
                },
              ],
              total_duration_seconds: dailyLick.pattern.defaultDurationSeconds,
            },
          },
        ],
        total_duration_seconds: dailyLick.pattern.defaultDurationSeconds,
      }
      usePlanStore.getState().setPlan(plan)
      router.push('/session/warmup')
    } catch {
      toast.error('Could not start daily lick.')
    }
  }, [dailyLick, router])

  const onDismissDailyLick = useCallback(async () => {
    try {
      await dismissDailyLick()
      setDailyLickDismissed(true)
    } catch {
      console.log('[DailyLick] dismiss failed')
    }
  }, [])

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
      <Clock color={colors.muted.brown} size={16} strokeWidth={2} />
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

          {/* <Text className="mb-4 font-sans-medium text-sm uppercase tracking-wider text-muted-brown">Your practice path</Text> */}

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
                     <AnimatedPressable
                       onPress={refresh}
                       className="mt-4 rounded-xl border border-amber-accent/60 bg-wood-900/50 px-4 py-3"
                       accessibilityRole="button"
                       accessibilityLabel="Retry loading suggestion"
                     >
                       <Text className="text-center font-sans-medium text-amber-light">Retry</Text>
                     </AnimatedPressable>
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
                      Take a style quiz, try a demo session, add a song, or connect to your Spotify.
                    </Text>
                  </View>

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
                        <ListMusic color={colors.wood[900]} size={20} strokeWidth={2} />
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
                       <AnimatedPressable
                         onPress={goAnalyze}
                         className="flex-row items-center gap-3 rounded-lg border border-wood-600/50 bg-wood-800/35 px-4 py-3.5 active:opacity-90"
                         accessibilityRole="button"
                         accessibilityLabel="Add a song"
                       >
                         <Plus color={colors.amber.light} size={20} strokeWidth={2} />
                         <Text className="flex-1 font-sans-medium text-sm text-cream">Add a song</Text>
                       </AnimatedPressable>
                       {spotifyLinked ? (
                         <AnimatedPressable
                           onPress={() => router.push('/(tabs)/settings')}
                           className="flex-row items-center gap-3 rounded-lg border border-wood-600/50 bg-wood-800/35 px-4 py-3.5 active:opacity-90"
                           accessibilityRole="button"
                           accessibilityLabel="Spotify connected, open Settings"
                         >
                           <Link2 color={colors.amber.light} size={20} strokeWidth={2} />
                           <Text className="flex-1 font-sans-medium text-sm text-cream">Spotify · Connected</Text>
                           <ChevronRight color={colors.amber.light} size={20} strokeWidth={2} />
                         </AnimatedPressable>
                       ) : (
                         <AnimatedPressable
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
                         </AnimatedPressable>
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
                  currentSlotIndex={validPlanSlotIndex}
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
                    <Play color={colors.wood[900]} size={20} fill={colors.wood[900]} strokeWidth={0} />
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
                    accessibilityLabel="Practice latest saved lick"
                  >
                    <Play color={colors.wood[900]} size={20} fill={colors.wood[900]} strokeWidth={0} />
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
                    <Play color={colors.wood[900]} size={20} fill={colors.wood[900]} strokeWidth={0} />
                    <Text className="font-sans-medium text-base text-wood-900">Start session</Text>
                  </AnimatedPressable>
                </>
              )}
            </View>
          </LinearGradient>

          {dailyLick && !dailyLickDismissed && suggestion && suggestion.kind !== 'cold_start' ? (
            <View className="relative mb-6 overflow-hidden rounded-2xl border border-hairline bg-wood-800/40">
              <AnimatedPressable
                onPress={() => void startDailyLick()}
                haptic="light"
                accessibilityRole="button"
                accessibilityLabel="Start daily lick"
              >
                <View className="p-5">
                  <Text className="mb-1 font-sans-medium text-[11px] uppercase tracking-wider text-amber-accent/80">
                    Daily Lick
                  </Text>
                  <Text className="mb-2 font-serif text-xl text-cream">{dailyLick.name}</Text>
                  <Text className="mb-3 font-sans text-sm italic leading-relaxed text-cream/80">
                    &ldquo;{dailyLick.description}&rdquo;
                  </Text>
                  <DailyLickFretboard cells={dailyLick.pattern.fretboardCells} caption={dailyLick.pattern.caption} />
                  <View className="flex-row flex-wrap items-center gap-2">
                    <View className="flex-row items-center gap-2 rounded-full border border-hairline bg-wood-800/55 px-2.5 py-1">
                      <DifficultyDots level={dailyLick.pattern.difficulty} />
                    </View>
                    {dailyLick.pattern.techniqueTags.map((tag) => (
                      <View
                        key={tag}
                        className="rounded-full border border-hairline bg-wood-700/40 px-2.5 py-1"
                      >
                        <Text className="font-sans text-xs text-muted-brown">
                          {tag.replace(/_/g, ' ')}
                        </Text>
                      </View>
                    ))}
                  </View>
                </View>
              </AnimatedPressable>
              <View className="absolute right-3 top-3 z-10 flex-row items-center gap-1.5">
                <View className="h-7 w-7 items-center justify-center rounded-full bg-wood-900/70">
                  <AnimatedPressable
                    onPress={() => setLickDateOffset((p) => p + 1)}
                    accessibilityRole="button"
                    accessibilityLabel="Next lick"
                  >
                    <ChevronRight color={colors.amber.accent} size={14} strokeWidth={2.5} />
                  </AnimatedPressable>
                </View>
                <View className="h-7 w-7 items-center justify-center rounded-full bg-wood-900/70">
                  <AnimatedPressable
                    onPress={() => void onDismissDailyLick()}
                    accessibilityRole="button"
                    accessibilityLabel="Dismiss daily lick"
                  >
                    <X color={colors.amber.accent} size={14} strokeWidth={2.5} />
                  </AnimatedPressable>
                </View>
              </View>
            </View>
          ) : null}

          {suggestion && suggestion.kind !== 'cold_start' && weakPulseNode ? <WeakAreaPulse node={weakPulseNode} /> : null}
          <View className="mb-8">
            <RecentProgress sessions={sessionsLog.slice(0, 5)} lastPlanCompletion={latestPlanCompletion} />
          </View>

          <View className="flex-col gap-8">
            <View>
              <Text className="mb-3 font-sans-medium text-sm uppercase tracking-wider text-muted-brown">Recently uploaded</Text>
              <View className="gap-2">
                {recentItems.length === 0 ? (
                  <Text className="font-sans text-sm text-muted-brown">Add a song or finish a session and it&apos;ll show up here.</Text>
                 ) : (
                   recentItems.map((item) => (
                     <AnimatedPressable
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
                     </AnimatedPressable>
                  ))
                )}
              </View>
            </View>

            <View>
              <Text className="mb-4 font-sans-medium text-sm uppercase tracking-wider text-muted-brown">Quick actions</Text>
               <View className="flex-row flex-wrap gap-3">
                  <AnimatedPressable
                    onPress={goAnalyze}
                    className="min-h-[128px] min-w-[148] flex-1 items-center justify-center gap-3 rounded-xl border border-wood-700/50 bg-wood-800/40 px-4 py-5 active:bg-wood-700/50"
                    accessibilityRole="button"
                    accessibilityLabel="Add a song"
                  >
                    <View className="h-12 w-12 items-center justify-center rounded-full bg-wood-700">
                      <Plus color={colors.amber.light} size={22} strokeWidth={2} />
                    </View>
                    <Text className="text-center font-sans-medium text-sm text-cream">Add Song</Text>
                  </AnimatedPressable>
                  <AnimatedPressable
                    onPress={goLibrary}
                    className="min-h-[128px] min-w-[148] flex-1 items-center justify-center gap-3 rounded-xl border border-wood-700/50 bg-wood-800/40 px-4 py-5 active:bg-wood-700/50"
                    accessibilityRole="button"
                    accessibilityLabel="Open library"
                  >
                    <View className="h-12 w-12 items-center justify-center rounded-full bg-wood-700">
                      <LibraryIcon color={colors.amber.light} size={22} strokeWidth={2} />
                    </View>
                    <Text className="text-center font-sans-medium text-sm text-cream">Open Library</Text>
                  </AnimatedPressable>
                  <AnimatedPressable
                    onPress={goListening}
                    className="min-h-[128px] min-w-[148px] flex-1 items-center justify-center gap-3 rounded-xl border border-wood-700/50 bg-wood-800/40 px-4 py-5 active:bg-wood-700/50"
                    accessibilityRole="button"
                    accessibilityLabel="Open mic"
                  >
                    <View className="h-12 w-12 items-center justify-center rounded-full bg-wood-700">
                      <Headphones color={colors.amber.light} size={22} strokeWidth={2} />
                    </View>
                    <Text className="text-center font-sans-medium text-sm text-cream">Open Mic</Text>
                  </AnimatedPressable>
                  <AnimatedPressable
                    onPress={() => router.push('/scale-explorer' as any)}
                    className="min-h-[128px] min-w-[148px] flex-1 items-center justify-center gap-3 rounded-xl border border-wood-700/50 bg-wood-800/40 px-4 py-5 active:bg-wood-700/50"
                    accessibilityRole="button"
                    accessibilityLabel="Scale Explorer"
                  >
                    <View className="h-12 w-12 items-center justify-center rounded-full bg-wood-700">
                      <Music color={colors.amber.light} size={22} strokeWidth={2} />
                    </View>
                    <Text className="text-center font-sans-medium text-sm text-cream">Scales</Text>
                  </AnimatedPressable>
                </View>
            </View>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  )
}
