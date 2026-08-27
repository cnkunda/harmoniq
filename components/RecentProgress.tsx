import { useRouter } from 'expo-router'
import { useCallback, useMemo } from 'react'
import { Text, View } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'
import Animated, { FadeIn } from 'react-native-reanimated'
import Svg, { Polyline } from 'react-native-svg'

import { toast } from '@/components/ToastConfig'
import colors from '@/src/constants/colors'
import { getLessonByJobId } from '@/src/db/client'
import type { PracticePlanCompletionRow, SessionJournalRow } from '@/src/db/types'
import { summaryFromPlanCompletionRow } from '@/src/home/planCompletionSummary'
import { sessionOverallAccuracy } from '@/src/home/sessionAccuracy'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'

const CHART_W = 268
const CHART_H = 52
const PAD = 6

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

function sessionCardTitle(s: SessionJournalRow): string {
  if (s.song_title?.trim()) return s.song_title.trim()
  if (s.section_label?.trim()) return s.section_label.trim()
  return 'Practice session'
}

function sessionCardSubtitle(s: SessionJournalRow): string {
  const parts: string[] = []
  if (s.artist?.trim()) parts.push(s.artist.trim())
  if (s.nodes_targeted?.length) {
    const labels = s.nodes_targeted.slice(0, 2).map((n) => n.replace(/_/g, ' '))
    parts.push(labels.join(', '))
  }
  if (s.duration_min) parts.push(`${s.duration_min} min`)
  return parts.join(' · ') || 'Completed session'
}

export function RecentProgress({
  sessions,
  lastPlanCompletion,
}: {
  sessions: readonly SessionJournalRow[]
  lastPlanCompletion?: PracticePlanCompletionRow | null
}) {
  const router = useRouter()
  const saveLesson = useLessonStore((s) => s.saveLesson)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)

  const points = useMemo(() => {
    const chronological = [...sessions].slice(0, 3).reverse()
    return chronological
      .map((s) => sessionOverallAccuracy(s))
      .filter((v): v is number => v != null && Number.isFinite(v))
  }, [sessions])

  const totalSessions = sessions.length

  const polyline = useMemo(() => {
    if (points.length < 2) return null
    const minV = Math.min(...points, 0)
    const maxV = Math.max(...points, 1)
    const span = Math.max(0.05, maxV - minV)
    const innerW = CHART_W - PAD * 2
    const innerH = CHART_H - PAD * 2
    const coords = points.map((v, i) => {
      const x = PAD + (innerW * i) / Math.max(1, points.length - 1)
      const yn = (v - minV) / span
      const y = PAD + innerH * (1 - yn)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    return coords.join(' ')
  }, [points])

  const planNote = (() => {
    if (!lastPlanCompletion) return null
    const { stepCount, firstTitle } = summaryFromPlanCompletionRow(lastPlanCompletion)
    if (stepCount <= 0) return null
    const head = firstTitle ? `${firstTitle} · ` : ''
    return `${head}${stepCount}-section plan finished`
  })()

  const openSession = useCallback(
    async (s: SessionJournalRow) => {
      if (!s.job_id) return
      try {
        const fullLesson = await getLessonByJobId(s.job_id)
        if (!fullLesson) {
          toast.error('Song not found. Try opening from Library.')
          return
        }
        saveLesson(fullLesson)
        setLessonSectionIndex(Math.max(0, s.section_index ?? 0))
        const skipTune = useSessionPrefsStore.getState().skipTuneStep
        router.replace(skipTune ? '/session/listen' : '/session/tune')
      } catch {
        toast.error('Could not open session.')
      }
    },
    [router, saveLesson, setLessonSectionIndex],
  )

  const showChart = points.length >= 2

  return (
    <View className="mb-2">
      <Text className="mb-2 font-sans-medium text-sm uppercase tracking-wider text-muted-light">
        Recently completed
      </Text>

      {showChart ? (
        <Animated.View entering={FadeIn.duration(320)}>
          <Svg width={CHART_W} height={CHART_H} viewBox={`0 0 ${CHART_W} ${CHART_H}`}>
            <Polyline
              points={polyline ?? ''}
              fill="none"
              stroke={colors.amber.accent}
              strokeWidth={2.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </Svg>
          <View className="mt-1 flex-row justify-between px-1">
            {points.map((p, i) => (
              <Text key={`${i}-${p}`} className="font-sans text-[11px] text-muted-light">
                {(p * 100).toFixed(0)}%
              </Text>
            ))}
          </View>
        </Animated.View>
      ) : null}

      {totalSessions > 0 ? (
        <View className="gap-2">
        <Text className="font-sans text-sm text-muted-light">
          No completed sessions yet.
        </Text>
          {sessions.slice(0, 5).map((s) => (
            <AnimatedPressable
              key={s.id}
              haptic="light"
              onPress={() => void openSession(s)}
              disabled={!s.job_id}
              className="flex-row items-center justify-between rounded-xl border border-wood-700/50 bg-wood-800/40 px-3 py-2.5 active:bg-wood-800/60"
              accessibilityRole="button"
              accessibilityLabel={`Open session ${sessionCardTitle(s)}`}
            >
              <View className="flex-1 pr-2">
                <Text className="font-sans-medium text-[15px] text-cream">{sessionCardTitle(s)}</Text>
                <Text className="mt-0.5 font-sans text-[11px] text-muted-light">{sessionCardSubtitle(s)}</Text>
              </View>
              <Text className="font-sans text-[11px] text-muted-light">{relativeDateLabel(s.date)}</Text>
            </AnimatedPressable>
          ))}
        </View>
      ) : (
        <Text className="font-sans text-sm text-muted-light">
          No completed sessions yet.
        </Text>
      )}

      {planNote ? (
        <Text className="mt-2 font-sans text-xs text-muted-light">
          Latest plan wrap-up: {planNote}.
        </Text>
      ) : null}
    </View>
  )
}
