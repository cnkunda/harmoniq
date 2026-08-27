import { AnimatedPressable } from '@/components/AnimatedPressable'
import { Text, View } from 'react-native'

import colors from '@/src/constants/colors'

interface SettingsChipsProps {
  label: string
  description?: string
  options: readonly string[]
  value: string
  onValueChange: (value: string) => void
}

export function SettingsChips({ label, description, options, value, onValueChange }: SettingsChipsProps) {
  return (
    <View className="py-2">
      <Text className="font-sans-medium text-sm text-cream">{label}</Text>
      {description && (
        <Text className="mt-1 font-sans text-[11px] text-muted-light">{description}</Text>
      )}
      <View className="mt-3 flex-row flex-wrap gap-2">
        {options.map((option) => {
          const isSelected = value === option
          return (
            <AnimatedPressable
              key={option}
              onPress={() => onValueChange(option)}
              haptic="light"
              className={`rounded-full border px-3 py-1.5 ${
                isSelected
                  ? 'border-amber-accent bg-amber-accent/20'
                  : 'border-wood-600/50 bg-wood-900/40'
              }`}
              accessibilityRole="button"
              accessibilityState={{ selected: isSelected }}
            >
              <Text
                className={`font-sans text-xs capitalize ${
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
