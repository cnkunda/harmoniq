import { useRouter } from 'expo-router'
import { useEffect, useMemo, useState } from 'react'
import { Pressable, Text, View } from 'react-native'

import { ErrorBanner } from '@/components/ErrorBanner'
import { OnboardingScreenShell } from '@/components/onboarding/OnboardingScreenShell'
import { fetchOnboardingPlacementCoach } from '@/src/api/analyze'
import { DEFAULT_SKILL_NODES } from '@/src/db/schema'
import {
  aggregatePlacementCoachMetrics,
  aggregatePlacementNodeScores,
} from '@/src/onboarding/aggregatePlacementScores'
import { FALLBACK_PLACEMENT_COACH_COPY } from '@/src/onboarding/fallbackPlacementCoach'
import { commitPlacementOnboarding } from '@/src/db/client'
import type { MappedUiError } from '@/src/errors/mapErrorToUi'
import { toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import { useOnboardingPlacementStore } from '@/src/stores/onboardingPlacementStore'
import { useSkillStore } from '@/src/stores/skillStore'

const RADIAL_R = 78
const RADIAL_CX = 100
const RADIAL_CY = 102

export default function OnboardingResultsScreen() {
  const router = useRouter()
  const results = useOnboardingPlacementStore((s) => s.results)
  const loadSkills = useSkillStore((s) => s.loadFromDb)

  const [coachText, setCoachText] = useState<string | null>(null)
  const [confidenceNote, setConfidenceNote] = useState<string | null>(null)
  const [seedError, setSeedError] = useState<MappedUiError | null>(null)
  const [retryToken, setRetryToken] = useState(0)

  useEffect(() => {
    const [a, b, c] = results
    if (!a || !b || !c) {
      router.replace('/onboarding')
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const nodeScores = aggregatePlacementNodeScores([a, b, c])
        await commitPlacementOnboarding(nodeScores)
        if (cancelled) return
        await loadSkills()
        const metrics = aggregatePlacementCoachMetrics([a, b, c])
        try {
          const res = await fetchOnboardingPlacementCoach(metrics)
          if (!cancelled) {
            setCoachText(res.coach_paragraph)
            setConfidenceNote(res.confidence_note ?? null)
          }
        } catch {
          if (!cancelled) {
            setCoachText(FALLBACK_PLACEMENT_COACH_COPY)
            setConfidenceNote(
              metrics.placement_confidence === 'low'
                ? 'Your initial baseline used lower-confidence phrase captures and will adapt quickly with more takes.'
                : null,
            )
          }
        }
      } catch {
        if (!cancelled) {
          setSeedError({
            message: 'Could not save your onboarding baseline right now. Your phrase scores are safe - try again.',
            variant: 'error',
            actionKind: 'retry',
            actionLabel: 'Retry',
          })
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [results, router, loadSkills, retryToken])

  const nodes = useSkillStore((s) => s.nodes)
  const aggScores = useMemo(() => {
    const [x, y, z] = results
    if (!x || !y || !z) return null
    return aggregatePlacementNodeScores([x, y, z])
  }, [results])

  const displayNodes = DEFAULT_SKILL_NODES.map((def) => {
    const row = nodes.find((n) => n.id === def.id)
    const fallback = aggScores?.[def.id] ?? 0
    const value = row != null && row.sessions_count > 0 ? row.score : fallback
    return { id: def.id, label: def.label, value }
  })

  const finish = () => {
    router.replace('/(tabs)')
  }

  return (
    <OnboardingScreenShell currentStep={5} showProgress={false} scrollable>
      <View className="py-4">
        <Text className="text-center font-serif text-2xl text-cream">Your baseline</Text>
        <Text className="mt-2 text-center font-sans text-sm text-muted-brown">
          Five skill nodes are seeded from your three phrases. The coach note below is tailored to these averages (or
          an offline template if the server is unavailable).
        </Text>

        {seedError ? (
          <ErrorBanner
            className="mt-4"
            {...toErrorBannerProps(seedError, {
              onRetry: () => {
                setSeedError(null)
                setRetryToken((v) => v + 1)
              },
              onDismiss: () => setSeedError(null),
              onOpenSettings: () => setSeedError(null),
              onContinue: () => setSeedError(null),
            })}
          />
        ) : null}

        <View className="mt-8 h-[210px] w-[200px] self-center">
          {displayNodes.map((s, i) => {
            const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 5
            const x = RADIAL_CX + RADIAL_R * Math.cos(angle) - 36
            const y = RADIAL_CY + RADIAL_R * Math.sin(angle) - 22
            return (
              <View key={s.id} className="absolute w-[72px] items-center" style={{ left: x, top: y }}>
                <View className="h-3.5 w-3.5 rounded-full bg-amber-accent" />
                <Text className="mt-1 text-center text-[9px] leading-3 text-cream" numberOfLines={2}>
                  {s.label}
                </Text>
                <Text className="text-[9px] text-muted-brown">{(s.value * 100).toFixed(0)}%</Text>
              </View>
            )
          })}
        </View>

        <View className="mt-4 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Coach</Text>
          {coachText == null ? (
            <Text className="mt-2 font-sans text-sm text-muted-brown">Fetching coach note…</Text>
          ) : (
            <>
              <Text className="mt-2 font-sans text-sm leading-6 text-cream">{coachText}</Text>
              {confidenceNote ? <Text className="mt-3 font-sans text-xs text-muted-brown">{confidenceNote}</Text> : null}
            </>
          )}
        </View>

        <Pressable
          onPress={finish}
          className="mt-8 rounded-lg bg-amber-accent px-4 py-3"
          accessibilityRole="button"
          accessibilityLabel="Go to home"
        >
          <Text className="text-center font-sans-medium text-wood-900">Enter Harmoniq</Text>
        </Pressable>
      </View>
    </OnboardingScreenShell>
  )
}
