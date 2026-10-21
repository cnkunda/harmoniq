import { useRouter } from 'expo-router'
import { BarChart3, CalendarDays, ChevronLeft, Clock, Music, Target } from 'lucide-react-native'
import { useEffect, useMemo, useState } from 'react'
import { ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { toast } from '@/components/ToastConfig'
import { emit, flushAnalytics } from '@/src/analytics/eventBus'
import { computeEngagementMetrics, type EngagementMetrics } from '@/src/analytics/metrics'
import { colors } from '@/src/constants/colors'
import { getUserFeedbackStats, listAnalyticsEvents } from '@/src/db/client'
import type { AnalyticsEventRow, UserFeedbackStats } from '@/src/db/types'

const EMPTY_FEEDBACK_STATS: UserFeedbackStats = {
  total: 0,
  chord_corrections: 0,
  note_corrections: 0,
  wrong_chords: 0,
  most_corrected_chords: [],
}

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return '0s'
  const rounded = Math.round(seconds)
  if (rounded < 60) return `${rounded}s`
  const minutes = Math.floor(rounded / 60)
  const remainder = rounded % 60
  if (minutes < 60) return remainder > 0 ? `${minutes}m ${remainder}s` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const leftoverMinutes = minutes % 60
  return leftoverMinutes > 0 ? `${hours}h ${leftoverMinutes}m` : `${hours}h`
}

function formatPercent(rate: number): string {
  if (!Number.isFinite(rate)) return '0%'
  return `${Math.round(rate * 100)}%`
}

function formatDayLabel(dateKey: string): string {
  const [year, month, day] = dateKey.split('-').map(Number)
  if (!year || !month || !day) return dateKey
  return new Date(year, month - 1, day).toLocaleDateString(undefined, { weekday: 'short' })
}

