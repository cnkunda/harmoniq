import type { ReactNode } from 'react'
import { ScrollView, Text, View } from 'react-native'

import { Button } from '@/components/Button'

export interface SessionStepScreenProps {
  title: string
  subtitle?: string
  /** Small uppercase eyebrow text shown above the title (e.g. "ORIENT PHASE"). */
  phaseEyebrow?: string | null
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
  /** Optional NativeWind classes for the fixed footer row. */
  footerContainerClassName?: string
  backButtonClassName?: string
  nextButtonClassName?: string
}

export function SessionStepScreen({
  title,
  subtitle,
  phaseEyebrow,
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
    footerContainerClassName ??
    'flex-row gap-3 border-t border-wood-600/30 bg-wood-800/60 px-6 pb-8 pt-4'

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
            {phaseEyebrow ? (
              <Text className="font-sans-medium text-[10px] uppercase tracking-[0.18em] text-amber-accent">
                {phaseEyebrow}
              </Text>
            ) : null}
            <Text className={`text-3xl font-serif text-cream ${phaseEyebrow ? 'mt-1' : ''}`}>{title}</Text>
            {subtitle ? (
              <Text className="mt-2 font-sans text-sm leading-relaxed text-muted-brown">{subtitle}</Text>
            ) : null}
          </>
        ) : null}

        {children}
      </ScrollView>

      {hideFooter ? null : (
        <View className={footerRow}>
          {showBack ? (
            <Button
              label={backLabel}
              variant="secondary"
              onPress={onBack}
              accessibilityLabel={backLabel}
              containerClassName="flex-1"
              className={backButtonClassName ?? ''}
            />
          ) : (
            <View className="flex-1" />
          )}
          {showNext ? (
            <Button
              label={nextLabel}
              variant="primary"
              onPress={onNext}
              accessibilityLabel={nextLabel}
              containerClassName="flex-1"
              className={nextButtonClassName ?? ''}
            />
          ) : null}
        </View>
      )}
    </View>
  )
}
