import React, { useCallback } from 'react'
import { View, Text, TextInput } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'
import colors from '@/src/constants/colors'

export interface BpmEditorProps {
  value: number
  onChange: (bpm: number) => void
  min?: number
  max?: number
  step?: number
  fineStep?: number
  style?: object
}

export function BpmEditor({
  value,
  onChange,
  min = 20,
  max = 300,
  step = 5,
  fineStep = 1,
  style,
}: BpmEditorProps) {
  const clamp = useCallback((v: number) => Math.round(Math.max(min, Math.min(max, v)) * 10) / 10, [min, max])

  const increment = useCallback(() => onChange(clamp(value + step)), [value, step, clamp, onChange])
  const decrement = useCallback(() => onChange(clamp(value - step)), [value, step, clamp, onChange])
  const fineIncrement = useCallback(() => onChange(clamp(value + fineStep)), [value, fineStep, clamp, onChange])
  const fineDecrement = useCallback(() => onChange(clamp(value - fineStep)), [value, fineStep, clamp, onChange])

  const handleTextChange = useCallback(
    (text: string) => {
      const num = parseFloat(text)
      if (!isNaN(num)) {
        onChange(clamp(num))
      }
    },
    [clamp, onChange],
  )

  return (
    <View style={[{ gap: 6 }, style]}>
      <Text className="text-xs font-sans text-muted-brown">BPM</Text>
      <View className="flex-row items-center gap-2">
        <AnimatedPressable
          onPress={decrement}
          haptic="light"
          className="rounded-lg px-3 py-2"
          style={{ backgroundColor: colors.wood[700] }}
        >
          <Text className="text-lg font-mono" style={{ color: colors.cream }}>
            -{step}
          </Text>
        </AnimatedPressable>

        <AnimatedPressable
          onPress={fineDecrement}
          haptic="light"
          className="rounded-lg px-2 py-2"
          style={{ backgroundColor: colors.wood[700] }}
        >
          <Text className="text-sm font-mono" style={{ color: colors.muted.brown }}>
            -{fineStep}
          </Text>
        </AnimatedPressable>

        <TextInput
          value={String(Math.round(value))}
          onChangeText={handleTextChange}
          keyboardType="numeric"
          className="text-center font-mono text-lg"
          style={{
            color: colors.cream,
            backgroundColor: colors.wood[800],
            borderWidth: 1,
            borderColor: colors.wood[600],
            borderRadius: 8,
            paddingHorizontal: 12,
            paddingVertical: 6,
            minWidth: 60,
          }}
        />

        <AnimatedPressable
          onPress={fineIncrement}
          haptic="light"
          className="rounded-lg px-2 py-2"
          style={{ backgroundColor: colors.wood[700] }}
        >
          <Text className="text-sm font-mono" style={{ color: colors.muted.brown }}>
            +{fineStep}
          </Text>
        </AnimatedPressable>

        <AnimatedPressable
          onPress={increment}
          haptic="light"
          className="rounded-lg px-3 py-2"
          style={{ backgroundColor: colors.wood[700] }}
        >
          <Text className="text-lg font-mono" style={{ color: colors.cream }}>
            +{step}
          </Text>
        </AnimatedPressable>
      </View>
    </View>
  )
}
