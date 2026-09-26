import { useState } from 'react'
import { ChevronDown, type LucideIcon } from 'lucide-react-native'
import Animated, {
  FadeInDown,
  Layout,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from 'react-native-reanimated'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { colors } from '@/src/constants/colors'

interface SettingsSectionProps {
  icon: LucideIcon
  title: string
  description?: string
  defaultOpen?: boolean
  children: React.ReactNode
}

export function SettingsSection({
  icon: Icon,
  title,
  description,
  defaultOpen = true,
  children,
}: SettingsSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  const rotation = useSharedValue(defaultOpen ? 180 : 0)

  const chevronStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${rotation.value}deg` }],
  }))

  const toggle = () => {
    const next = !isOpen
    setIsOpen(next)
    rotation.value = withSpring(next ? 180 : 0, { damping: 16, stiffness: 180 })
  }

  return (
    <View className="mb-6 overflow-hidden rounded-xl border border-wood-600/50 bg-wood-800/80">
      <AnimatedPressable
        onPress={toggle}
        haptic="light"
        className="flex-row items-center gap-3 border-b border-wood-600/35 bg-wood-800/60 px-4 py-4"
        accessibilityRole="button"
        accessibilityState={{ expanded: isOpen }}
        accessibilityLabel={`${title}, ${isOpen ? 'expanded' : 'collapsed'}`}
      >
        <View className="h-10 w-10 items-center justify-center rounded-full bg-wood-700">
          <Icon color={colors.amber.accent} size={20} strokeWidth={2} />
        </View>
        <View className="flex-1">
          <Text className="font-sans-medium text-sm text-cream">{title}</Text>
          {description ? (
            <Text className="mt-0.5 font-sans text-xs text-muted-brown">{description}</Text>
          ) : null}
        </View>
        <Animated.View style={chevronStyle}>
          <ChevronDown color={colors.muted.brown} size={20} strokeWidth={2} />
        </Animated.View>
      </AnimatedPressable>

      {isOpen && (
        <Animated.View entering={FadeInDown} layout={Layout}>
          <View className="p-4">{children}</View>
        </Animated.View>
      )}
    </View>
  )
}
