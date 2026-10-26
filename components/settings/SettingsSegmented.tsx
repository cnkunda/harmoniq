import { AnimatedPressable } from '@/components/AnimatedPressable'
import { Text, View } from 'react-native'

interface SettingsSegmentedProps {
  label: string
  description?: string
  options: readonly string[]
  value: string
  onValueChange: (value: string) => void
  /** Capitalize option labels (e.g. lowercase enum values in Settings). */
  capitalizeOptions?: boolean
}

export function SettingsSegmented({
  label,
  description,
  options,
  value,
  onValueChange,
  capitalizeOptions = false,
}: SettingsSegmentedProps) {
  return (
    <View className="py-2">
      <Text className="font-sans-medium text-sm text-cream">{label}</Text>
      {description && (
        <Text className="mt-1 font-sans text-[11px] text-muted-light">{description}</Text>
      )}
      <View className="mt-3 flex-row rounded-full border border-wood-600/50 bg-wood-900/40 p-1">
        {options.map((option) => {
          const isSelected = value === option
          return (
            <View key={option} className="flex-1">
              <AnimatedPressable
                onPress={() => onValueChange(option)}
                haptic="light"
                className={`rounded-full px-3 py-2.5 ${isSelected ? 'bg-amber-accent' : ''}`}
                accessibilityRole="button"
                accessibilityState={{ selected: isSelected }}
              >
                <Text
                  className={`text-center font-sans-medium text-xs ${
                    capitalizeOptions ? 'capitalize' : ''
                  } ${isSelected ? 'text-wood-900' : 'text-cream'}`}
                >
                  {option}
                </Text>
              </AnimatedPressable>
            </View>
          )
        })}
      </View>
    </View>
  )
}
