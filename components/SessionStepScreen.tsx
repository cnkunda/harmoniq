import type { ReactNode } from 'react'
import { Pressable, ScrollView, Text, View } from 'react-native'

export interface SessionStepScreenProps {
  title: string
  subtitle?: string
  /** Hide the scroll header block (warm-up uses inline section labels). */
  hideTitle?: boolean
  /** Hide the fixed bottom bar (e.g. tune step uses in-flow actions). */
  hideFooter?: boolean
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
  hideFooter = false,
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
  const footerRow =
    footerContainerClassName ?? 'flex-row gap-3 border-t border-wood-600/30 bg-wood-900 px-6 pb-8 pt-4 shadow-soft-wood'
  const backClass = backButtonClassName ?? 'flex-1 rounded-xl border border-wood-600 bg-wood-800 py-3.5'
  const nextClass = nextButtonClassName ?? 'flex-1 rounded-xl bg-amber-accent py-3.5 shadow-soft-wood'

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
            <Text className="font-serif text-2xl text-wood-900">{title}</Text>
            {subtitle ? (
              <Text className="mt-1.5 font-sans text-sm leading-6 text-wood-600">{subtitle}</Text>
            ) : null}
          </>
        ) : null}

        {children}
      </ScrollView>

      {hideFooter ? null : (
        <View className={footerRow}>
          {showBack ? (
            <Pressable
              onPress={onBack}
              className={`${backClass} items-center justify-center`}
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
                className={`${nextClass} flex-nowrap items-center justify-center`}
                accessibilityRole="button"
              >
                 <Text className="text-center font-sans-medium text-wood-900 whitespace-nowrap">{nextLabel}</Text>
              </Pressable>
            ) : null}
        </View>
      )}
    </View>
  )
}
