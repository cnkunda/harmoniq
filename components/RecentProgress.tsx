import { useMemo } from 'react'
import { Text, View } from 'react-native'
import Animated, { FadeIn } from 'react-native-reanimated'
import Svg, { Polyline } from 'react-native-svg'

import colors from '@/src/constants/colors'
import type { PracticePlanCompletionRow, SessionJournalRow } from '@/src/db/types'
import { summaryFromPlanCompletionRow } from '@/src/home/planCompletionSummary'
import { sessionOverallAccuracy } from '@/src/home/sessionAccuracy'

const CHART_W = 268
const CHART_H = 52
const PAD = 6

export function RecentProgress({
  sessions,
  lastPlanCompletion,
}: {
  sessions: readonly SessionJournalRow[]
  /** Most recent row from `listPracticePlanCompletions()` (optional). */
  lastPlanCompletion?: PracticePlanCompletionRow | null
}) {
  // Sessions with accuracy scores for the chart
  const points = useMemo(() => {
    const chronological = [...sessions].slice(0, 3).reverse()
    return chronological
      .map((s) => sessionOverallAccuracy(s))
      .filter((v): v is number => v != null && Number.isFinite(v))
  }, [sessions])

  // Total session count for progress messaging (includes plan completions without accuracy)
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
    return `${head}${stepCount}-step plan finished`
  })()

  const completedCountMessage = totalSessions > 0
    ? `You've completed ${totalSessions} session${totalSessions === 1 ? '' : 's'}.`
    : null

  return (
    <View className="mb-2">
      <Text className="mb-2 font-sans-medium text-sm uppercase tracking-wider text-muted-brown">Recent sessions</Text>
      {points.length < 2 ? (
        <View>
          {completedCountMessage ? (
            <Text className="font-sans text-sm text-muted-brown mb-1">{completedCountMessage}</Text>
          ) : null}
          <Text className="font-sans text-sm text-muted-brown">
            Finish at least two sessions with review scores to see your accuracy trend here.
          </Text>
        </View>
      ) : (
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
              <Text key={`${i}-${p}`} className="font-sans text-[11px] text-muted-brown">
                {(p * 100).toFixed(0)}%
              </Text>
            ))}
          </View>
        </Animated.View>
      )}
      {planNote ? (
        <Text className="mt-2 font-sans text-xs text-muted-brown">Latest plan wrap-up: {planNote}.</Text>
      ) : null}
    </View>
  )
}
