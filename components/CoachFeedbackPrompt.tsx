import { Check, SkipForward, X } from 'lucide-react-native'
import { useState } from 'react'
import { Text, View } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'

import colors from '@/src/constants/colors'
import { getSessionCount, recordCoachFeedback, type CoachFeedbackRating } from '@/src/session'

export interface CoachFeedbackPromptProps {
  focusArea: string | null
  onFeedbackSubmitted?: (rating: CoachFeedbackRating) => void
  onDismissed?: () => void
}

/**
 * Feedback prompt for coach redundancy perception (commit 90).
 * Asks users whether coach feedback felt repetitive after each session.
 */
export function CoachFeedbackPrompt({ focusArea, onFeedbackSubmitted, onDismissed }: CoachFeedbackPromptProps) {
  const [submitted, setSubmitted] = useState(false)

  const handleFeedback = async (rating: CoachFeedbackRating) => {
    if (submitted) return
    setSubmitted(true)

    try {
      const sessionCount = await getSessionCount()
      await recordCoachFeedback({
        focus_area: focusArea,
        rating,
        session_count: sessionCount,
      })
      onFeedbackSubmitted?.(rating)
    } catch (error) {
      console.error('Failed to record coach feedback:', error)
    }
  }

  const handleSkip = () => {
    if (submitted) return
    setSubmitted(true)
    handleFeedback('skipped')
  }

  if (submitted) {
    return null
  }

  return (
    <View className="mx-4 mb-4 rounded-xl border border-wood-600/30 bg-wood-800/60 p-4">
      <Text className="mb-3 font-sans text-[14px] font-medium text-cream/80">
        How was this coaching tip?
      </Text>
      <View className="flex-row gap-2">
        <AnimatedPressable
          haptic="light"
          onPress={() => handleFeedback('helpful')}
          className="flex-1 flex-row items-center justify-center gap-2 rounded-lg bg-success/20 px-3 py-2.5"
        >
          <Check color={colors.success} size={16} strokeWidth={2} />
          <Text className="font-sans text-[13px] font-medium text-success">Helpful</Text>
        </AnimatedPressable>
        <AnimatedPressable
          haptic="light"
          onPress={() => handleFeedback('repetitive')}
          className="flex-1 flex-row items-center justify-center gap-2 rounded-lg bg-danger/20 px-3 py-2.5"
        >
          <X color={colors.danger} size={16} strokeWidth={2} />
          <Text className="font-sans text-[13px] font-medium text-danger">Repetitive</Text>
        </AnimatedPressable>
        <AnimatedPressable
          haptic="light"
          onPress={() => handleFeedback('neutral')}
          className="flex-1 flex-row items-center justify-center gap-2 rounded-lg bg-wood-700/50 px-3 py-2.5"
        >
          <Text className="font-sans text-[13px] font-medium text-cream/70">Neutral</Text>
        </AnimatedPressable>
        <AnimatedPressable
          haptic="light"
          onPress={handleSkip}
          className="flex-row items-center justify-center rounded-lg bg-transparent px-2 py-2.5"
        >
          <SkipForward color={colors.muted.brown} size={16} strokeWidth={2} />
        </AnimatedPressable>
      </View>
    </View>
  )
}
