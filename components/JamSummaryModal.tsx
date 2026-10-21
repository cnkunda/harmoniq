import { ActivityIndicator, Modal, ScrollView, Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import type { JamPhraseFeedback, JamPhraseMetrics, JamSummaryBundle } from '@/src/api/jam'
import { colors } from '@/src/constants/colors'
import type { BackingTrackDefinition } from '@/src/constants/backingTracks'

export type JamSummaryStatus = 'pending' | 'ready' | 'failed' | 'skipped'

type JamSummaryModalProps = {
  visible: boolean
  status: JamSummaryStatus
  bundle: JamSummaryBundle | null
  coachSummary: string
  phrases: readonly JamPhraseMetrics[]
  track: BackingTrackDefinition | null
  onClose: () => void
  onRetry?: () => void
  onPracticePhrase?: (feedback: JamPhraseFeedback, metrics: JamPhraseMetrics) => void
}

function gradeColor(grade: JamSummaryBundle['grade']): string {
  if (grade === 'A' || grade === 'B') return colors.success
  if (grade === 'C') return colors.amber.accent
  return colors.danger
}

function phraseMetricsFor(
  feedback: JamPhraseFeedback,
  phrases: readonly JamPhraseMetrics[],
): JamPhraseMetrics | null {
  return phrases[feedback.phrase_index] ?? null
}

export function JamSummaryModal({
  visible,
  status,
  bundle,
  coachSummary,
  phrases,
  track,
  onClose,
  onRetry,
  onPracticePhrase,
}: JamSummaryModalProps) {
  const summary = bundle?.coach_summary?.trim() || coachSummary.trim()
  const weakestFeedback =
    bundle?.phrase_feedback.find((item) => item.phrase_index === bundle.weakest_phrase_index) ??
    bundle?.phrase_feedback[0] ??
    null
  const weakestMetrics =
    bundle && weakestFeedback ? phraseMetricsFor(weakestFeedback, phrases) : null
  const weakestHasLoop =
    weakestMetrics != null &&
    track != null &&
    weakestMetrics.backing_start_ms != null &&
    weakestMetrics.backing_end_ms != null &&
    weakestMetrics.backing_end_ms > weakestMetrics.backing_start_ms

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View className="flex-1">
        <AnimatedPressable
          className="absolute inset-0 bg-wood-900/60"
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel="Close jam summary"
        />
        <View className="flex-1 justify-center px-5 py-10">
          <View className="max-h-[85%] w-full max-w-lg self-center overflow-hidden rounded-3xl border border-wood-600/70 bg-wood-900">
            <View className="flex-row items-center justify-between border-b border-wood-700/60 px-5 py-4">
              <Text className="font-serif text-xl text-cream">Jam summary</Text>
              <AnimatedPressable
                onPress={onClose}
                haptic="light"
                className="min-h-[44px] min-w-[44px] items-center justify-center"
                accessibilityRole="button"
                accessibilityLabel="Close jam summary"
              >
                <Text className="font-sans-medium text-sm text-muted-light">Close</Text>
              </AnimatedPressable>
            </View>

            <ScrollView className="px-5" contentContainerStyle={{ paddingTop: 16, paddingBottom: 20 }}>
              {status === 'pending' ? (
                <View className="items-center gap-3 py-8">
                  <ActivityIndicator color={colors.amber.light} />
                  <Text className="text-center font-sans text-sm text-cream">
                    Analyzing your phrases…
                  </Text>
                  <Text className="text-center font-sans text-xs leading-snug text-muted-light">
                    Your jam is already saved. The coach summary will appear here when it is ready.
                  </Text>
                </View>
              ) : null}

              {status === 'failed' ? (
                <View className="gap-3">
                  <Text className="font-sans-medium text-base text-danger">
                    The coach summary could not be generated.
                  </Text>
                  <Text className="font-sans text-sm leading-relaxed text-cream/80">
                    Your jam and phrase data were still saved on this device.
                  </Text>
                  {summary ? (
                    <Text className="font-sans text-sm leading-relaxed text-cream/80">{summary}</Text>
                  ) : null}
                  {onRetry ? (
                    <AnimatedPressable
                      onPress={onRetry}
                      haptic="light"
                      className="mt-1 items-center rounded-xl border border-amber-accent/50 py-3"
                      accessibilityRole="button"
                      accessibilityLabel="Retry jam summary"
                    >
                      <Text className="font-sans-medium text-sm text-amber-light">Retry analysis</Text>
                    </AnimatedPressable>
                  ) : null}
                </View>
              ) : null}

              {status === 'skipped' ? (
                <View className="gap-2">
                  <Text className="font-sans-medium text-base text-cream">Not enough phrases yet</Text>
                  <Text className="font-sans text-sm leading-relaxed text-cream/80">
                    This jam did not capture any phrases to analyze. Try playing a few longer lines next time.
                  </Text>
                  {summary ? (
                    <Text className="font-sans text-sm leading-relaxed text-cream/80">{summary}</Text>
                  ) : null}
                </View>
              ) : null}

              {status === 'ready' && !bundle ? (
                <View className="gap-2">
                  <Text className="font-sans-medium text-base text-cream">Jam saved</Text>
                  <Text className="font-sans text-sm leading-relaxed text-cream/80">
                    {summary || 'No coach summary was saved for this jam.'}
                  </Text>
                </View>
              ) : null}

              {status === 'ready' && bundle ? (
                <View className="gap-4">
                  <View className="flex-row items-center gap-4">
                    <View
                      className="h-16 w-16 items-center justify-center rounded-full border-2"
                      style={{ borderColor: gradeColor(bundle.grade) }}
                    >
                      <Text
                        className="font-serif-bold text-2xl"
                        style={{ color: gradeColor(bundle.grade) }}
                      >
                        {bundle.grade}
                      </Text>
                    </View>
                    <View className="flex-1">
                      <Text className="font-sans-medium text-base text-cream">
                        {Math.round(bundle.grade_score)} / 100
                      </Text>
                      <Text className="mt-0.5 font-sans text-xs text-muted-light">
                        {bundle.phrase_count} {bundle.phrase_count === 1 ? 'phrase' : 'phrases'} ·{' '}
                        {bundle.total_notes} notes
                      </Text>
                    </View>
                  </View>

                  {summary ? (
                    <Text className="font-sans text-sm leading-relaxed text-cream/85">{summary}</Text>
                  ) : null}

                  {onPracticePhrase && weakestFeedback && weakestMetrics ? (
                    <AnimatedPressable
                      onPress={() => {
                        if (weakestHasLoop) onPracticePhrase(weakestFeedback, weakestMetrics)
                      }}
                      haptic="light"
                      disabled={!weakestHasLoop}
                      className={`items-center rounded-xl border px-4 py-3 ${
                        weakestHasLoop
                          ? 'border-amber-accent/50 bg-amber-accent/10'
                          : 'border-wood-700/50 opacity-50'
                      }`}
                      accessibilityRole="button"
                      accessibilityLabel={
                        weakestHasLoop
                          ? `Practice weakest phrase ${weakestFeedback.phrase_index + 1} slowly`
                          : 'Weakest phrase has no matching loop'
                      }
                    >
                      <Text
                        className={`font-sans-medium text-sm ${
                          weakestHasLoop ? 'text-amber-light' : 'text-muted-light'
                        }`}
                      >
                        {weakestHasLoop ? 'Practice weakest phrase · 0.75×' : 'No matching loop'}
                      </Text>
                    </AnimatedPressable>
                  ) : null}

                  {bundle.coach_strengths.length > 0 ? (
                    <View className="gap-1">
                      <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">
                        What worked
                      </Text>
                      {bundle.coach_strengths.map((line, i) => (
                        <Text key={`strength-${i}`} className="font-sans text-sm text-cream/80">
                          · {line}
                        </Text>
                      ))}
                    </View>
                  ) : null}

                  {bundle.coach_focus_areas.length > 0 ? (
                    <View className="gap-1">
                      <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">
                        Focus next
                      </Text>
                      {bundle.coach_focus_areas.map((line, i) => (
                        <Text key={`focus-${i}`} className="font-sans text-sm text-cream/80">
                          · {line}
                        </Text>
                      ))}
                    </View>
                  ) : null}

                  {bundle.phrase_feedback.length > 0 ? (
                    <View className="gap-2">
                      <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">
                        Phrase by phrase
                      </Text>
                      {bundle.phrase_feedback.map((feedback) => {
                        const metrics = phraseMetricsFor(feedback, phrases)
                        const hasLoop =
                          metrics != null &&
                          track != null &&
                          metrics.backing_start_ms != null &&
                          metrics.backing_end_ms != null &&
                          metrics.backing_end_ms > metrics.backing_start_ms
                        return (
                          <View
                            key={`phrase-${feedback.phrase_index}`}
                            className="rounded-xl border border-wood-700/60 bg-wood-800/50 p-3"
                          >
                            <View className="flex-row items-center justify-between">
                              <Text className="font-sans-medium text-sm text-cream">
                                Phrase {feedback.phrase_index + 1}
                              </Text>
                              <Text className="font-mono text-xs text-muted-light">
                                clarity {Math.round(feedback.clarity * 100)}%
                              </Text>
                            </View>
                            <Text className="mt-1 font-sans text-sm leading-snug text-cream/80">
                              {feedback.suggestion}
                            </Text>
                            {onPracticePhrase ? (
                              <AnimatedPressable
                                onPress={() => {
                                  if (hasLoop && metrics) onPracticePhrase(feedback, metrics)
                                }}
                                haptic="light"
                                disabled={!hasLoop}
                                className={`mt-2 self-start rounded-lg border px-3 py-2 ${
                                  hasLoop
                                    ? 'border-amber-accent/50'
                                    : 'border-wood-700/50 opacity-50'
                                }`}
                                accessibilityRole="button"
                                accessibilityLabel={`Practice phrase ${feedback.phrase_index + 1} slowly`}
                              >
                                <Text
                                  className={`font-sans-medium text-xs ${
                                    hasLoop ? 'text-amber-light' : 'text-muted-light'
                                  }`}
                                >
                                  {hasLoop ? 'Practice this phrase · 0.75×' : 'No matching loop'}
                                </Text>
                              </AnimatedPressable>
                            ) : null}
                          </View>
                        )
                      })}
                    </View>
                  ) : null}

                  {bundle.coach_next_step ? (
                    <View className="rounded-xl border border-amber-accent/30 bg-amber-accent/10 p-3">
                      <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">
                        Next step
                      </Text>
                      <Text className="mt-1 font-sans text-sm text-cream/85">
                        {bundle.coach_next_step}
                      </Text>
                    </View>
                  ) : null}
                </View>
              ) : null}
            </ScrollView>
          </View>
        </View>
      </View>
    </Modal>
  )
}
