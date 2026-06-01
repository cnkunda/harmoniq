/** Commit 109: Time signature picker — numerator/denominator chips per section. */

import { Pressable, Text, View } from 'react-native'

import colors from '@/src/constants/colors'

const NUMERATOR_OPTIONS = [2, 3, 4, 6, 9, 12] as const
const DENOMINATOR_OPTIONS = [4, 8] as const

export interface TimeSignaturePickerProps {
  numerator: number
  denominator: number
  onChange: (numerator: number, denominator: number) => void
  disabled?: boolean
}

function Chip({
  label,
  active,
  onPress,
  disabled,
}: {
  label: string
  active: boolean
  onPress: () => void
  disabled?: boolean
}) {
  return (
    <Pressable
      onPress={() => {
        if (!disabled) onPress()
      }}
      className="h-8 min-w-[32px] items-center justify-center rounded-full px-3"
      style={{
        backgroundColor: active ? colors.amber.accent : colors.wood[700],
        opacity: disabled ? 0.4 : 1,
      }}
    >
      <Text
        style={{
          fontSize: 13,
          fontWeight: active ? '600' : '400',
          color: active ? colors.wood[900] : colors.cream,
        }}
      >
        {label}
      </Text>
    </Pressable>
  )
}

/**
 * Picker for time signature with numerator and denominator chips.
 * Supports 2/4, 3/4, 4/4, 6/8, 9/8, 12/8.
 */
export function TimeSignaturePicker({
  numerator,
  denominator,
  onChange,
  disabled = false,
}: TimeSignaturePickerProps) {
  return (
    <View className="gap-2">
      <Text className="font-sans-medium text-xs uppercase tracking-wide text-muted-brown">
        Numerator
      </Text>
      <View className="flex-row flex-wrap gap-1.5">
        {NUMERATOR_OPTIONS.map((n) => (
          <Chip
            key={`num-${n}`}
            label={String(n)}
            active={numerator === n}
            onPress={() => onChange(n, denominator)}
            disabled={disabled}
          />
        ))}
      </View>

      <Text className="mt-1 font-sans-medium text-xs uppercase tracking-wide text-muted-brown">
        Denominator
      </Text>
      <View className="flex-row gap-1.5">
        {DENOMINATOR_OPTIONS.map((d) => (
          <Chip
            key={`den-${d}`}
            label={String(d)}
            active={denominator === d}
            onPress={() => onChange(numerator, d)}
            disabled={disabled}
          />
        ))}
      </View>
    </View>
  )
}