export default function PracticeInsightsScreen() {
  const router = useRouter()
  const [events, setEvents] = useState<AnalyticsEventRow[]>([])
  const [feedbackStats, setFeedbackStats] = useState<UserFeedbackStats>(EMPTY_FEEDBACK_STATS)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      await flushAnalytics().catch((e) => {
        console.warn('[insights] analytics flush skipped', e instanceof Error ? e.message : String(e))
      })
      try {
        const [analyticsRows, stats] = await Promise.all([listAnalyticsEvents(), getUserFeedbackStats()])
        if (cancelled) return
        setEvents(analyticsRows)
        setFeedbackStats(stats)
        emit({ type: 'feature_usage', payload: { feature: 'practice_insights' } })
      } catch (e) {
        const message = e instanceof Error ? e.message : 'unknown error'
        if (!cancelled) {
          setLoadError(message)
          toast.error(`Could not load practice insights: ${message}`)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const metrics = useMemo(
    () => computeEngagementMetrics(events, feedbackStats, new Date()),
    [events, feedbackStats],
  )

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <ScrollView className="flex-1 px-6 py-6" contentContainerStyle={{ paddingBottom: 40 }}>
        <View className="mb-5 flex-row items-center gap-3">
          <AnimatedPressable
            onPress={() => router.back()}
            haptic="light"
            className="flex h-11 w-11 items-center justify-center rounded-full border border-wood-600/50 bg-wood-800/60"
            accessibilityRole="button"
            accessibilityLabel="Back to settings"
          >
            <ChevronLeft color={colors.cream} size={20} strokeWidth={2} />
          </AnimatedPressable>
          <View className="flex-1">
            <Text className="font-serif text-3xl text-cream">Practice insights</Text>
            <Text className="mt-1 font-sans text-sm text-muted-light">
              Anonymous patterns from this device only.
            </Text>
          </View>
        </View>

        {loading ? (
          <Text className="font-sans text-sm text-muted-light">Loading practice insights…</Text>
        ) : loadError ? (
          <View className="rounded-2xl border border-danger/40 bg-danger/10 px-5 py-6">
            <Text className="font-serif text-lg text-cream">Insights could not load</Text>
            <Text className="mt-2 font-sans text-sm text-muted-light">{loadError}</Text>
          </View>
        ) : events.length === 0 ? (
          <View className="items-center rounded-2xl border border-wood-600/40 bg-wood-800/40 px-6 py-10">
            <BarChart3 color={colors.amber.accent} size={32} strokeWidth={1.5} />
            <Text className="mt-3 font-serif text-lg text-cream">No practice insights yet</Text>
            <Text className="mt-1 text-center font-sans text-xs text-muted-light">
              Complete a session or record a play-along to see local engagement data here.
            </Text>
          </View>
        ) : (
          <>
            <View className="mb-5 flex-row flex-wrap gap-2">
              <StatCard label="Sessions" value={String(metrics.totalSessions)} />
              <StatCard label="Completed" value={String(metrics.completedSessions)} />
              <StatCard label="Completion" value={formatPercent(metrics.completionRate)} />
            </View>

            <View className="mb-5 flex-row gap-3">
              <InfoCard
                icon={Clock}
                label="Avg session"
                value={formatDuration(metrics.averageSessionLengthSec)}
              />
              <InfoCard
                icon={Music}
                label="Play-along"
                value={formatDuration(metrics.totalPlayAlongSec)}
                helper={
                  metrics.averagePlayAlongSec > 0
                    ? `${formatDuration(metrics.averagePlayAlongSec)} avg take`
                    : undefined
                }
              />
            </View>

            <SectionCard icon={Music} title="Most-practiced songs">
              {metrics.mostPracticedSongs.length === 0 ? (
                <EmptyLine text="No song titles recorded yet." />
              ) : (
                metrics.mostPracticedSongs.map((song) => (
                  <View key={song.song_title} className="flex-row items-center justify-between py-1.5">
                    <Text className="flex-1 pr-3 font-sans text-sm text-cream" numberOfLines={1}>
                      {song.song_title}
                    </Text>
                    <Text className="font-mono text-xs text-amber-light">
                      {song.count} session{song.count === 1 ? '' : 's'}
                    </Text>
                  </View>
                ))
              )}
            </SectionCard>

            <SectionCard icon={Target} title="Most-corrected chords">
              {metrics.mostCorrectedChords.length === 0 ? (
                <EmptyLine text="No chord corrections yet." />
              ) : (
                metrics.mostCorrectedChords.map((item) => (
                  <View key={item.chord} className="flex-row items-center justify-between py-1.5">
                    <Text className="font-sans text-sm text-cream">{item.chord}</Text>
                    <Text className="font-mono text-xs text-amber-light">{item.count}</Text>
                  </View>
                ))
              )}
            </SectionCard>

            <FrequencyCard metrics={metrics} />
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  )
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <View
      accessible
      accessibilityLabel={`${label}: ${value}`}
      className="min-w-[96px] flex-1 rounded-xl border border-wood-600/50 bg-wood-800/60 p-3"
    >
      <Text className="font-serif text-2xl text-amber-light">{value}</Text>
      <Text className="mt-1 font-sans text-[10px] uppercase tracking-wider text-muted-light">{label}</Text>
    </View>
  )
}

function InfoCard({
  icon: Icon,
  label,
  value,
  helper,
}: {
  icon: typeof Clock
  label: string
  value: string
  helper?: string
}) {
  return (
    <View className="flex-1 rounded-xl border border-wood-600/50 bg-wood-800/60 p-4">
      <Icon color={colors.amber.accent} size={18} strokeWidth={2} />
      <Text className="mt-2 font-serif text-xl text-cream">{value}</Text>
      <Text className="mt-1 font-sans text-[10px] uppercase tracking-wider text-muted-light">{label}</Text>
      {helper ? <Text className="mt-1 font-sans text-[10px] text-muted-light">{helper}</Text> : null}
    </View>
  )
}

function SectionCard({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Music
  title: string
  children: React.ReactNode
}) {
  return (
    <View className="mb-5 rounded-2xl border border-wood-600/50 bg-wood-800/50 p-4">
      <View className="mb-2 flex-row items-center gap-2">
        <Icon color={colors.amber.accent} size={18} strokeWidth={2} />
        <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">{title}</Text>
      </View>
      {children}
    </View>
  )
}

function FrequencyCard({ metrics }: { metrics: EngagementMetrics }) {
  const maxCount = Math.max(1, ...metrics.sessionsByDay.map((day) => day.count))
  return (
    <View className="mb-5 rounded-2xl border border-wood-600/50 bg-wood-800/50 p-4">
      <View className="mb-3 flex-row items-center justify-between">
        <View className="flex-row items-center gap-2">
          <CalendarDays color={colors.amber.accent} size={18} strokeWidth={2} />
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">
            Last 7 days
          </Text>
        </View>
        <Text className="font-mono text-xs text-cream">
          {metrics.sessionsThisWeek} session{metrics.sessionsThisWeek === 1 ? '' : 's'}
        </Text>
      </View>
      <View className="gap-2">
        {metrics.sessionsByDay.map((day) => (
          <View key={day.date} className="flex-row items-center gap-3">
            <Text className="w-10 font-sans text-[11px] text-muted-light">{formatDayLabel(day.date)}</Text>
            <View className="h-2 flex-1 overflow-hidden rounded-full bg-wood-900/60">
              <View
                className="h-2 rounded-full bg-amber-accent/80"
                style={{ width: `${(day.count / maxCount) * 100}%` }}
              />
            </View>
            <Text className="w-5 text-right font-mono text-[11px] text-cream">{day.count}</Text>
          </View>
        ))}
      </View>
    </View>
  )
}

function EmptyLine({ text }: { text: string }) {
  return <Text className="font-sans text-xs text-muted-light">{text}</Text>
}
