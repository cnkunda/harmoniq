import { AnimatedPressable } from '@/components/AnimatedPressable'
import { Text, View } from 'react-native'

import colors from '@/src/constants/colors'

interface SettingsSegmentedProps {
  label: string
  description?: string
  options: readonly string[]
  value: string
  onValueChange: (value: string) => void
}

export function SettingsSegmented({
  label,
  description,
  options,
  value,
  onValueChange,
}: SettingsSegmentedProps) {
  return (
    <View className="py-2">
      <Text className="font-sans-medium text-sm text-cream">{label}</Text>
      {description && (
        <Text className="mt-1 font-sans text-[11px] text-muted-light">{description}</Text>
      )}
      <View className="mt-3 flex-row gap-2">
        {options.map((option) => {
          const isSelected = value === option
          return (
            <AnimatedPressable
              key={option}
              onPress={() => onValueChange(option)}
              haptic="light"
              className={`flex-1 rounded-lg border px-3 py-2.5 ${
                isSelected
                  ? 'border-amber-accent bg-amber-accent/20'
                  : 'border-wood-600/50 bg-wood-900/40'
              }`}
              accessibilityRole="button"
              accessibilityState={{ selected: isSelected }}
            >
              <Text
                className={`text-center font-sans-medium text-xs capitalize ${
                  isSelected ? 'text-amber-light' : 'text-cream'
                }`}
              >
                {option}
              </Text>
            </AnimatedPressable>
          )
        })}
      </View>
    </View>
  )
}
