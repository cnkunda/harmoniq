import { useFocusEffect } from '@react-navigation/native'
import { useRouter, type Href } from 'expo-router'
import { Compass, Music, RefreshCw, Target } from 'lucide-react-native'
import { useCallback, useRef, useState } from 'react'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { Button } from '@/components/Button'
import { Pill } from '@/components/Pill'
import { AccuracyTrendChart } from '@/components/pulse/AccuracyTrendChart'
import type { MentorSkillDelta, MentorTrajectoryRequest } from '@/src/api/mentor'
import { colors } from '@/src/constants/colors'
import { loadMentorView, type MentorView } from '@/src/progress/mentorNote'
import type { PulseAccuracyPoint } from '@/src/progress/pulseData'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'

function formatShortDate(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function formatDelta(delta: number): string {
  const points = Math.round(delta * 100)
  return `${points >= 0 ? '+' : ''}${points} pts`
}

function deltaClass(delta: number): string {
  if (Math.abs(delta) < 0.005) return 'text-cream/70'
  return delta > 0 ? 'text-success' : 'text-danger'
}

function chartPoints(trajectory: MentorTrajectoryRequest): PulseAccuracyPoint[] {
  return trajectory.accuracy_points.map((point, index) => ({
    id: `mentor-${index}-${point.date}`,
    date: point.date,
    label: formatShortDate(point.date),
    accuracy: point.accuracy,
  }))
}

function modeLabel(mode: 'single' | 'plan'): string {
  return mode === 'plan' ? 'Following a plan' : 'Practicing a song'
}

function confidenceLabel(confidence: 'low' | 'medium' | 'high'): string {
  if (confidence === 'high') return 'High confidence'
  if (confidence === 'medium') return 'Medium confidence'
  return 'Early signal'
}

function SkillMovement({ deltas }: { deltas: MentorSkillDelta[] }) {
  if (deltas.length === 0) return null
  return (
    <View className="mt-4">
      <Text className="mb-2 font-sans-medium text-[11px] uppercase tracking-wider text-muted-light">
        Skill movement
      </Text>
      <View className="flex-row flex-wrap gap-2">
        {deltas.map((delta) => (
          <View key={delta.id} className="rounded-lg border border-wood-700/50 bg-wood-900/30 px-3 py-2">
            <Text className="font-sans text-[11px] text-muted-light">{delta.label}</Text>
            <Text className={`mt-0.5 font-sans-medium text-sm ${deltaClass(delta.delta)}`}>
              {formatDelta(delta.delta)}
            </Text>
          </View>
        ))}
      </View>
    </View>
  )
}

function PlanFacts({ trajectory }: { trajectory: MentorTrajectoryRequest }) {
  const plan = trajectory.plan
  if (!plan) return null
  const facts = [
    `${plan.slot_count} slot${plan.slot_count === 1 ? '' : 's'}`,
    ...plan.slot_types.map((type) => type.replace(/_/g, ' ')),
    ...plan.target_skills.map((skill) => skill.replace(/_/g, ' ')),
  ]
  const uniqueFacts = [...new Set(facts)]
  return (
    <View className="mb-2 flex-row flex-wrap gap-1.5">
      {uniqueFacts.map((fact) => (
        <Pill key={fact} variant="neutral" size="xs">
          {fact}
        </Pill>
      ))}
      {plan.remediation_count > 0 ? (
        <Pill variant="accent" size="xs">
          {plan.remediation_count} remediation{plan.remediation_count === 1 ? '' : 's'}
        </Pill>
      ) : null}
    </View>
  )
}

export function MentorSection() {
  const router = useRouter()
  const mode = useSessionPrefsStore((s) => s.homePracticeMode)
  const [view, setView] = useState<MentorView | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const hasLoadedRef = useRef(false)
  const inFlightRef = useRef(false)

  const load = useCallback(
    async (force: boolean) => {
      if (inFlightRef.current) return
      inFlightRef.current = true
      if (force) {
        setRefreshing(true)
      } else if (!hasLoadedRef.current) {
        setLoading(true)
      }
      try {
        const next = await loadMentorView(mode, { force })
        setView(next)
        hasLoadedRef.current = true
      } catch (error) {
        console.error('[Mentor] unexpected view load error', error)
        setView({
          kind: 'error',
          message: error instanceof Error ? error.message : 'Mentor could not load.',
          historyDays: 0,
          evidenceCount: 0,
        })
      } finally {
        inFlightRef.current = false
        setLoading(false)
        setRefreshing(false)
      }
    },
    [mode],
  )

  useFocusEffect(
    useCallback(() => {
      void load(false)
    }, [load]),
  )

  return (
    <View className="mb-12">
      <View className="mb-4 flex-row flex-wrap items-center justify-between gap-2">
        <View>
          <Text className="font-sans-medium text-sm uppercase tracking-wider text-muted-light">Mentor</Text>
          <Text className="mt-1 font-serif text-2xl text-cream">Your next month</Text>
        </View>
        <Pill variant="accent" size="xs">
          {modeLabel(mode)}
        </Pill>
      </View>

      <View className="rounded-2xl border border-wood-700/50 bg-wood-800/40 p-5">
        {loading ? (
          <View>
            <Text className="font-serif text-xl text-cream">Reading your last month…</Text>
            <Text className="mt-2 font-sans text-sm leading-6 text-muted-light">
              Pulling together sessions, plans, corrections, and Riff DNA.
            </Text>
          </View>
        ) : view == null ? (
          <View>
            <Text className="font-serif text-xl text-cream">Mentor could not load</Text>
            <Text className="mt-2 font-sans text-sm leading-6 text-muted-light">
              Try again in a moment.
            </Text>
            <Button
              label="Try again"
              variant="secondary"
              size="sm"
              haptic="light"
              onPress={() => void load(true)}
              accessibilityLabel="Retry loading mentor"
              className="mt-4 self-start"
            />
          </View>
        ) : view.kind === 'ineligible' ? (
          <View className="flex-row items-start gap-3">
            <View className="mt-0.5 h-9 w-9 items-center justify-center rounded-full border border-wood-600/50 bg-wood-900/40">
              <Compass color={colors.amber.accent} size={18} strokeWidth={1.75} />
            </View>
            <View className="flex-1">
              <Text className="font-serif text-lg text-cream">Your mentor needs a little more history</Text>
              <Text className="mt-1 font-sans text-sm leading-6 text-muted-light">
                {view.evidenceCount < 3
                  ? 'Log at least three sessions, jams, or completed plans. Your mentor will start mapping the longer trend from there.'
                  : `Keep practicing for ${Math.max(0, 30 - view.historyDays)} more day${
                      Math.max(0, 30 - view.historyDays) === 1 ? '' : 's'
                    } and your mentor will start mapping your longer trend.`}
              </Text>
            </View>
          </View>
        ) : view.kind === 'error' ? (
          <View>
            <Text className="font-serif text-xl text-cream">Mentor is unavailable</Text>
            <Text className="mt-2 font-sans text-sm leading-6 text-muted-light">{view.message}</Text>
            <Button
              label="Try again"
              variant="secondary"
              size="sm"
              haptic="light"
              onPress={() => void load(true)}
              accessibilityLabel="Retry loading mentor"
              className="mt-4 self-start"
            />
          </View>
        ) : (
          <MentorNoteBody view={view} refreshing={refreshing} onRefresh={() => void load(true)} router={router} />
        )}
      </View>
    </View>
  )
}

function MentorNoteBody({
  view,
  refreshing,
  onRefresh,
  router,
}: {
  view: Extract<MentorView, { kind: 'ready' }>
  refreshing: boolean
  onRefresh: () => void
  router: ReturnType<typeof useRouter>
}) {
  const { note, trajectory } = view
  const history = trajectory.history
  const planFallback = trajectory.plan
    ? `This plan runs ${trajectory.plan.slot_count} slots across ${trajectory.plan.slot_types
        .map((type) => type.replace(/_/g, ' '))
        .join(', ')}. Your next scored sessions will tell the mentor whether to keep or change that shape.`
    : 'No active plan yet. Start a plan from Home and your mentor will explain how each slot builds toward your goals.'

  return (
    <View>
      <Text className="font-serif text-xl text-cream">{note.headline}</Text>
      <Text className="mt-1 font-sans text-xs text-muted-light">
        Based on {history.session_count} session{history.session_count === 1 ? '' : 's'} over {history.days} days ·{' '}
        {confidenceLabel(note.confidence)} · Updated {formatShortDate(note.generated_at)}
      </Text>

      {view.stale ? (
        <Text className={`mt-2 font-sans text-xs ${view.refreshError ? 'text-danger' : 'text-muted-light'}`}>
          {view.refreshError ? `Could not refresh: ${view.refreshError}` : 'Showing your last mentor note.'}
        </Text>
      ) : null}

      <Text className="mt-3 font-sans text-sm leading-6 text-cream/85">{note.trajectory_summary}</Text>

      {note.plateau_diagnosis ? (
        <View className="mt-4 rounded-lg border border-amber-accent/25 bg-amber-accent/5 px-3 py-3">
          <Text className="font-sans-medium text-[11px] uppercase tracking-wider text-amber-light">Plateau read</Text>
          <Text className="mt-1 font-sans text-xs leading-5 text-cream/85">{note.plateau_diagnosis}</Text>
        </View>
      ) : null}

      {trajectory.accuracy_points.length > 0 ? (
        <View className="mt-5 rounded-xl border border-wood-700/40 bg-wood-900/30 p-4">
          <AccuracyTrendChart points={chartPoints(trajectory)} />
        </View>
      ) : (
        <Text className="mt-4 font-sans text-xs text-muted-light">
          No scored sessions in this window yet — the mentor is reading your plans, jams, and corrections instead.
        </Text>
      )}

      <SkillMovement deltas={trajectory.skill_deltas} />

      <View className="mt-6">
        <View className="mb-2 flex-row items-center gap-2">
          <Music color={colors.amber.accent} size={16} strokeWidth={2} />
          <Text className="font-sans-medium text-xs uppercase tracking-wider text-muted-light">Next songs to play</Text>
        </View>
        {note.next_songs.length > 0 ? (
          <View className="gap-2">
            {note.next_songs.map((song) => (
              <View
                key={`${song.source}-${song.title}`}
                className="rounded-lg border border-wood-700/40 bg-wood-900/25 px-3 py-3"
              >
                <View className="flex-row items-start justify-between gap-2">
                  <View className="flex-1">
                    <Text className="font-sans-medium text-sm text-cream">{song.title}</Text>
                    {song.artist ? (
                      <Text className="font-sans text-xs text-amber-light/80">{song.artist}</Text>
                    ) : null}
                  </View>
                  <Pill variant={song.source === 'library' ? 'accent' : 'light'} size="xs">
                    {song.source === 'library' ? 'Library' : 'Idea'}
                  </Pill>
                </View>
                <Text className="mt-1 font-sans text-xs leading-5 text-cream/75">{song.reason}</Text>
              </View>
            ))}
          </View>
        ) : (
          <Text className="font-sans text-sm leading-6 text-muted-light">
            Add a song to your library and your mentor can suggest where to go next.
          </Text>
        )}
        <View className="mt-3 flex-row flex-wrap gap-3">
          <AnimatedPressable
            onPress={() => router.push('/library' as Href)}
            haptic="light"
            accessibilityRole="button"
            accessibilityLabel="Browse your song library"
            className="rounded-lg border border-wood-600/50 bg-wood-800/50 px-3 py-2"
          >
            <Text className="font-sans-medium text-xs text-cream">Browse library</Text>
          </AnimatedPressable>
          {note.next_songs.some((song) => song.source === 'taste') ? (
            <AnimatedPressable
              onPress={() => router.push('/add-song' as Href)}
              haptic="light"
              accessibilityRole="button"
              accessibilityLabel="Add a suggested song"
              className="rounded-lg border border-wood-600/50 bg-wood-800/50 px-3 py-2"
            >
              <Text className="font-sans-medium text-xs text-cream">Add a song</Text>
            </AnimatedPressable>
          ) : null}
        </View>
      </View>

      <View className="mt-6">
        <View className="mb-2 flex-row items-center gap-2">
          <Target color={colors.amber.accent} size={16} strokeWidth={2} />
          <Text className="font-sans-medium text-xs uppercase tracking-wider text-muted-light">
            How your plan builds your playing
          </Text>
        </View>
        <PlanFacts trajectory={trajectory} />
        <Text className="font-sans text-sm leading-6 text-cream/85">{note.plan_guidance ?? planFallback}</Text>
      </View>

      {note.next_month.length > 0 ? (
        <View className="mt-6">
          <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wider text-muted-light">
            Proposed next month
          </Text>
          <View className="gap-2">
            {note.next_month.map((item, index) => (
              <View
                key={`${item.title}-${index}`}
                className="rounded-lg border border-wood-700/40 bg-wood-900/25 px-3 py-3"
              >
                <View className="flex-row items-start gap-2">
                  <Pill variant="neutral" size="xs">
                    {item.mode === 'plan' ? 'Plan' : 'Song'}
                  </Pill>
                  <Text className="flex-1 font-sans-medium text-sm text-cream">{item.title}</Text>
                </View>
                <Text className="mt-1 font-sans text-[11px] uppercase tracking-wider text-amber-light/80">
                  {item.skill_focus.replace(/_/g, ' ')}
                </Text>
                <Text className="mt-1 font-sans text-xs leading-5 text-cream/75">{item.why}</Text>
              </View>
            ))}
          </View>
        </View>
      ) : null}

      <View className="mt-6 flex-row flex-wrap items-center justify-between gap-3 border-t border-wood-700/50 pt-4">
        <Text className="flex-1 font-sans text-[11px] leading-4 text-muted-light">
          Proposals only — nothing changes automatically.
        </Text>
        <Button
          label="Refresh note"
          variant="secondary"
          size="sm"
          haptic="light"
          loading={refreshing}
          onPress={onRefresh}
          accessibilityLabel="Refresh mentor note"
          icon={<RefreshCw color={colors.cream} size={14} strokeWidth={2} />}
        />
      </View>
    </View>
  )
}
