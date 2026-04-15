import { useFocusEffect } from '@react-navigation/native'
import { useCallback, useMemo, useState } from 'react'
import { ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { CoachNote } from '@/components/CoachNote'
import { SkillGraph } from '@/components/SkillGraph'
import { WoodGradient } from '@/components/WoodGradient'
import { DEFAULT_SKILL_NODES } from '@/src/db/schema'
import { listSessionsJournal } from '@/src/db/client'
import type { SessionJournalRow } from '@/src/db/types'
import { useSkillStore } from '@/src/stores/skillStore'

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
  const [journal, setJournal] = useState<SessionJournalRow[]>([])

  const refresh = useCallback(() => {
    void loadSkills()
    void listSessionsJournal()
      .then(setJournal)
      .catch(() => setJournal([]))
  }, [loadSkills])

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

  const coachSummary =
    journal[0]?.coach_review?.trim() ||
    'Your pitch accuracy on bends has improved significantly over the last two weeks. The next frontier is dynamics: make the quiet notes whisper so the loud notes can scream.'

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

            <View>
              <Text className="mb-4 font-sans-medium text-sm uppercase tracking-wider text-muted-brown">Session History</Text>
              {journal.length === 0 ? (
                <Text className="font-sans text-sm text-muted-brown">No completed sessions yet.</Text>
              ) : (
                <View className="gap-4">
                  {journal.map((session) => {
                    const durationMin = (session as SessionJournalRow & { duration_min?: number | null }).duration_min
                    return (
                      <View
                        key={session.id}
                        className="rounded-xl border border-wood-700/50 bg-wood-800/40 p-5 transition-colors"
                      >
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
                            <Text className="font-sans text-sm text-muted-brown">{formatRelativeSessionDate(session.date)}</Text>
                            {durationMin != null ? (
                              <Text className="font-sans text-xs text-muted-brown">{durationMin} min</Text>
                            ) : null}
                          </View>
                        </View>
                        <Text className="border-t border-wood-700/50 pt-3 font-sans text-sm leading-relaxed text-cream/80">
                          &ldquo;{session.coach_review?.trim() || 'Keep going. Your consistency is building musical confidence.'}
                          &rdquo;
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
