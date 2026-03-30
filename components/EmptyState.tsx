import { Text, View } from 'react-native'
import type { LucideIcon } from 'lucide-react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import colors from '@/src/constants/colors'

export interface EmptyStateProps {
  Icon: LucideIcon
  heading: string
  subtext: string
  ctaLabel?: string
  onCta?: () => void
}

export function EmptyState({ Icon, heading, subtext, ctaLabel, onCta }: EmptyStateProps) {
  return (
    <View className="min-h-[180px] flex-1 items-center justify-center gap-4 px-10">
      <View className="mb-2 h-20 w-20 items-center justify-center rounded-full border border-wood-700/50 bg-wood-800">
        <Icon color={colors.amber.accent} size={36} strokeWidth={1.5} />
      </View>
      <Text className="text-center font-serif text-xl text-cream">{heading}</Text>
      <Text className="text-center font-sans leading-relaxed text-muted-brown">{subtext}</Text>
      {ctaLabel && onCta && (
        <AnimatedPressable
          onPress={onCta}
          haptic="medium"
          className="mt-4 rounded-xl bg-amber-accent px-8 py-3.5"
        >
          <Text className="font-sans-medium text-wood-900">{ctaLabel}</Text>
        </AnimatedPressable>
      )}
    </View>
  )
}
