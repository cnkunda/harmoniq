import React from 'react'
import { View, Text } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'
import colors from '@/src/constants/colors'

export interface TimeSignaturePickerProps {
  value: { numerator: number; denominator: number }
  onChange: (ts: { numerator: number; denominator: number }) => void
  style?: object
}

const TIME_SIGNATURES = [
  { numerator: 2, denominator: 4, label: '2/4' },
  { numerator: 3, denominator: 4, label: '3/4' },
  { numerator: 4, denominator: 4, label: '4/4' },
  { numerator: 6, denominator: 8, label: '6/8' },
  { numerator: 9, denominator: 8, label: '9/8' },
  { numerator: 12, denominator: 8, label: '12/8' },
]

export function TimeSignaturePicker({ value, onChange, style }: TimeSignaturePickerProps) {
  const currentLabel = `${value.numerator}/${value.denominator}`

  return (
    <View style={[{ gap: 6 }, style]}>
      <Text className="text-xs font-sans text-muted-light mb-1">Time Signature</Text>
      <View className="flex-row flex-wrap gap-2">
        {TIME_SIGNATURES.map((ts) => {
          const isSelected = ts.numerator === value.numerator && ts.denominator === value.denominator
          return (
            <AnimatedPressable
              key={ts.label}
              onPress={() => onChange({ numerator: ts.numerator, denominator: ts.denominator })}
              haptic="light"
              className="rounded-lg px-3 py-2"
              style={{
                backgroundColor: isSelected ? colors.amber.accent : colors.wood[700],
                borderWidth: 1,
                borderColor: isSelected ? colors.amber.accent : colors.wood[600],
              }}
            >
              <Text
                className="text-sm font-mono"
                style={{ color: isSelected ? colors.wood[900] : colors.cream }}
              >
                {ts.label}
              </Text>
            </AnimatedPressable>
          )
        })}
      </View>
    </View>
  )
}
