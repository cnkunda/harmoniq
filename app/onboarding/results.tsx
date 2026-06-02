import { useLocalSearchParams, useRouter } from 'expo-router'
import { Music2, Check, X } from 'lucide-react-native'
import { useEffect, useMemo, useState } from 'react'
import { ActivityIndicator, Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { ErrorBanner } from '@/components/ErrorBanner'
import { OnboardingScreenShell } from '@/components/onboarding/OnboardingScreenShell'
import { toast } from '@/components/ToastConfig'
import { fetchOnboardingPlacementCoach, parseTasteProfileJson } from '@/src/api/analyze'
import { ONBOARDING_STEP_WITHOUT_QUIZ, ONBOARDING_WITHOUT_QUIZ_TOTAL, ONBOARDING_WITH_QUIZ_TOTAL } from '@/src/constants/onboardingSteps'
import colors from '@/src/constants/colors'
import { getAppPref, commitPlacementOnboarding } from '@/src/db/client'
import { DEFAULT_SKILL_NODES, PREF_TASTE_PROFILE_JSON } from '@/src/db/schema'
import type { MappedUiError } from '@/src/errors/mapErrorToUi'
import { toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import {
  aggregatePlacementCoachMetrics,
  aggregatePlacementNodeScores,
} from '@/src/onboarding/aggregatePlacementScores'
import { FALLBACK_PLACEMENT_COACH_COPY } from '@/src/onboarding/fallbackPlacementCoach'
import { suggestOnboardingSongs, type SongSuggestion } from '@/src/onboarding/suggestSongs'
import { useOnboardingPlacementStore } from '@/src/stores/onboardingPlacementStore'
import { useSkillStore } from '@/src/stores/skillStore'

const RADIAL_R = 78
const RADIAL_CX = 100
const RADIAL_CY = 102

type AnalysisState = 'idle' | 'analyzing' | 'done' | 'error'

export default function OnboardingResultsScreen() {
  const router = useRouter()
  const { quizTaken } = useLocalSearchParams<{ quizTaken?: string }>()
  const results = useOnboardingPlacementStore((s) => s.results)
  const loadSkills = useSkillStore((s) => s.loadFromDb)

  const [coachText, setCoachText] = useState<string | null>(null)
  const [confidenceNote, setConfidenceNote] = useState<string | null>(null)
  const [seedError, setSeedError] = useState<MappedUiError | null>(null)
  const [retryToken, setRetryToken] = useState(0)

  const [suggestions, setSuggestions] = useState<SongSuggestion[]>([])
  const [selectedSongs, setSelectedSongs] = useState<Set<number>>(() => new Set())
  const [analysisState, setAnalysisState] = useState<AnalysisState>('idle')
  const [analysisProgress, setAnalysisProgress] = useState(0)
  const [hasQuiz, setHasQuiz] = useState(quizTaken === '1')
  const resultsStep = hasQuiz ? 7 : ONBOARDING_STEP_WITHOUT_QUIZ.results
  const resultsTotal = hasQuiz ? ONBOARDING_WITH_QUIZ_TOTAL : ONBOARDING_WITHOUT_QUIZ_TOTAL

  useEffect(() => {
    const [a, b, c] = results
    if (!a || !b || !c) {
      // Results aren't populated yet — render a stable empty state instead of
      // redirecting away, so the route remains testable and discoverable.
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

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const tasteJson = await getAppPref(PREF_TASTE_PROFILE_JSON)
        const taste = parseTasteProfileJson(tasteJson)
        if (!cancelled) {
          if (!hasQuiz) setHasQuiz(taste != null)
          const songs = await suggestOnboardingSongs(taste)
          setSuggestions(songs)
          setSelectedSongs(new Set(songs.map((_, i) => i)))
        }
      } catch {
        if (!cancelled) {
          setSuggestions([])
        }
      }
    })()
    return () => {
      cancelled = true
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  const toggleSong = (index: number) => {
    setSelectedSongs((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        if (next.size > 1) next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  const startSession = () => {
    router.replace('/(tabs)')
  }

  const analyzeAndContinue = async () => {
    if (selectedSongs.size === 0) {
      toast.error('Select at least one song to continue.')
      return
    }
    setAnalysisState('analyzing')
    setAnalysisProgress(0)
    try {
      const selected = suggestions.filter((_, i) => selectedSongs.has(i))
      for (let i = 0; i < selected.length; i++) {
        setAnalysisProgress(Math.round(((i + 1) / selected.length) * 100))
        // TODO: Actually analyze the YouTube URLs via POST /analyze
        // For now, simulate a short delay
        await new Promise((resolve) => setTimeout(resolve, 500))
      }
      setAnalysisState('done')
      toast.success('Session ready!')
    } catch {
      setAnalysisState('error')
      toast.error('Could not analyze songs. You can add them later from Home.')
    }
  }

  const finish = () => {
    router.replace('/(tabs)')
  }

  const [a, b, c] = results
  if (!a || !b || !c) {
    return (
      <OnboardingScreenShell
        currentStep={resultsStep}
        totalSteps={resultsTotal}
        showProgress={false}
      >
        <View className="flex-1 items-center justify-center gap-4 py-16">
          <Text className="text-center font-serif text-2xl text-cream">Your baseline will appear here</Text>
          <Text className="max-w-md text-center font-sans text-sm leading-6 text-muted-brown">
            Complete the three placement phrases to see your skill baseline, coach note, and song
            recommendations on this screen.
          </Text>
          <AnimatedPressable
            haptic="light"
            onPress={() => router.replace('/onboarding/phrase/0')}
            className="mt-4 rounded-xl bg-amber-accent px-8 py-3.5"
            accessibilityRole="button"
            accessibilityLabel="Start placement phrases"
          >
            <Text className="font-sans-medium text-wood-900">Start placement phrases</Text>
          </AnimatedPressable>
        </View>
      </OnboardingScreenShell>
    )
  }

  return (
    <OnboardingScreenShell currentStep={resultsStep} totalSteps={resultsTotal} showProgress={false} scrollable>
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

        <View className="mt-8">
          <Text className="text-center font-serif text-xl text-cream">We picked these for you</Text>
          <Text className="mt-1 text-center font-sans text-sm text-muted-brown">
            Based on your taste — select the songs you want in your first session.
          </Text>

          {suggestions.length === 0 ? (
            <View className="mt-4 items-center">
              <ActivityIndicator color={colors.amber.accent} />
            </View>
          ) : (
            <View className="mt-4 gap-3">
              {suggestions.map((song, i) => {
                const selected = selectedSongs.has(i)
                return (
                  <AnimatedPressable
                    key={i}
                    onPress={() => toggleSong(i)}
                    className={`flex-row items-center gap-3 rounded-xl border p-3 ${
                      selected ? 'border-amber-accent bg-amber-accent/12' : 'border-wood-600/50 bg-wood-800/80'
                    }`}
                    accessibilityRole="button"
                    accessibilityState={{ selected }}
                  >
                    <View className="h-10 w-10 items-center justify-center rounded-full border border-wood-600/50 bg-wood-900/60">
                      <Music2 color={colors.amber.accent} size={20} strokeWidth={1.5} />
                    </View>
                    <View className="flex-1">
                      <Text className="font-sans-medium text-sm text-cream">{song.title}</Text>
                      <Text className="font-sans text-xs text-muted-brown">{song.artist}</Text>
                    </View>
                    <View className="h-6 w-6 items-center justify-center rounded-full border border-wood-600/50">
                      {selected ? (
                        <Check color={colors.amber.accent} size={14} strokeWidth={2} />
                      ) : (
                        <X color={colors.muted.brown} size={14} strokeWidth={2} />
                      )}
                    </View>
                  </AnimatedPressable>
                )
              })}
            </View>
          )}

          {analysisState === 'analyzing' && (
            <View className="mt-4 items-center">
              <Text className="font-sans text-sm text-amber-light">Analyzing songs… {analysisProgress}%</Text>
              <View className="mt-2 h-1.5 w-full max-w-xs rounded-full bg-wood-700">
                <View
                  className="h-full rounded-full bg-amber-accent"
                  style={{ width: `${analysisProgress}%` }}
                />
              </View>
            </View>
          )}

          {analysisState === 'error' && (
            <Text className="mt-3 text-center font-sans text-xs text-danger">
              Analysis failed. You can add these songs later from Home.
            </Text>
          )}
        </View>

        <View className="mt-8 gap-3">
          {analysisState === 'idle' && (
            <>
              <AnimatedPressable haptic="light"
                onPress={analyzeAndContinue}
                disabled={suggestions.length === 0}
                className="w-full rounded-xl bg-amber-accent px-4 py-3 disabled:opacity-50"
                accessibilityRole="button"
                accessibilityLabel="Analyze selected songs and start session"
              >
                <Text className="text-center font-sans-medium text-wood-900">
                  Analyze &amp; start session
                </Text>
              </AnimatedPressable>
              <AnimatedPressable haptic="light"
                onPress={startSession}
                className="w-full rounded-xl border border-wood-600/50 px-4 py-3"
                accessibilityRole="button"
                accessibilityLabel="Skip song analysis and go to home"
              >
                <Text className="text-center font-sans-medium text-cream">Skip for now</Text>
              </AnimatedPressable>
            </>
          )}

          {analysisState === 'done' && (
            <AnimatedPressable haptic="light"
              onPress={finish}
              className="w-full rounded-xl bg-amber-accent px-4 py-3"
              accessibilityRole="button"
              accessibilityLabel="Go to home"
            >
              <Text className="text-center font-sans-medium text-wood-900">Enter Harmoniq</Text>
            </AnimatedPressable>
          )}

          {analysisState === 'error' && (
            <>
              <AnimatedPressable haptic="light"
                onPress={finish}
                className="w-full rounded-xl bg-amber-accent px-4 py-3"
                accessibilityRole="button"
                accessibilityLabel="Go to home"
              >
                <Text className="text-center font-sans-medium text-wood-900">Enter Harmoniq</Text>
              </AnimatedPressable>
              <AnimatedPressable haptic="light"
                onPress={() => setAnalysisState('idle')}
                className="w-full rounded-xl border border-wood-600/50 px-4 py-3"
                accessibilityRole="button"
              >
                <Text className="text-center font-sans-medium text-cream">Try again</Text>
              </AnimatedPressable>
            </>
          )}
        </View>
      </View>
    </OnboardingScreenShell>
  )
}
