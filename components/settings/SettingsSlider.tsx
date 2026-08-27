import Slider from '@react-native-community/slider'
import { Text, View } from 'react-native'

import colors from '@/src/constants/colors'

interface SettingsSliderProps {
  label: string
  description?: string
  value: number
  min: number
  max: number
  step: number
  onValueChange: (value: number) => void
  formatValue?: (value: number) => string
}

export function SettingsSlider({
  label,
  description,
  value,
  min,
  max,
  step,
  onValueChange,
  formatValue = (v) => v.toFixed(2),
}: SettingsSliderProps) {
  return (
    <View className="py-2">
      <View className="flex-row items-center justify-between">
        <Text className="font-sans-medium text-sm text-cream">{label}</Text>
        <Text className="font-sans text-xs text-amber-light">{formatValue(value)}</Text>
      </View>
      {description && (
        <Text className="mt-1 font-sans text-[11px] text-muted-light">{description}</Text>
      )}
      <Slider
        style={{ width: '100%', height: 40, marginTop: 8 }}
        minimumValue={min}
        maximumValue={max}
        step={step}
        value={value}
        minimumTrackTintColor={colors.amber.accent}
        maximumTrackTintColor={colors.wood[600]}
        thumbTintColor={colors.amber.light}
        onValueChange={onValueChange}
      />
    </View>
  )
}
