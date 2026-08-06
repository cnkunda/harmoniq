import { useFocusEffect } from '@react-navigation/native'
import { useCallback, useMemo, useState } from 'react'
import { ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { CoachNote } from '@/components/CoachNote'
import { LearnerContextCard } from '@/components/LearnerContextCard'
import { RiffDNA } from '@/components/RiffDNA'
import { SkillGraph } from '@/components/SkillGraph'
import { WoodGradient } from '@/components/WoodGradient'
import { summaryFromPlanCompletionRow } from '@/src/home/planCompletionSummary'
import { DEFAULT_SKILL_NODES } from '@/src/db/schema'
import { listJamSnapshots, listPracticePlanCompletions, listSessionsJournal } from '@/src/db/client'
import { mergeProgressTimeline, type ProgressTimelineItem } from '@/src/progress/mergeProgressTimeline'
import { useDnaStore } from '@/src/stores/dnaStore'
import { useSkillStore } from '@/src/stores/skillStore'
import type { JamSummaryBundle } from '@/src/api/jam'

function formatRelativeSessionDate(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  const today = new Date()
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const startOfInput = new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate())
  const days = Math.floor((startOfToday.getTime() - startOfInput.getTime()) / (24 * 60 * 60 * 1000))
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days} days ago`
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function focusLabel(sectionLabel: string | null): string {
  if (!sectionLabel?.trim()) return 'General Feel'
  return sectionLabel.trim()
}

export default function ProgressScreen() {
  const loadSkills = useSkillStore((s) => s.loadFromDb)
  const nodes = useSkillStore((s) => s.nodes)
  const dna = useDnaStore((s) => s.dna)
  const refreshDna = useDnaStore((s) => s.refresh)
  const [timeline, setTimeline] = useState<ProgressTimelineItem[]>([])

  const refresh = useCallback(() => {
    void loadSkills()
    void refreshDna()
    void Promise.all([listSessionsJournal(), listJamSnapshots(), listPracticePlanCompletions()])
      .then(([sessions, jams, completions]) => {
        setTimeline(mergeProgressTimeline(sessions, jams, completions))
      })
      .catch(() => setTimeline([]))
  }, [loadSkills, refreshDna])

  useFocusEffect(
    useCallback(() => {
      refresh()
    }, [refresh]),
  )

  const displayNodes = useMemo(() => {
    return DEFAULT_SKILL_NODES.map((def) => {
      const row = nodes.find((n) => n.id === def.id)
      const score = row != null ? row.score : 0
      return {
        id: def.id,
        label: def.label,
        score,
      }
    })
  }, [nodes])

  const coachSummary = useMemo(() => {
    const hit = timeline.find((i) => i.kind === 'review_score' && i.session.coach_review?.trim())
    if (hit?.kind === 'review_score') return hit.session.coach_review!.trim()
    return 'Finish a practice session through Review to capture a personalized coach summary here.'
  }, [timeline])

  return (
    <WoodGradient className="flex-1">
      <SafeAreaView className="flex-1" edges={['top', 'left', 'right']}>
        <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 32 }} showsVerticalScrollIndicator={false}>
          <View className="w-full max-w-4xl self-center px-6 pb-8 pt-4">
            <View className="mb-8 mt-4">
              <Text className="mb-2 font-serif text-3xl text-cream">Your Progress</Text>
              <Text className="font-sans text-muted-brown">A slow-moving map of your musical feel.</Text>
              <Text className="mt-2 font-sans text-xs text-muted-brown">
                Node movement blends accuracy, timing stability, and capture confidence so low-signal takes do not cause jumps.
              </Text>
            </View>

            <View className="mb-8">
              <LearnerContextCard skillNodes={nodes} />
            </View>

            <View className="mb-12 flex-col gap-8 md:flex-row md:items-stretch">
              <View className="md:flex-1">
                <Text className="mb-4 font-sans-medium text-sm uppercase tracking-wider text-muted-brown">Skill Map</Text>
                <SkillGraph nodes={displayNodes} />
              </View>

              <View className="md:flex-1 md:justify-center">
                <Text className="mb-4 font-sans-medium text-sm uppercase tracking-wider text-muted-brown">
                  Coach Summary
                </Text>
                <CoachNote text={coachSummary} className="h-full" />
              </View>
            </View>

            <View className="mb-12">
              <Text className="mb-4 font-sans-medium text-sm uppercase tracking-wider text-muted-brown">Your DNA</Text>
              <RiffDNA dna={dna} />
            </View>

            <View>
              <Text className="mb-4 font-sans-medium text-sm uppercase tracking-wider text-muted-brown">Session History</Text>
              <Text className="mb-3 font-sans text-xs text-muted-brown">
                Review scores, saved jams, and completed practice plans in one timeline.
              </Text>
              {timeline.length === 0 ? (
                <Text className="font-sans text-sm text-muted-brown">No history yet.</Text>
              ) : (
                <View className="gap-4">
                  {timeline.map((item) => {
                    if (item.kind === 'review_score') {
                      const session = item.session
                      const durationMin = session.duration_min
                      return (
                        <View
                          key={`r-${session.id}`}
                          className="rounded-xl border border-wood-700/50 bg-wood-800/40 p-5 transition-colors"
                        >
                          <View className="mb-2 flex-row flex-wrap items-center gap-2">
                            <Text className="rounded-full bg-amber-accent/15 px-2.5 py-0.5 font-sans-medium text-[11px] text-amber-light">
                              Review
                            </Text>
                          </View>
                          <View className="mb-3 flex-row items-start justify-between">
                            <View className="flex-1 pr-3">
                              <Text className="font-serif text-lg text-cream">
                                {session.song_title?.trim() || 'Practice session'}
                              </Text>
                              <Text className="font-sans text-sm text-amber-light/80">
                                Focus: {focusLabel(session.section_label)}
                              </Text>
                            </View>
                            <View className="items-end">
                              <Text className="font-sans text-sm text-muted-brown">
                                {formatRelativeSessionDate(session.date)}
                              </Text>
                              {durationMin != null ? (
                                <Text className="font-sans text-xs text-muted-brown">{durationMin} min</Text>
                              ) : null}
                            </View>
                          </View>
                          <Text className="border-t border-wood-700/50 pt-3 font-sans text-sm leading-relaxed text-cream/80">
                            &ldquo;
                            {session.coach_review?.trim() ||
                              'Keep going. Your consistency is building musical confidence.'}
                            &rdquo;
                          </Text>
                        </View>
                      )
                    }
                    if (item.kind === 'jam_snapshot') {
                      const jam = item.jam
                      const title = jam.track_label?.trim() || 'Jam session'
                      const durMin = jam.duration_seconds >= 60 ? Math.round(jam.duration_seconds / 60) : null
                      const durLabel =
                        durMin != null && durMin > 0 ? `${durMin} min` : `${Math.max(0, jam.duration_seconds)}s`
                      let summaryBundle: JamSummaryBundle | null = null
                      if (jam.summary_bundle_json) {
                        try {
                          summaryBundle = JSON.parse(jam.summary_bundle_json) as JamSummaryBundle
                        } catch {
                          // ignore parse errors
                        }
                      }
                      return (
                        <View
                          key={`j-${jam.id}`}
                          className="rounded-xl border border-wood-700/50 bg-wood-800/40 p-5 transition-colors"
                        >
                          <View className="mb-2 flex-row flex-wrap items-center gap-2">
                            <Text className="rounded-full bg-cream/10 px-2.5 py-0.5 font-sans-medium text-[11px] text-cream/90">
                              Jam
                            </Text>
                          </View>
                          <View className="mb-3 flex-row items-start justify-between">
                            <View className="flex-1 pr-3">
                              <Text className="font-serif text-lg text-cream">{title}</Text>
                              <Text className="font-sans text-sm text-amber-light/80">
                                {jam.track_key?.trim() ? `${jam.track_key.trim()} · ` : ''}
                                {durLabel}
                                {jam.inferred_scale_label?.trim() ? ` · ${jam.inferred_scale_label.trim()}` : ''}
                              </Text>
                            </View>
                            <Text className="font-sans text-sm text-muted-brown">{formatRelativeSessionDate(jam.date)}</Text>
                          </View>
                          {summaryBundle ? (
                            <View className="border-t border-wood-700/50 pt-3">
                              {summaryBundle.coach_summary ? (
                                <Text className="font-sans text-sm leading-relaxed text-cream/80">
                                  {summaryBundle.coach_summary}
                                </Text>
                              ) : null}
                              {summaryBundle.coach_strengths.length > 0 ? (
                                <Text className="mt-1.5 font-sans text-xs text-amber-light/80">
                                  Strengths: {summaryBundle.coach_strengths.join(', ')}
                                </Text>
                              ) : null}
                              {summaryBundle.coach_focus_areas.length > 0 ? (
                                <Text className="mt-1 font-sans text-xs text-muted-brown">
                                  Focus areas: {summaryBundle.coach_focus_areas.join(', ')}
                                </Text>
                              ) : null}
                              {summaryBundle.coach_next_step ? (
                                <Text className="mt-1 font-sans text-xs text-amber-light/70">
                                  Next step: {summaryBundle.coach_next_step}
                                </Text>
                              ) : null}
                              {summaryBundle.vocabulary_patterns.length > 0 ? (
                                <Text className="mt-1.5 font-sans text-[11px] text-muted-brown/80">
                                  Patterns: {summaryBundle.vocabulary_patterns.map((p) => p.description).join('; ')}
                                </Text>
                              ) : null}
                              <Text className="mt-1 font-sans text-[11px] text-muted-brown/60">
                                {summaryBundle.phrase_count} phrases · {summaryBundle.total_notes} notes · diversity{' '}
                                {(summaryBundle.vocabulary_diversity * 100).toFixed(0)}%
                              </Text>
                            </View>
                          ) : (
                            <Text className="border-t border-wood-700/50 pt-3 font-sans text-sm leading-relaxed text-cream/80">
                              &ldquo;{jam.coach_summary?.trim() || 'Jam snapshot saved.'}&rdquo;
                            </Text>
                          )}
                        </View>
                      )
                    }
                    const row = item.completion
                    const { stepCount, firstTitle } = summaryFromPlanCompletionRow(row)
                    const subtitle =
                      stepCount > 0
                        ? `${stepCount}-section plan${firstTitle ? ` · started with ${firstTitle}` : ''}`
                        : 'Practice plan'
                    return (
                      <View
                        key={`p-${row.id}`}
                        className="rounded-xl border border-wood-700/50 bg-wood-800/40 p-5 transition-colors"
                      >
                        <View className="mb-2 flex-row flex-wrap items-center gap-2">
                          <Text className="rounded-full bg-amber-accent/25 px-2.5 py-0.5 font-sans-medium text-[11px] text-wood-900">
                            Plan
                          </Text>
                        </View>
                        <View className="mb-3 flex-row items-start justify-between">
                          <View className="flex-1 pr-3">
                            <Text className="font-serif text-lg text-cream">Practice plan completed</Text>
                            <Text className="font-sans text-sm text-amber-light/80">{subtitle}</Text>
                          </View>
                          <Text className="font-sans text-sm text-muted-brown">
                            {formatRelativeSessionDate(row.completed_at)}
                          </Text>
                        </View>
                        <Text className="border-t border-wood-700/50 pt-3 font-sans text-sm leading-relaxed text-cream/80">
                          &ldquo;Nice work closing the loop—this full plan is in the books.&rdquo;
                        </Text>
                      </View>
                    )
                  })}
                </View>
              )}
            </View>
          </View>
        </ScrollView>
      </SafeAreaView>
    </WoodGradient>
  )
}
