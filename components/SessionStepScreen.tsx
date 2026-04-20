import type { ReactNode } from 'react'
import { Pressable, ScrollView, Text, View } from 'react-native'

export interface SessionStepScreenProps {
  title: string
  subtitle?: string
  /** Hide the scroll header block (warm-up uses inline section labels). */
  hideTitle?: boolean
  children?: ReactNode
  showBack: boolean
  backLabel?: string
  onBack: () => void
  showNext: boolean
  nextLabel?: string
  onNext: () => void
  /** Optional NativeWind classes for the fixed footer row (warm-up and other custom steps). */
  footerContainerClassName?: string
  backButtonClassName?: string
  nextButtonClassName?: string
}

export function SessionStepScreen({
  title,
  subtitle,
  hideTitle = false,
  children,
  showBack,
  backLabel = 'Back',
  onBack,
  showNext,
  nextLabel = 'Next',
  onNext,
  footerContainerClassName,
  backButtonClassName,
  nextButtonClassName,
}: SessionStepScreenProps) {
  const footerRow = footerContainerClassName ?? 'flex-row gap-3 border-t border-wood-600/25 bg-ivory px-6 pb-8 pt-4'
  const backClass = backButtonClassName ?? 'flex-1 rounded-lg border border-wood-600/55 bg-cream-dark/60 py-3'
  const nextClass = nextButtonClassName ?? 'flex-1 rounded-lg bg-amber-accent/90 py-3'

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
        {!hideTitle ? (
          <>
            <Text className="text-3xl font-serif text-wood-900">{title}</Text>
            {subtitle ? (
              <Text className="mt-2 font-sans text-sm leading-relaxed text-muted-brown">{subtitle}</Text>
            ) : null}
          </>
        ) : null}

        {children}
      </ScrollView>

      <View className={footerRow}>
        {showBack ? (
          <Pressable
            onPress={onBack}
            className={backClass}
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
            className={nextClass}
            accessibilityRole="button"
          >
            <Text className="text-center font-sans-medium text-wood-900">{nextLabel}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  )
}
