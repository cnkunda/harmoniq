import type { ReactNode } from 'react'
import { Pressable, Text, View } from 'react-native'

import { useLessonStore } from '@/src/stores/lessonStore'

export interface SessionStepScreenProps {
  title: string
  subtitle?: string
  children?: ReactNode
  showBack: boolean
  backLabel?: string
  onBack: () => void
  showNext: boolean
  nextLabel?: string
  onNext: () => void
}

export function SessionStepScreen({
  title,
  subtitle,
  children,
  showBack,
  backLabel = 'Back',
  onBack,
  showNext,
  nextLabel = 'Next',
  onNext,
}: SessionStepScreenProps) {
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const songTitle = lesson?.song_title?.trim() || null
  const sectionTotal = lesson?.sections?.length ?? 0

  return (
    <View className="flex-1 px-6 pb-8 pt-2">
      <Text className="text-3xl font-serif text-amber-accent">{title}</Text>
      {subtitle ? (
        <Text className="mt-2 font-sans text-sm leading-relaxed text-cream">{subtitle}</Text>
      ) : null}

      <View className="mt-6 rounded-xl border border-wood-600 bg-wood-800/80 p-4">
        <Text className="font-sans-medium text-xs uppercase tracking-wide text-muted-brown">
          lessonStore
        </Text>
        <Text className="mt-1 font-sans text-sm text-cream">
          {songTitle ? (
            <>
              Song: <Text className="font-sans-medium text-amber-light">{songTitle}</Text>
            </>
          ) : (
            <Text className="text-muted-brown">No lesson loaded yet — run Analyze (debug) first.</Text>
          )}
        </Text>
        <Text className="mt-1 font-mono text-xs text-muted-brown">
          lessonSectionIndex={lessonSectionIndex}
          {sectionTotal > 0 ? ` · sections.length=${sectionTotal}` : ''}
        </Text>
      </View>

      {children}

      <View className="mt-auto flex-row gap-3 pt-8">
        {showBack ? (
          <Pressable
            onPress={onBack}
            className="flex-1 rounded-lg border border-wood-600 py-3"
            accessibilityRole="button"
          >
            <Text className="text-center font-sans-medium text-cream">{backLabel}</Text>
          </Pressable>
        ) : (
          <View className="flex-1" />
        )}
        {showNext ? (
          <Pressable
            onPress={onNext}
            className="flex-1 rounded-lg bg-amber-accent py-3"
            accessibilityRole="button"
          >
            <Text className="text-center font-sans-medium text-wood-900">{nextLabel}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  )
}
