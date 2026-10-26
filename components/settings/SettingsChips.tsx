import { AnimatedPressable } from '@/components/AnimatedPressable'
import { Text, View } from 'react-native'

import {
  CHOICE_CHIP_BASE,
  CHOICE_CHIP_OFF,
  CHOICE_CHIP_ON,
  CHOICE_LABEL_SANS_OFF,
  CHOICE_LABEL_SANS_ON,
} from '@/src/constants/uiTokens'

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
              className={`${CHOICE_CHIP_BASE} ${isSelected ? CHOICE_CHIP_ON : CHOICE_CHIP_OFF}`}
              accessibilityRole="button"
              accessibilityState={{ selected: isSelected }}
            >
              <Text className={`capitalize ${isSelected ? CHOICE_LABEL_SANS_ON : CHOICE_LABEL_SANS_OFF}`}>
                {option}
              </Text>
            </AnimatedPressable>
          )
        })}
      </View>
    </View>
  )
}
