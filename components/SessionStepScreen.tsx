import type { ReactNode } from 'react'
import { Pressable, ScrollView, Text, View } from 'react-native'

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
    <View className="flex-1">
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{
          flexGrow: 1,
          paddingHorizontal: 24,
          paddingTop: 8,
          paddingBottom: 16,
        }}
        keyboardShouldPersistTaps="handled"
        nestedScrollEnabled
        showsVerticalScrollIndicator
      >
        <Text className="text-3xl font-serif text-wood-900">{title}</Text>
        {subtitle ? (
          <Text className="mt-2 font-sans text-sm leading-relaxed text-muted-brown">{subtitle}</Text>
        ) : null}

        <View className="mt-6 rounded-xl border border-wood-600/40 bg-cream-dark/50 p-4">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
            Current lesson
          </Text>
          <Text className="mt-1 font-sans text-sm text-wood-900">
            {songTitle ? (
              <>
                Song: <Text className="font-sans-medium text-amber-accent">{songTitle}</Text>
              </>
            ) : (
              <Text className="text-muted-brown">
                No lesson loaded yet — use Add Song to analyze audio, or open a save from your library.
              </Text>
            )}
          </Text>
          {songTitle && sectionTotal > 1 ? (
            <Text className="mt-1 font-sans text-xs text-muted-brown">
              Section {Math.min(lessonSectionIndex + 1, sectionTotal)} of {sectionTotal}
            </Text>
          ) : null}
          {__DEV__ && lesson ? (
            <Text className="mt-1 font-mono text-xs text-muted-brown">
              lessonSectionIndex={lessonSectionIndex}
              {sectionTotal > 0 ? ` · sections.length=${sectionTotal}` : ''}
            </Text>
          ) : null}
        </View>

        {children}
      </ScrollView>

      <View className="flex-row gap-3 border-t border-wood-600/25 bg-ivory px-6 pb-8 pt-4">
        {showBack ? (
          <Pressable
            onPress={onBack}
            className="flex-1 rounded-lg border border-wood-600/55 bg-cream-dark/60 py-3"
            accessibilityRole="button"
          >
            <Text className="text-center font-sans-medium text-wood-900">{backLabel}</Text>
          </Pressable>
        ) : (
          <View className="flex-1" />
        )}
        {showNext ? (
          <Pressable
            onPress={onNext}
            className="flex-1 rounded-lg bg-amber-accent/90 py-3"
            accessibilityRole="button"
          >
            <Text className="text-center font-sans-medium text-wood-900">{nextLabel}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  )
}
