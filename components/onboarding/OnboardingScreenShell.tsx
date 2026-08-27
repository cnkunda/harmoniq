import type { ReactNode } from 'react'
import { ScrollView, Text, View } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'
import { SafeAreaView } from 'react-native-safe-area-context'

import { WoodGradient } from '@/components/WoodGradient'

import { OnboardingProgress } from './OnboardingProgress'

/** Pre-results flow: welcome, mic, three phrase screens */
export const ONBOARDING_PLACEMENT_STEP_COUNT = 5

export type OnboardingScreenShellProps = {
  currentStep: number
  totalSteps?: number
  showProgress?: boolean
  showBack?: boolean
  onBack?: () => void
  footer?: ReactNode
  /** When true, main content scrolls and vertically centers when short */
  scrollable?: boolean
  children: ReactNode
}

export function OnboardingScreenShell({
  currentStep,
  totalSteps = ONBOARDING_PLACEMENT_STEP_COUNT,
  showProgress = true,
  showBack = false,
  onBack,
  footer,
  scrollable = false,
  children,
}: OnboardingScreenShellProps) {
  const showHeader = showBack || showProgress

  const header = showHeader ? (
    <View className="min-h-11 flex-row items-center justify-between px-6 pt-2">
      {showBack ? (
        <AnimatedPressable
          haptic="light"
          onPress={onBack}
          className="min-h-[44px] min-w-[44px] justify-center py-2 pr-2"
          accessibilityRole="button"
          accessibilityLabel="Back"
        >
          <Text className="font-sans text-sm text-muted-light">Back</Text>
        </AnimatedPressable>
      ) : (
        <View className="w-9" />
      )}
      {showProgress ? (
        <View className="w-44">
          <OnboardingProgress totalSteps={totalSteps} currentStep={currentStep} />
        </View>
      ) : (
        <View className="w-9" />
      )}
    </View>
  ) : null

  const column = (
    <View className="w-full max-w-md self-center px-6 md:max-w-2xl lg:max-w-3xl">
      {children}
    </View>
  )

  return (
    <WoodGradient variant="background" className="flex-1">
      <SafeAreaView className="flex-1" edges={['top', 'right', 'bottom', 'left']}>
        {header}
        {scrollable ? (
          <ScrollView
            className="flex-1"
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={{
              flexGrow: 1,
              paddingBottom: 32,
              justifyContent: 'center',
            }}
          >
            {column}
            {footer ? <View className="mt-8 w-full max-w-md self-center px-6 md:max-w-2xl lg:max-w-3xl">{footer}</View> : null}
          </ScrollView>
        ) : (
          <>
            <View className="flex-1 justify-center">{column}</View>
            {footer ? (
              <View className="pb-4">
                <View className="w-full max-w-md self-center px-6 md:max-w-2xl lg:max-w-3xl">{footer}</View>
              </View>
            ) : null}
          </>
        )}
      </SafeAreaView>
    </WoodGradient>
  )
}
